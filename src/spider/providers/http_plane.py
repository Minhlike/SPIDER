"""Bounded service-owned HTTP pools and run-scoped anonymous replay/coalescing."""
import asyncio
import hashlib
import hmac
import re
import secrets
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
import httpx

CREDENTIAL_HEADERS = frozenset({"authorization", "cookie", "x-api-key", "x-key", "api-key",
                                "x-api-token", "x-auth-token"})
CREDENTIAL_PARAMS = frozenset({"key", "api_key", "apikey", "token", "access_token", "password", "secret"})


def credentialed(request):
    return (any(name in request.headers for name in CREDENTIAL_HEADERS)
            or any(name.casefold() in CREDENTIAL_PARAMS for name in request.url.params))


class HTTPPlane:
    def __init__(self, factory=None, clock=time.monotonic):
        self.factory = factory or (lambda: httpx.AsyncHTTPTransport(retries=0,
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=2, keepalive_expiry=30)))
        self.clock = clock
        self.salt = secrets.token_bytes(32)
        self.pools, self.cache, self.locks = {}, OrderedDict(), {}
        self.closed = False

    def digest(self, value):
        return hmac.new(self.salt, repr(value).encode(), hashlib.sha256).hexdigest()

    def pool(self, provider, request):
        scope = (provider, tuple((k, v) for k, v in request.headers.multi_items() if k in CREDENTIAL_HEADERS),
                 tuple((k, v) for k, v in request.url.params.multi_items() if k.casefold() in CREDENTIAL_PARAMS))
        key = self.digest(scope)
        if key in self.pools:
            return self.pools[key], False
        transport = self.factory()
        if len(self.pools) < 16:
            self.pools[key] = transport
            return transport, False
        # Overflow clients own and close their temporary transport.
        return transport, True

    @asynccontextmanager
    async def coalesce(self, key):
        if key not in self.locks and len(self.locks) >= 128:
            yield
            return
        entry = self.locks.setdefault(key, [asyncio.Lock(), 0])
        entry[1] += 1
        try:
            async with entry[0]:
                yield
        finally:
            entry[1] -= 1
            if not entry[1]:
                self.locks.pop(key, None)

    async def request(self, request, provider, run_scope, ledger, dispatch):
        if self.closed:
            raise RuntimeError("HTTP plane is closed")
        request_control = request.headers.get("cache-control", "").casefold()
        if (not run_scope or request.method != "GET" or credentialed(request)
                or any(x in request_control for x in ("no-store", "no-cache", "max-age=0"))
                or "pragma" in request.headers):
            return await dispatch(request)
        key = self.digest(("replay-v1", run_scope, provider, str(request.url), tuple(request.headers.multi_items())))
        async with self.coalesce(key):
            cached = self.cache.get(key)
            if cached and cached[0] > self.clock():
                self.cache.move_to_end(key)
                if ledger is not None:
                    ledger.record_cache_hit()
                return httpx.Response(200, headers=cached[1], content=cached[2],
                                      extensions={"spider_replayed": True})
            self.cache.pop(key, None)
            response = await dispatch(request)
            control = response.headers.get("cache-control", "").casefold()
            age_match = re.search(r"(?:^|,)\s*max-age\s*=\s*(\d+)", control)
            ttl = min(30, int(age_match[1])) if age_match else 30
            age = response.headers.get("age", "0")
            ttl = max(0, ttl - int(age)) if age.isdigit() else 0
            if (response.status_code == 200 and ttl and len(response.content) <= 65536
                    and "set-cookie" not in response.headers and "*" not in response.headers.get("vary", "")
                    and not any(x in control for x in ("no-store", "no-cache", "private"))):
                # response.content is decoded; do not decode gzip a second time on replay.
                headers = [(k, v) for k, v in response.headers.multi_items()
                           if k not in {"content-encoding", "content-length", "transfer-encoding"}]
                self.cache[key] = (self.clock() + ttl, headers, response.content)
                while len(self.cache) > 128:
                    self.cache.popitem(last=False)
            return response

    async def aclose(self):
        self.closed = True
        await asyncio.gather(*(pool.aclose() for pool in self.pools.values()))
        self.pools.clear()
        self.cache.clear()
