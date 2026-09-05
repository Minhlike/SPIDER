"""Request accounting at the HTTP transport boundary; no URL/header/body logging."""
import httpx

CREDENTIAL_HEADERS = frozenset({"authorization", "cookie", "x-api-key", "x-key", "api-key"})


class MeteredTransport(httpx.AsyncBaseTransport):
    def __init__(self, ledger, budget, provider_id, inner=None, recorder=None, replay_cache=None):
        self.ledger, self.budget, self.provider_id = ledger, budget, provider_id
        # Disable hidden connection retries. Redirects re-enter handle_async_request.
        self.inner = inner if inner is not None else httpx.AsyncHTTPTransport(retries=0)
        self.recorder = recorder
        # Explicit run-local replay only, disabled by default; no credentials cached.
        self.replay_cache = replay_cache

    async def handle_async_request(self, request):
        credentialed = any(name in request.headers for name in CREDENTIAL_HEADERS)
        cacheable = request.method == "GET" and not credentialed
        key = ((str(request.url), tuple(request.headers.multi_items()))
               if cacheable else None)
        if cacheable and self.replay_cache is not None and key in self.replay_cache:
            if self.ledger is not None:
                self.ledger.record_cache_hit()
            status, headers, content = self.replay_cache[key]
            return httpx.Response(status, headers=headers, content=content)
        if self.ledger is not None:
            self.ledger.request(self.budget, self.provider_id)
        event = await self.recorder.begin(
            str(request.url),
            purpose=request.extensions.get("spider_purpose", "lookup"),
            credentialed=credentialed,
            identifier=request.extensions.get("spider_identifier"),
        ) if self.recorder else None
        try:
            response = await self.inner.handle_async_request(request)
        except BaseException:
            if event:
                await self.recorder.finish(event, "UNKNOWN_AFTER_DISPATCH")
            raise
        if event:
            await self.recorder.finish(event, "HTTP_" + str(response.status_code))
        if cacheable and self.replay_cache is not None and response.status_code == 200 and "set-cookie" not in response.headers:
            content = await response.aread()
            if len(content) <= 65536:
                self.replay_cache[key] = (response.status_code, dict(response.headers), content)
        return response

    async def aclose(self):
        await self.inner.aclose()


def provider_client(provider_id, options, **kwargs):
    inner = kwargs.pop("transport", None)
    return httpx.AsyncClient(trust_env=False, transport=MeteredTransport(
        options.get("request_ledger"), options.get("execution_budget"), provider_id, inner,
        options.get("egress_recorder")), **kwargs)
