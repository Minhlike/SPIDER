from fastapi import APIRouter, Depends, Request
from typing import Dict, Any, List
from spider.service.service import SpiderService

router = APIRouter(prefix="/providers", tags=["Providers"])

def get_srv(request: Request) -> SpiderService:
    from spider.web.app import get_service
    return get_service(request)

@router.get("", response_model=List[Dict[str, Any]])
async def list_providers(service: SpiderService = Depends(get_srv)):
    is_temp = False
    if not service.is_running:
        await service.start()
        is_temp = True
    try:
        adapters = service.provider_manager.list_adapters()
        health_map = await service.check_provider_health()
        
        result = []
        for a in adapters:
            pid = a.provider_id()
            h = health_map.get(pid, {})
            result.append({
                "provider_id": pid,
                "version": a.version(),
                "adapter_version": a.adapter_version(),
                "capabilities": a.capabilities(),
                "network_class": a.network_class().value,
                "accepts": [t.value for t in a.accepts()],
                "produces": [t.value for t in a.produces()],
                "state": h.get("state", "READY"),
                "provider_version": h.get("provider_version") or a.version(),
                "latency_ms": h.get("latency_ms"),
                "health_message": h.get("message", "OK"),
                "health_details": h.get("details", {})
            })
        return result
    finally:
        if is_temp:
            await service.stop()


@router.post("/{provider_id}/test")
async def test_single_provider(provider_id: str, service: SpiderService = Depends(get_srv)):
    from fastapi import HTTPException
    adapter = service.provider_manager.get_adapter(provider_id)
    if not adapter:
        raise HTTPException(status_code=404, detail=f"Provider {provider_id} not found")
    h = await adapter.health()
    return {
        "provider_id": provider_id,
        "state": h.state.value if hasattr(h.state, "value") else str(h.state),
        "version": h.provider_version or adapter.version(),
        "runtime_exists": h.runtime_exists,
        "latency_ms": h.latency_ms,
        "message": h.message,
        "credential_state": h.credential_state
    }
