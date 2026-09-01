from fastapi import APIRouter, Depends
from typing import Dict, Any, List
from spider.cli.main import get_service

router = APIRouter(prefix="/providers", tags=["Providers"])

@router.get("", response_model=List[Dict[str, Any]])
async def list_providers():
    service = get_service()
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
            "health_message": h.get("message", "OK"),
            "health_details": h.get("details", {})
        })
    return result
