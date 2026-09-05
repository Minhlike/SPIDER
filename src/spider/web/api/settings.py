import json
from copy import deepcopy
from threading import RLock
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, Field, SecretStr
from typing import Dict, Any, Optional, Literal
from spider.storage.key_store import LocalKeyStore, KeyStoreError, atomic_write
from spider.providers.uncover.api_access import canonical_keys, engine_presence, REQUIREMENTS, OPTIONAL_FIELDS
from urllib.parse import urlsplit
from datetime import datetime, timezone
import hashlib
import hmac
import secrets
import time
from threading import Lock

ALLOWED_SETTINGS_HOSTS = {"127.0.0.1", "localhost", "::1"}


async def local_settings_request(request: Request):
    # CORS alone cannot prevent forged writes or DNS rebinding against localhost.
    if request.url.hostname not in ALLOWED_SETTINGS_HOSTS:
        raise HTTPException(403, "Local settings access required")
    origin = request.headers.get("origin")
    if origin and origin != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "Same-origin settings access required")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "Same-origin settings access required")

router = APIRouter(prefix="/settings", tags=["Settings"], dependencies=[Depends(local_settings_request)])

SETTINGS_FILE = Path("data/settings.json")
SETTINGS_LOCK = RLock()
KeyName = Literal["shodan", "censys_id", "censys_secret", "securitytrails", "virustotal",
                  "SHODAN", "CENSYS", "FOFA", "SHODAN_API_KEY", "CENSYS_API_TOKEN",
                  "CENSYS_ORGANIZATION_ID", "FOFA_EMAIL", "FOFA_KEY",
                  "WHATISMYIP_API_KEY"]

ALL_REQUIREMENTS = {**REQUIREMENTS, "whatismyip": ("WHATISMYIP_API_KEY",)}
ALL_OPTIONAL_FIELDS = {**OPTIONAL_FIELDS, "whatismyip": ()}

DEFAULT_SETTINGS: Dict[str, Any] = {
    "language": "vi",
    "theme": "light",
    "default_profile": "passive_standard",
    "max_depth": 2,
    "max_entities": 250,
    "timeout_seconds": 25,
    "concurrency": 4,
    "enabled_providers": {
        "native_dns": True,
        "native_rdap": True,
        "native_ct": True,
        "subfinder": True,
        "metabigor": True,
        "spiderfoot": True,
        "maigret": True,
        "uncover": True,
        "whatismyip": True
    },
    "api_keys": {
        "shodan": "",
        "censys_id": "",
        "censys_secret": "",
        "securitytrails": "",
        "virustotal": "",
        "WHATISMYIP_API_KEY": ""
    }
}

def load_settings() -> Dict[str, Any]:
    with SETTINGS_LOCK:
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8")) if SETTINGS_FILE.exists() else {}
            merged = deepcopy(DEFAULT_SETTINGS)
            merged.update({k: v for k, v in data.items() if k in DEFAULT_SETTINGS and k != "api_keys"})
            store = LocalKeyStore(SETTINGS_FILE.with_name("api-keys.dpapi"))
            keys = store.load()
            legacy = data.get("api_keys", {})
            if legacy:
                # Persist and verify encrypted data BEFORE removing the legacy plaintext.
                keys.update({k: v for k, v in legacy.items() if v and v != "********"})
                if keys:
                    store.save(keys)
            normalized = canonical_keys(keys)
            if normalized != keys:
                store.save(normalized)
            merged["api_keys"].update(normalized)
            if "api_keys" in data or not SETTINGS_FILE.exists():
                _save_public(merged)
            return merged
        except Exception:
            raise KeyStoreError() from None


def _save_public(data: Dict[str, Any]) -> None:
    public = {k: v for k, v in data.items() if k in DEFAULT_SETTINGS and k != "api_keys"}
    atomic_write(SETTINGS_FILE, json.dumps(public, indent=2).encode("utf-8"))

def save_settings(data: Dict[str, Any]) -> None:
    with SETTINGS_LOCK:
        try:
            LocalKeyStore(SETTINGS_FILE.with_name("api-keys.dpapi")).save(data.get("api_keys", {}))
            _save_public(data)
        except Exception:
            raise KeyStoreError() from None

class UpdateSettingsRequest(BaseModel):
    language: Optional[str] = None
    theme: Optional[str] = None
    default_profile: Optional[str] = None
    default_policy_profile: Optional[str] = None
    max_depth: Optional[int] = None
    max_entities: Optional[int] = None
    timeout_seconds: Optional[int] = None
    concurrency: Optional[int] = None
    enabled_providers: Optional[Dict[str, bool]] = None
    api_keys: Optional[Dict[KeyName, SecretStr]] = Field(default=None, repr=False)


