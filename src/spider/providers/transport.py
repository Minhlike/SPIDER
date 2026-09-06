"""Request accounting at the HTTP transport boundary; no URL/header/body logging."""
import httpx
from spider.providers.http_plane import credentialed

class MeteredTransport(httpx.AsyncBaseTransport):
    def __init__(self, ledger, budget, provider_id, inner=None, recorder=None,
                 origin_limits=None, plane=None, run_scope=None):
        self.ledger, self.budget, self.provider_id = ledger, budget, provider_id
        # Disable hidden connection retries. Redirects re-enter handle_async_request.
        self.inner = inner if inner is not None else (None if plane else httpx.AsyncHTTPTransport(retries=0))
        self.recorder = recorder
        self.origin_limits = origin_limits
        self.plane, self.run_scope, self.temporary = plane, run_scope, []

    async def handle_async_request(self, request):
        if self.plane:
            return await self.plane.request(request, self.provider_id, self.run_scope,
                                            self.ledger, self._limited_request)
        return await self._limited_request(request)

    async def _limited_request(self, request):
        lease = await self.origin_limits.acquire(request.url.host) if self.origin_limits else None
        response = None
        try:
            response = await self._request(request)
            if self.origin_limits:
                self.origin_limits.feedback(request.url.host, response.status_code, response.headers.get("retry-after"))
            # Hold the origin slot through body collection, not just response headers.
            await response.aread()
            return response
        except BaseException:
            if response is not None:
                await response.aclose()
            raise
        finally:
            if lease:
                lease.release()

    async def _request(self, request):
        authenticated = credentialed(request)
        if self.ledger is not None:
            self.ledger.request(self.budget, self.provider_id)
        event = await self.recorder.begin(
            str(request.url),
            purpose=request.extensions.get("spider_purpose", "lookup"),
            credentialed=authenticated,
            identifier=request.extensions.get("spider_identifier"),
        ) if self.recorder else None
        try:
            inner = self.inner
            if inner is None:
                inner, temporary = self.plane.pool(self.provider_id, request)
                if temporary:
                    self.temporary.append(inner)
            response = await inner.handle_async_request(request)
        except BaseException:
            if event:
                await self.recorder.finish(event, "UNKNOWN_AFTER_DISPATCH")
            raise
        if event:
            await self.recorder.finish(event, "HTTP_" + str(response.status_code))
        return response

    async def aclose(self):
        if self.inner:
            await self.inner.aclose()
        for inner in self.temporary:
            await inner.aclose()


def provider_client(provider_id, options, **kwargs):
    inner = kwargs.pop("transport", None)
    return httpx.AsyncClient(trust_env=False, transport=MeteredTransport(
        options.get("request_ledger"), options.get("execution_budget"), provider_id, inner,
        options.get("egress_recorder"), origin_limits=options.get("origin_limits"),
        plane=options.get("http_plane"), run_scope=options.get("http_run_scope")), **kwargs)
