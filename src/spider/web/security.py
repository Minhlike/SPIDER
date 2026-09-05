"""Guard the complete local HTTP/WS boundary, before routers or CORS."""
from urllib.parse import urlsplit
from starlette.responses import JSONResponse

ALLOWED_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def authority(value, scheme):
    try:
        parsed = urlsplit(f"{scheme}://{value}")
        if (not parsed.hostname or parsed.username is not None or parsed.password is not None
                or parsed.path or parsed.query or parsed.fragment or any(c.isspace() for c in value)):
            return None
        return parsed.hostname.lower(), parsed.port or (443 if scheme == "https" else 80)
    except ValueError:
        return None


class LocalAccessMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        headers = {}
        duplicate = False
        for key, value in scope.get("headers", []):
            key = key.lower()
            if key in (b"host", b"origin", b"sec-fetch-site") and key in headers:
                duplicate = True
            headers[key] = value.decode("latin1")
        scheme = "https" if scope.get("scheme") in ("https", "wss") else "http"
        host = authority(headers.get(b"host", ""), scheme)
        allowed = not duplicate and host is not None and host[0] in ALLOWED_HOSTS
        origin = headers.get(b"origin")
        if origin is not None:
            prefix = scheme + "://"
            allowed = allowed and origin.startswith(prefix) and authority(origin[len(prefix):], scheme) == host
        # Browsers always send Origin in a websocket handshake. CLI HTTP can omit it.
        if scope["type"] == "websocket" and origin is None:
            allowed = False
        if headers.get(b"sec-fetch-site", "none").lower() not in ("same-origin", "none"):
            allowed = False
        if not allowed:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            else:
                await JSONResponse({"detail": "Local same-origin access required"}, status_code=403)(scope, receive, send)
            return
        await self.app(scope, receive, send)
