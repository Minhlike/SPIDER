import os
import time
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import BackgroundTasks, FastAPI, WebSocket, WebSocketDisconnect, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from starlette.middleware.base import BaseHTTPMiddleware

from spider.core.factory import create_spider_service
from spider.service.service import SpiderService
from spider.web.events import event_broker
from spider.web.api.cases import router as cases_router
from spider.web.api.investigate import router as investigate_router
from spider.web.api.graph import router as graph_router
from spider.web.api.explain import router as explain_router
from spider.web.api.providers import router as providers_router
from spider.web.api.settings import router as settings_router
from spider.web.api.network import router as network_router
from spider.web.api.settings import load_settings
from spider.storage.key_store import KeyStoreError
from spider.models.classifier import TargetClassifier
from spider.web.security import LocalAccessMiddleware
from spider.service.investigation_api import input_catalogue
from spider.capability.applicability import assess_provider
from spider.capability.scopes import capability_allowed, resolve_investigation_mode


def source_preflight(service: SpiderService, observable_type, requested_mode=None, browser_assisted=False):
    mode = resolve_investigation_mode([observable_type], requested_mode)
    sources = []
    for capability in service.capability_registry.get_capabilities_for_input(observable_type):
        if not capability_allowed(mode, observable_type, capability.name):
            continue
        if capability.name == "BROWSER_PERSONAL_DISCOVERY" and not browser_assisted:
            continue
        for provider_id in capability.default_providers:
            adapter = service.provider_manager.get_adapter(provider_id)
            if adapter is None:
                continue
            decision = assess_provider(adapter, observable_type, capability.name)
            sources.append({
                "provider_id": provider_id,
                "capability": capability.name,
                "network_class": adapter.network_class().value,
                "request_accounting": "SUPPORTED" if adapter.request_budget_supported else "UNMETERED_BLOCKED",
                "credential_scope": ("INTERNET_ASSET" if provider_id == "uncover"
                                     else "IP_ENRICHMENT" if provider_id == "whatismyip"
                                     else "SIGNED_IN_BROWSER_SESSION" if provider_id == "coccoc_browser"
                                     else "NOT_REQUIRED"),
                "identifier_disclosure": ("SHA256_EMAIL" if provider_id == "gravatar_public"
                                          else "RAW_TARGET"),
                "applicability": "APPLICABLE" if decision.applicable else "NOT_APPLICABLE",
                "applicability_reason": decision.reason,
            })
    # A provider may implement several matching capabilities but executes once per observable.
    unique = {}
    for item in sources:
        existing = unique.get(item["provider_id"])
        if existing is None or (item["applicability"] == "APPLICABLE" and
                                existing["applicability"] != "APPLICABLE"):
            unique[item["provider_id"]] = item
    return {
        "investigation_mode": mode.value,
        "sources": list(unique.values()),
        "internet_api_keys_applicable": any(item["provider_id"] == "uncover" and
                                             item["applicability"] == "APPLICABLE"
                                             for item in unique.values()),
    }

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        if request.url.path.startswith("/api/settings"):
            response.headers["Cache-Control"] = "no-store"
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
    if not hasattr(request.app.state, "_fallback_service"):
        srv = create_spider_service(mode="production")
        request.app.state._fallback_service = srv
    return request.app.state._fallback_service


def _signal_launcher_shutdown(state):
    # BackgroundTasks runs after the HTTP response has been sent.
    time.sleep(0.15)
    from spider.launcher import signal_stop
    signal_stop(state)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Migrate legacy keys before the web service can accept requests; fail closed.
    load_settings()
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
    @app.exception_handler(KeyStoreError)
    async def protected_settings_error(request, exc):
        return JSONResponse(status_code=503, content={"detail": str(KeyStoreError())})

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        if request.url.path.startswith("/api/settings"):
            # FastAPI's default validation response includes the rejected input.
            return JSONResponse(status_code=422, content={"detail": "Invalid settings request"})
        return await request_validation_exception_handler(request, exc)

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:8765", "http://localhost:8765", "http://127.0.0.1", "http://localhost"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(LocalAccessMiddleware)

    @app.get("/api/input-catalogue")
    async def supported_inputs(request: Request):
        return {"inputs": input_catalogue(get_service(request))}

    # Target Classifier Endpoint (supports both GET and POST)
    @app.api_route("/api/classify", methods=["GET", "POST"])
    async def classify_target(request: Request):
        from spider.models.classifier import ClassificationError
        from fastapi import HTTPException
        try:
            payload = await request.json() if request.method == "POST" else request.query_params
            if not hasattr(payload, "get"):
                raise ValueError("Expected an object.")
            raw = payload.get("target", "")
            res = TargetClassifier.classify(raw, payload.get("target_type"))
        except ClassificationError as exc:
            raise HTTPException(status_code=422, detail=exc.detail()) from None
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail={"code": "invalid_target", "message": "Invalid classification request."}) from None
        try:
            preflight = source_preflight(
                get_service(request), res.detected_type, payload.get("investigation_mode"),
                bool(payload.get("browser_assisted", False)),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={
                "code": "incompatible_investigation_mode",
                "message": str(exc),
            }) from None
        return {**res.model_dump(mode="json"), "target": raw, "type": res.detected_type.value,
                "source_preflight": preflight}

    # API Routers
    app.include_router(cases_router, prefix="/api")
    app.include_router(investigate_router, prefix="/api")
    app.include_router(graph_router, prefix="/api")
    app.include_router(explain_router, prefix="/api")
    app.include_router(providers_router, prefix="/api")
    app.include_router(settings_router, prefix="/api")
    app.include_router(network_router, prefix="/api")

    # Health Check
    @app.get("/api/health")
    async def health_check(request: Request, ready: bool = False):
        srv = get_service(request)
        if ready:
            # Launcher readiness must not wait on optional provider subprocesses/network.
            from sqlalchemy import text
            if not srv.is_running:
                return JSONResponse(status_code=503, content={"status": "STARTING"})
            async with srv.db_manager.session_factory() as session:
                await session.execute(text("SELECT 1"))
            return {"status": "HEALTHY", "database_connected": True, "pid": os.getpid()}
        is_temp = False
        if not srv.is_running:
            await srv.start()
            is_temp = True
        try:
            diag = await srv.doctor()
            return diag
        finally:
            if is_temp:
                await srv.stop()

    @app.post("/api/system/shutdown", status_code=202)
    async def shutdown_app(background_tasks: BackgroundTasks):
        from fastapi import HTTPException
        from spider.launcher import read_state
        state = read_state()
        if not state or state.get("pid") != os.getpid():
            raise HTTPException(status_code=409, detail=(
                "SPIDER is not controlled by the verified project launcher; no process was stopped."
            ))
        background_tasks.add_task(_signal_launcher_shutdown, state)
        return {"status": "SHUTDOWN_REQUESTED", "pid": state["pid"]}

    # WebSocket Real-Time Events
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await event_broker.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
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