class CheckCache:
    """Bounded, private cache; changing either field invalidates prior authentication."""
    def __init__(self):
        self.salt = secrets.token_bytes(32)
        self.entries = {}
        self.locks = {engine: Lock() for engine in ALL_REQUIREMENTS}

    def fingerprint(self, engine, keys):
        fields = ALL_REQUIREMENTS[engine] + tuple(ALL_OPTIONAL_FIELDS.get(engine, ()))
        value = json.dumps([str(SETTINGS_FILE.resolve()), *[keys.get(k, "") for k in fields]])
        return hmac.new(self.salt, value.encode(), hashlib.sha256).digest()

    def recent(self, engine, keys, max_age=120):
        entry = self.entries.get(engine)
        if entry and entry[0] == self.fingerprint(engine, keys) and time.monotonic() - entry[1] < max_age:
            return {**entry[2], "cached": True}
        return None


CHECK_CACHE = CheckCache()


def public_settings(curr):
    result = curr.copy()
    result["api_keys"] = {k: "********" if v and v.strip() else "" for k, v in curr["api_keys"].items()}
    keys = canonical_keys(curr["api_keys"])
    result["credential_status"] = engine_presence(keys)
    result["credential_status"]["whatismyip"] = {
        "configured": bool(keys.get("WHATISMYIP_API_KEY")),
        "missing_fields": ([] if keys.get("WHATISMYIP_API_KEY") else ["WHATISMYIP_API_KEY"]),
        "optional_fields": [],
    }
    for engine, status in result["credential_status"].items():
        status["test"] = CHECK_CACHE.recent(engine, keys)
    result["default_policy_profile"] = curr.get("default_profile", "passive_standard")
    return result

@router.get("", response_model=Dict[str, Any])
async def get_settings():
    return public_settings(load_settings())

@router.post("", response_model=Dict[str, Any])
def update_settings(req: UpdateSettingsRequest):
    with SETTINGS_LOCK:
        return _update_settings(req)


def _update_settings(req: UpdateSettingsRequest):
    curr = load_settings()
    if req.language:
        curr["language"] = "vi" if req.language.lower() == "vi" else "en"
    if req.theme:
        curr["theme"] = "dark" if req.theme.lower() == "dark" else "light"
    if req.default_policy_profile:
        curr["default_profile"] = req.default_policy_profile
    elif req.default_profile:
        curr["default_profile"] = req.default_profile
    if req.max_depth is not None:
        curr["max_depth"] = max(1, min(5, req.max_depth))
    if req.max_entities is not None:
        curr["max_entities"] = max(10, min(1000, req.max_entities))
    if req.timeout_seconds is not None:
        curr["timeout_seconds"] = max(5, min(120, req.timeout_seconds))
    if req.concurrency is not None:
        curr["concurrency"] = max(1, min(16, req.concurrency))
    if req.enabled_providers:
        curr["enabled_providers"].update(req.enabled_providers)
    if req.api_keys:
        for k, secret in req.api_keys.items():
            v = secret.get_secret_value()
            # If user provided non-masked new key, update it
            if v and v != "********":
                curr["api_keys"][k] = v.strip()
            elif v == "":
                curr["api_keys"][k] = ""
            if v != "********":
                if k in ("SHODAN", "shodan"):
                    curr["api_keys"]["SHODAN_API_KEY"] = v.strip()
                if k in ("CENSYS", "FOFA"):
                    normalized = canonical_keys({k: v})
                    for field in REQUIREMENTS[k.lower()] + tuple(OPTIONAL_FIELDS.get(k.lower(), ())):
                        curr["api_keys"][field] = normalized.get(field, "")
                # Retire superseded aliases so deleted/rotated values cannot reappear.
                aliases = {"SHODAN_API_KEY": ("SHODAN", "shodan"),
                           "CENSYS_API_TOKEN": ("CENSYS", "censys_id", "censys_secret"),
                           "CENSYS_ORGANIZATION_ID": ("CENSYS",), "FOFA_EMAIL": ("FOFA",), "FOFA_KEY": ("FOFA",)}
                for alias in aliases.get(k, ()):
                    curr["api_keys"].pop(alias, None)

    save_settings(curr)
    
    res = public_settings(curr)
    res["status"] = "SAVED"
    return res


@router.post("/test/{engine}")
async def test_engine_access(engine: Literal["shodan", "censys", "fofa", "whatismyip"]):
    from spider.providers.uncover.api_access import run_engine
    keys = canonical_keys(load_settings()["api_keys"])
    cached = CHECK_CACHE.recent(engine, keys, max_age=30)
    if cached:
        return cached
    lock = CHECK_CACHE.locks[engine]
    if not lock.acquire(blocking=False):
        raise HTTPException(409, "A check is already running for this engine")
    try:
        if engine == "whatismyip":
            from spider.providers.whatismyip.adapter import check_api_key
            result = await check_api_key(keys.get("WHATISMYIP_API_KEY", ""))
        else:
            result = await run_engine(engine, keys)
        result.pop("results", None)
        result.update(checked_at=datetime.now(timezone.utc).isoformat(), cached=False)
        # Saving another key while the request is in flight must not show old success.
        if CHECK_CACHE.fingerprint(engine, keys) != CHECK_CACHE.fingerprint(engine, canonical_keys(load_settings()["api_keys"])):
            raise HTTPException(409, "Credentials changed; test the saved values again")
        CHECK_CACHE.entries[engine] = (CHECK_CACHE.fingerprint(engine, keys), time.monotonic(), result)
        return result
    finally:
        lock.release()
        keys.clear()
