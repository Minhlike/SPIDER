import json
from copy import deepcopy
from threading import RLock
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, SecretStr
from typing import Dict, Any, Optional, Literal
from spider.storage.key_store import LocalKeyStore, KeyStoreError, atomic_write

router = APIRouter(prefix="/settings", tags=["Settings"])

SETTINGS_FILE = Path("data/settings.json")
SETTINGS_LOCK = RLock()
KeyName = Literal["shodan", "censys_id", "censys_secret", "securitytrails", "virustotal",
                  "SHODAN", "CENSYS", "FOFA"]

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
        "uncover": True
    },
    "api_keys": {
        "shodan": "",
        "censys_id": "",
        "censys_secret": "",
        "securitytrails": "",
        "virustotal": ""
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
            merged["api_keys"].update(keys)
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

@router.get("", response_model=Dict[str, Any])
async def get_settings():
    curr = load_settings()
    # Mask API keys before sending to client
    masked_keys = {}
    for k, v in curr.get("api_keys", {}).items():
        masked_keys[k] = "********" if v and v.strip() else ""
    
    res = curr.copy()
    res["api_keys"] = masked_keys
    res["default_policy_profile"] = curr.get("default_profile", "passive_standard")
    return res

@router.post("", response_model=Dict[str, Any])
async def update_settings(req: UpdateSettingsRequest):
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

    save_settings(curr)
    
    # Return masked
    masked_keys = {}
    for k, v in curr.get("api_keys", {}).items():
        masked_keys[k] = "********" if v and v.strip() else ""
    res = curr.copy()
    res["api_keys"] = masked_keys
    res["default_policy_profile"] = curr.get("default_profile", "passive_standard")
    res["status"] = "SAVED"
    return res
