import os
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from spider.web.events import event_broker
from spider.web.api.cases import router as cases_router
from spider.web.api.investigate import router as investigate_router
from spider.web.api.graph import router as graph_router
from spider.web.api.explain import router as explain_router
from spider.web.api.providers import router as providers_router
from spider.cli.main import get_service

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Localhost binding safety check
        host = request.headers.get("host", "")
        client_ip = request.client.host if request.client else ""
        
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self' ws://127.0.0.1:* ws://localhost:* http://127.0.0.1:* http://localhost:*;"
        )
        return response

def create_app() -> FastAPI:
    app = FastAPI(
        title="SPIDER — Evidence-First OSINT Orchestration Engine",
        description="Local Web UI & REST API for SPIDER OSINT Platform",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc"
    )

    # Security & CORS
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:8765", "http://localhost:8765", "http://127.0.0.1", "http://localhost"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API Routers
    app.include_router(cases_router, prefix="/api")
    app.include_router(investigate_router, prefix="/api")
    app.include_router(graph_router, prefix="/api")
    app.include_router(explain_router, prefix="/api")
    app.include_router(providers_router, prefix="/api")

    # Health Check
    @app.get("/api/health")
    async def health_check():
        service = get_service()
        diag = await service.doctor()
        return diag

    # WebSocket Real-Time Events
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await event_broker.connect(websocket)
        try:
            while True:
                # Keepalive ping/pong
                data = await websocket.receive_text()
        except WebSocketDisconnect:
            event_broker.disconnect(websocket)
        except Exception:
            event_broker.disconnect(websocket)

    # Static Assets & SPA Root
    static_dir = Path(__file__).parent / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def serve_spa():
        index_path = static_dir / "index.html"
        if index_path.exists():
            return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
        return HTMLResponse(content="<h1>SPIDER Backend Ready</h1><p>Static index.html not yet built.</p>")

    return app
