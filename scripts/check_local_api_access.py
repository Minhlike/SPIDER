"""Opt-in real-account check. Never auto-loaded by SPIDER or pytest.

Only fixed status fields reach stdout. Secrets enter a short-lived child process;
the normal settings/vault, API logs and raw provider responses stay untouched.
"""
import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def load_local_env(path):
    from spider.providers.uncover.api_access import FIELDS
    values = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        name, sep, value = line.partition("=")
        name = name.strip()
        if not sep or name not in FIELDS:
            continue
        value = value.strip()
        if value[:1] in ("'", '"'):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError("Invalid local credential file")
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].rstrip()
        if name in values or any(c in value for c in "\r\n\0"):
            raise ValueError("Invalid local credential file")
        values[name] = value
    return values


def child(search):
    logging.disable(logging.CRITICAL)
    from fastapi.testclient import TestClient
    from spider.web.api import settings
    from spider.web.app import create_app
    from spider.providers.uncover import api_access as access
    from spider.providers.uncover.adapter import UncoverAdapter
    from spider.models.observable import NormalizedObservable
    from spider.models.enums import ObservableType
    keys = {name: os.environ.pop(name, "") for name in access.FIELDS}
    output = {"schema": {name: bool(value) for name, value in keys.items()}, "engines": {}}
    with tempfile.TemporaryDirectory(prefix="spider-api-check-", dir=ROOT / "runtime") as directory:
        settings.SETTINGS_FILE = Path(directory) / "settings.json"
        client = TestClient(create_app(), base_url="http://127.0.0.1:8765")
        response = client.post("/api/settings", json={"api_keys": keys})
        if response.status_code != 200 or access.contains_secret(response.text, keys):
            raise RuntimeError("Protected save check failed")
        output["dpapi_roundtrip"] = all(settings.load_settings()["api_keys"].get(k) == v for k, v in keys.items())
        output["public_files_clean"] = all(not access.contains_secret(p.read_bytes().decode(errors="replace"), keys)
                                           for p in Path(directory).iterdir() if p.is_file())
        for engine in access.REQUIREMENTS:
            response = client.post(f"/api/settings/test/{engine}")
            if response.status_code != 200 or access.contains_secret(response.text, keys):
                raise RuntimeError("Protected connection check failed")
            result = response.json()
            record = {"account": {k: result[k] for k in ("state", "reason", "scope", "http_status") if k in result}}
            if search and result["state"] in ("VALID", "PLAN/QUOTA_LIMIT"):
                target = NormalizedObservable(type=ObservableType.DOMAIN, value="example.org")
                result = asyncio.run(access.run_engine(engine, keys, mode="search", limit=1,
                                                        query=UncoverAdapter.query_for(target, engine)))
                record["search"] = {k: result[k] for k in ("state", "reason", "scope", "http_status") if k in result}
                record["search"]["result_count"] = len(result["results"])
            output["engines"][engine] = record
        if access.contains_secret(json.dumps(output), keys):
            raise RuntimeError("Unsafe test summary")
        print(json.dumps(output, ensure_ascii=True))
    keys.clear()


def main():
    parser = argparse.ArgumentParser(description="Local credential checks without starting SPIDER")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env.local")
    parser.add_argument("--search", action="store_true", help="Also make at most one bounded search request per eligible engine")
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child:
        child(args.search)
        return
    from spider.providers.uncover.api_access import contains_secret
    keys = load_local_env(args.env_file)
    allowed = {"SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PATH"}
    env = {k: v for k, v in os.environ.items() if k.upper() in allowed}
    env.update(keys)
    command = [sys.executable, str(Path(__file__).resolve()), "--child"]
    if args.search:
        command.append("--search")
    try:
        result = subprocess.run(command, env=env, cwd=ROOT, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=155, check=False)
    finally:
        env.clear()
    if result.returncode != 0 or contains_secret(result.stdout.decode(errors="replace"), keys):
        raise RuntimeError("Local account check did not complete safely")
    data = json.loads(result.stdout)
    print(json.dumps(data, ensure_ascii=True, indent=2))
    keys.clear()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Tracebacks from credential parsers, HTTP libraries or children are never printed.
        print('{"status":"CHECK_FAILED","detail":"Local test failed; no diagnostics containing credentials were retained."}')
        sys.exit(1)
