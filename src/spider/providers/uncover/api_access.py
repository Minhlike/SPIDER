"""Credential schema and the private Uncover process boundary.

No dotenv auto-loading, plaintext provider config, global environment mutation,
or provider diagnostics may cross this boundary.
"""
import asyncio
import base64
import hashlib
import ipaddress
import json
import os
import re
from pathlib import Path
from typing import Mapping
from urllib.parse import quote, quote_plus, urlsplit, urlunsplit

REQUIREMENTS = {
    "shodan": ("SHODAN_API_KEY",),
    # Censys Free accounts authenticate with a PAT; an organization is optional.
    "censys": ("CENSYS_API_TOKEN",),
    # FOFA's current account endpoint and API authenticate with the key alone.
    "fofa": ("FOFA_KEY",),
}
OPTIONAL_FIELDS = {"censys": ("CENSYS_ORGANIZATION_ID",), "fofa": ("FOFA_EMAIL",)}
FIELDS = tuple(dict.fromkeys(
    field for names in (*REQUIREMENTS.values(), *OPTIONAL_FIELDS.values()) for field in names
))
STATES = {"VALID", "MISSING_CREDENTIAL", "INVALID_CREDENTIAL", "PLAN/QUOTA_LIMIT", "NETWORK_ERROR",
          "VALID_FREE_PLAN", "INVALID_TOKEN", "NO_SEARCH_ENTITLEMENT", "QUOTA_LIMIT", "RATE_LIMIT",
          "KEY_VALID", "NO_QUERY_ENTITLEMENT", "INVALID_KEY"}
REASONS = {
    "AUTH_REJECTED", "PLAN_OR_QUOTA", "PERMISSION_DENIED", "HTTP_ERROR",
    "UNEXPECTED_RESPONSE", "PROVIDER_ERROR_UNCLASSIFIED", "REQUEST_ACCEPTED",
    "DESTINATION_BLOCKED", "CONNECTION_FAILED", "MALFORMED_CREDENTIAL",
    "ORGANIZATION_REJECTED", "NO_QUERY_CREDITS", "EMAIL_MISMATCH",
    "ACCOUNT_VERIFIED_SEARCH_NOT_TESTED", "SEARCH_VERIFIED", "TIMEOUT",
    "REQUIRED_FIELDS_MISSING", "RUNTIME_UNAVAILABLE", "NOT_REQUESTED", "PAGE_LIMIT",
    "ACCOUNT_VERIFIED", "ACCOUNT_EMAIL_MISMATCH", "NO_QUERY_CREDITS",
}
ROOT = Path(__file__).resolve().parents[4]
PRIVATE_BINARY = ROOT / "runtime/uncover/uncover-private.exe"


def canonical_keys(values: Mapping[str, str]) -> dict[str, str]:
    result = {k: str(v).strip() for k, v in values.items() if isinstance(v, str)}
    # Only unambiguous aliases migrate. Legacy Censys ID/secret is NOT a PAT/org pair.
    for old in ("SHODAN", "shodan"):
        if "SHODAN_API_KEY" not in result and result.get(old):
            result["SHODAN_API_KEY"] = result[old]
    censys = result.get("CENSYS", "")
    if censys.count(":") == 1 and all(censys.split(":")):
        token, organization = censys.split(":")
        result.setdefault("CENSYS_API_TOKEN", token)
        result.setdefault("CENSYS_ORGANIZATION_ID", organization)
    fofa = result.get("FOFA", "")
    if fofa.count(":") == 1 and all(fofa.split(":")):
        email, key = fofa.split(":")
        result.setdefault("FOFA_EMAIL", email)
        result.setdefault("FOFA_KEY", key)
    elif fofa:
        result.setdefault("FOFA_KEY", fofa)
    return result


def saved_keys() -> dict[str, str]:
    # Settings owns the single lock, migration and vault path (also isolated in tests).
    from spider.web.api.settings import load_settings
    return canonical_keys(load_settings()["api_keys"])


