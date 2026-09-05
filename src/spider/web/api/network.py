"""Small local-only network identity endpoints used by the target form."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException

from spider.providers.whatismyip.adapter import fetch_public_address, saved_api_key

router = APIRouter(prefix="/network", tags=["Network"])
_cache: dict[int, tuple[float, dict]] = {}
_locks = {4: asyncio.Lock(), 6: asyncio.Lock()}


async def resolve_public_address(version: int) -> dict:
    now = time.monotonic()
    cached = _cache.get(version)
    if cached and now - cached[0] < 60:
        return {**cached[1], "cached": True}
    async with _locks[version]:
        cached = _cache.get(version)
        if cached and time.monotonic() - cached[0] < 60:
            return {**cached[1], "cached": True}
        key = saved_api_key()
        try:
            result = await fetch_public_address(key, version=version)
        except ValueError as exc:
            reason = str(exc) if str(exc) in {
                "MISSING_CREDENTIAL", "INVALID_KEY", "DISABLED_KEY", "QUOTA_LIMIT",
                "PUBLIC_ADDRESS_UNAVAILABLE", "NETWORK_ERROR", "PARSER_DRIFT",
            } else "NETWORK_ERROR"
            raise HTTPException(status_code=503, detail={
                "code": reason,
                "message": "Public IP address is unavailable",
            }) from None
        payload = {
            **result,
            "source": "whatismyip_api",
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "cached": False,
        }
        _cache[version] = (time.monotonic(), payload)
        return payload


@router.get("/public-address")
async def public_address(version: int = 4):
    if version not in (4, 6):
        raise HTTPException(status_code=422, detail={
            "code": "INVALID_IP_VERSION", "message": "IP version must be 4 or 6"})
    return await resolve_public_address(version)
