import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from spider.core.factory import create_spider_service
from spider.service.service import SpiderService
from spider.web.events import event_broker
from spider.web.api.cases import router as cases_router
from spider.web.api.investigate import router as investigate_router
from spider.web.api.graph import router as graph_router
from spider.web.api.explain import router as explain_router
from spider.web.api.providers import router as providers_router
from spider.models.classifier import TargetClassifier

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
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

def get_service(request: Request) -> SpiderService:
    if hasattr(request.app.state, "service") and request.app.state.service:
        return request.app.state.service
    # Fallback for direct unit test calls outside lifespan
    service = create_spider_service(mode="production")
    return service

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize single long-lived production service instance
    service = create_spider_service(mode="production")
    await service.start()
    app.state.service = service
    try:
        yield
    finally:
        await service.stop()

def create_app() -> FastAPI:
    app = FastAPI(
        title="SPIDER — Evidence-First OSINT Orchestration Engine",
        description="Local Web UI & REST API for SPIDER OSINT Platform",
        version="2.0.0",
        lifespan=lifespan,
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

    # Target Classifier Endpoint
    @app.post("/api/classify")
    async def classify_target(payload: dict):
        raw = payload.get("target", "")
        res = TargetClassifier.classify(raw)
        return {
            "target": raw,
            "detected_type": res.detected_type.value,
            "confidence": res.confidence,
            "canonical_value": res.canonical_value,
            "candidate_types": [t.value for t in res.candidate_types]
        }

    # API Routers
    app.include_router(cases_router, prefix="/api")
    app.include_router(investigate_router, prefix="/api")
    app.include_router(graph_router, prefix="/api")
    app.include_router(explain_router, prefix="/api")
    app.include_router(providers_router, prefix="/api")

    # Health Check
    @app.get("/api/health")
    async def health_check(request: Request):
        srv = get_service(request)
        is_temp = False
        if not srv.db_manager:
            await srv.start()
            is_temp = True
        try:
            diag = await srv.doctor()
            return diag
        finally:
            if is_temp:
                await srv.stop()

    # WebSocket Real-Time Events
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await event_broker.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
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
        return HTMLResponse(content="<h1>SPIDER Backend Ready</h1>")

    return app