def effective_keys(saved: Mapping[str, str], environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """A saved engine bundle wins as a whole; never mix two accounts' fields.

    An explicitly emptied saved bundle disables environment fallback for that engine.
    Environment-only credentials are for explicitly launched CLI/test processes.
    """
    env = os.environ if environ is None else environ
    stored = canonical_keys(saved)
    result = {}
    for names in REQUIREMENTS.values():
        source = stored if any(name in stored for name in names) else env
        result.update({name: source.get(name, "").strip() for name in names})
    for engine, names in OPTIONAL_FIELDS.items():
        source = stored if any(name in stored for name in REQUIREMENTS[engine]) else env
        result.update({name: source.get(name, "").strip() for name in names})
    return result


def engine_presence(keys: Mapping[str, str]) -> dict:
    return {engine: {"configured": all(bool(keys.get(name)) for name in names),
                     "missing_fields": [name for name in names if not keys.get(name)],
                     "optional_fields": [name for name in OPTIONAL_FIELDS.get(engine, ()) if not keys.get(name)]}
            for engine, names in REQUIREMENTS.items()}


def child_environment(engine: str, keys: Mapping[str, str]) -> dict[str, str]:
    # No inherited provider credentials, proxies, SSL overrides or diagnostic switches.
    allowed = {"SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA"}
    env = {k: v for k, v in os.environ.items() if k.upper() in allowed}
    env.update({name: keys[name] for name in REQUIREMENTS[engine] + OPTIONAL_FIELDS.get(engine, ()) if keys.get(name)})
    env["GOTRACEBACK"] = "none"
    return env


def verified_runtime(binary: Path = PRIVATE_BINARY) -> bool:
    try:
        manifest = json.loads(binary.with_name("build.json").read_text(encoding="utf-8"))
        return (manifest.get("revision") == "3f7b74af20b24a7d5477d1dc77f6ba881219b0de"
                and hashlib.sha256(binary.read_bytes()).hexdigest() == manifest["sha256"]
                and hashlib.sha256((ROOT / "tools/uncover_bridge/main.go").read_bytes()).hexdigest()
                == manifest["bridge_sha256"]
                and hashlib.sha256((ROOT / "scripts/build_uncover_bridge.py").read_bytes()).hexdigest()
                == manifest["builder_sha256"])
    except (OSError, ValueError, KeyError):
        return False


def result_state(engine: str, state: str, reason: str, scope: str = "account") -> dict:
    return {"engine": engine, "state": state, "reason": reason, "scope": scope, "results": []}


def contains_secret(text: str, keys: Mapping[str, str]) -> bool:
    lowered = text.casefold()
    for secret in keys.values():
        if not secret:
            continue
        variants = (secret, quote(secret, safe=""), quote_plus(secret),
                    base64.b64encode(secret.encode()).decode(), json.dumps(secret)[1:-1])
        if any(v.casefold() in lowered for v in variants):
            return True
    return False


def clean_rows(rows, keys: Mapping[str, str]) -> list[dict]:
    clean = []
    if not isinstance(rows, list):
        return clean
    for row in rows[:100]:
        if not isinstance(row, dict) or contains_secret(json.dumps(row), keys):
            continue
        item = {"engine": row.get("engine") if row.get("engine") in REQUIREMENTS else "uncover"}
        try:
            if isinstance(row.get("ip"), str):
                item["ip"] = str(ipaddress.ip_address(row["ip"]))
        except ValueError:
            pass
        host = row.get("host", "")
        if isinstance(host, str) and re.fullmatch(r"[a-zA-Z0-9_.-]{1,253}", host):
            item["host"] = host
        address = row.get("url", "")
        if isinstance(address, str) and len(address) <= 2048:
            try:
                parsed = urlsplit(address)
                if parsed.scheme in ("http", "https") and parsed.hostname and not parsed.username:
                    item["url"] = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
            except ValueError:
                pass
        if any(name in item for name in ("ip", "host", "url")):
            clean.append(item)
    return clean


async def run_engine(engine: str, keys: Mapping[str, str], *, mode: str = "check", query: str = "",
                     limit: int = 10, binary: Path = PRIVATE_BINARY, timeout: float = 23) -> dict:
    scope = "account" if mode == "check" else "search"
    if engine not in REQUIREMENTS or mode not in ("check", "search"):
        raise ValueError("Unsupported Uncover operation")
    if not engine_presence(keys)[engine]["configured"]:
        return result_state(engine, "MISSING_CREDENTIAL", "REQUIRED_FIELDS_MISSING", scope)
    if not verified_runtime(binary):
        return result_state(engine, "NETWORK_ERROR", "RUNTIME_UNAVAILABLE", scope)
    command = [str(binary.resolve()), "-engine", engine, "-mode", mode, "-limit", str(max(1, min(limit, 100)))]
    if mode == "search":
        command += ["-q", query]
    env = child_environment(engine, keys)
    process = None
    try:
        try:
            process = await asyncio.create_subprocess_exec(*command, env=env, cwd=str(ROOT),
                stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL)
        finally:
            env.clear()
        async def collect():
            content = bytearray()
            while chunk := await process.stdout.read(16384):
                content.extend(chunk)
                if len(content) > 256 * 1024:
                    raise ValueError("Invalid runner response")
            await process.wait()
            return bytes(content)
        raw = await asyncio.wait_for(collect(), timeout=timeout)
        if process.returncode != 0 or contains_secret(raw.decode(errors="replace"), keys):
            return result_state(engine, "NETWORK_ERROR", "UNEXPECTED_RESPONSE", scope)
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get("state") not in STATES or data.get("reason") not in REASONS:
            return result_state(engine, "NETWORK_ERROR", "UNEXPECTED_RESPONSE", scope)
        result = result_state(engine, data["state"], data["reason"], scope)
        status = data.get("http_status")
        if isinstance(status, int) and 100 <= status <= 599:
            result["http_status"] = status
        result["results"] = clean_rows(data.get("results", []), keys)
        if data.get("warning") == "ACCOUNT_EMAIL_MISMATCH":
            result["warning"] = "ACCOUNT_EMAIL_MISMATCH"
        return result
    except asyncio.TimeoutError:
        return result_state(engine, "NETWORK_ERROR", "TIMEOUT", scope)
    except (OSError, ValueError, TypeError):
        return result_state(engine, "NETWORK_ERROR", "UNEXPECTED_RESPONSE", scope)
    finally:
        env.clear()
        if process and process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()
