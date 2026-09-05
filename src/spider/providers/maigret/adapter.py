import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

from spider.providers.base import BaseProviderAdapter, ProviderHealth, ProviderExecutionResult
from spider.models.enums import ObservableType, NetworkClass, ProviderState
from spider.models.observable import NormalizedObservable
from spider.models.observation import Observation
from spider.discovery.vn_sources import DIRECT_MAIGRET_SITES


class MaigretAdapter(BaseProviderAdapter):
    request_budget_supported = True
    def __init__(self, python_exec=None, database_path=None):
        self.python_exec = python_exec or sys.executable
        self.database_path = database_path

    def provider_id(self): return "maigret"
    def version(self): return "v0.6.5"
    def adapter_version(self): return "2.1.0"
    def capabilities(self): return ["USERNAME_DISCOVERY"]
    def network_class(self): return NetworkClass.THIRD_PARTY_ONLY
    def accepts(self): return [ObservableType.USERNAME]
    def produces(self): return [ObservableType.ACCOUNT, ObservableType.URL]

    async def health(self):
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                self.python_exec, "-c",
                "import importlib.metadata; import maigret; print(importlib.metadata.version('maigret'))",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            out, _ = await asyncio.wait_for(proc.communicate(), 15)
            ready = proc.returncode == 0 and out.strip() == b"0.6.5"
            return ProviderHealth(state=ProviderState.READY if ready else ProviderState.MISSING_RUNTIME,
                                  provider_version="0.6.5" if ready else None,
                                  runtime_path=self.python_exec, runtime_exists=ready,
                                  runtime_version_verified=ready, live_verified=False,
                                  message="Runtime available; website availability varies")
        except (OSError, asyncio.TimeoutError):
            return ProviderHealth(state=ProviderState.BROKEN, live_verified=False,
                                  message="Maigret runtime unavailable or timed out")
        finally:
            if proc and proc.returncode is None:
                proc.kill()
                await proc.communicate()

    def build_command(self, target):
        # Supply the target on stdin, not in the process command line.
        return [self.python_exec, "-m", "spider.providers.maigret.worker"]

    @staticmethod
    def rows(raw):
        text = raw.decode("utf-8", errors="replace").strip()
        try:
            data = json.loads(text)
            if isinstance(data, dict) and isinstance(data.get("sites"), dict):
                return [dict(info, sitename=name) for name, info in data["sites"].items()
                        if isinstance(info, dict)]
        except ValueError:
            pass
        rows = []
        for line in text.splitlines():
            try:
                row = json.loads(line)
                if isinstance(row, dict): rows.append(row)
            except ValueError:
                continue
        return rows

    @staticmethod
    def state(row):
        status = row.get("status", "")
        if isinstance(status, dict): status = status.get("status", "")
        if row.get("error"): return "unknown"
        if row.get("negative_control", "not_required") not in ("not_required", "available"):
            return "unknown"
        return str(status).casefold()

    @classmethod
    def coverage(cls, raw):
        rows = cls.rows(raw)
        manifest = next((r for r in rows if r.get("kind") == "manifest"), {})
        sites = {r.get("sitename") or r.get("site_name"): r for r in rows
                 if r.get("sitename") or r.get("site_name")}
        priority_sites = {}
        for platform, details in manifest.get("priority_sites", {}).items():
            details = dict(details) if isinstance(details, dict) else {"state": str(details)}
            row = sites.get(details.get("site_name"))
            if row:
                details["outcome"] = cls.state(row).upper()
                if row.get("verification_reason"):
                    details["reason"] = row["verification_reason"]
            elif details.get("state") == "SCHEDULED":
                details["outcome"] = "UNPROCESSED"
            priority_sites[platform] = details
        found = sum(cls.state(r) in ("found", "claimed") for r in sites.values())
        absent = sum(cls.state(r) == "available" for r in sites.values())
        invalid = sum(cls.state(r) == "illegal" for r in sites.values())
        controls_pending = sum(r.get("negative_control") == "pending" for r in sites.values())
        controls_unknown = sum(r.get("negative_control") in ("unknown", "illegal") for r in sites.values())
        return {"selected": manifest.get("selected", len(sites)),
                "supported": manifest.get("supported", len(sites)),
                "checked": len(sites), "found": found, "not_found": absent,
                "invalid": invalid, "unknown": len(sites) - found - absent - invalid,
                "unprocessed": max(0, manifest.get("selected", len(sites)) - len(sites)),
                "complete": any(r.get("kind") == "complete" for r in rows),
                "controls_pending": controls_pending, "controls_unknown": controls_unknown,
                "non_unique_detections": sum(r.get("verification_reason") == "non_unique_detection" for r in sites.values()),
                "excluded_ineligible": manifest.get("excluded_ineligible", 0),
                "priority_sites": priority_sites,
                "database_sha256": manifest.get("database_sha256"),
                "source_scope": manifest.get("source_scope", "GLOBAL_LIMIT"),
                "requested_sites": manifest.get("requested_sites", []),
                "requested_missing": manifest.get("requested_missing", []),
                "search_only_sites": manifest.get("search_only_sites", [])}

    async def execute(self, target, lineage, **kwargs):
        started = time.perf_counter()
        timeout = max(0.1, float(kwargs.get("timeout_seconds", 180)))
        limit = kwargs.get("username_site_limit", 500)
        if limit not in (0, 50, 500): raise ValueError("Unsupported site budget")
        scope = kwargs.get("username_source_scope")
        if scope is None:
            scope = {0: "GLOBAL_ALL", 50: "GLOBAL_50", 500: "GLOBAL_500"}[limit]
        if scope not in ("VN_COMMON_CORE", "GLOBAL_50", "GLOBAL_500", "GLOBAL_ALL"):
            raise ValueError("Unsupported username source scope")
        if scope == "VN_COMMON_CORE":
            requested_sites = list(DIRECT_MAIGRET_SITES)
            limit = len(requested_sites)
        else:
            requested_sites = None
            limit = {"GLOBAL_50": 50, "GLOBAL_500": 500, "GLOBAL_ALL": 0}[scope]
        progress = kwargs.get("on_progress")
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        proc = None
        timed_out = False
        with tempfile.TemporaryDirectory(prefix="spider-maigret-") as folder:
            report = Path(folder) / "results.ndjson"
            spec = {"username": target.canonical_value, "report": str(report),
                    "site_limit": limit, "source_scope": scope}
            if requested_sites is not None:
                spec["requested_sites"] = requested_sites
            ledger, budget = kwargs.get("request_ledger"), kwargs.get("execution_budget")
            if ledger is not None:
                spec["max_requests"] = max(0, budget.max_requests - ledger.requests_count)
                spec["fingerprint_salt"] = ledger._fingerprint_salt.hex()
            accounted = 0
            journal_events, recorded_outcomes = {}, set()
            recorder = kwargs.get("egress_recorder")
            async def account_requests():
                nonlocal accounted
                rows = self.rows(report.read_bytes()) if report.exists() else []
                events = [row for row in rows if row.get("kind") == "request"]
                for event in events[accounted:]:
                    if ledger is not None:
                        ledger.request(budget, self.provider_id(), "HTTP", event.get("purpose", "lookup"))
                    if recorder:
                        journal_events[event["sequence"]] = await recorder.begin(event["destination"],
                            event["purpose"], fingerprint=event["identifier_fingerprint"])
                    accounted += 1
                if recorder:
                    for event in rows:
                        sequence = event.get("sequence")
                        if event.get("kind") == "request_outcome" and sequence in journal_events and sequence not in recorded_outcomes:
                            await recorder.finish(journal_events[sequence], event["outcome"])
                            recorded_outcomes.add(sequence)
            if self.database_path: spec["database"] = str(self.database_path)
            try:
                proc = await asyncio.create_subprocess_exec(*self.build_command(target),
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL, env=env)
                communication = asyncio.create_task(proc.communicate(json.dumps(spec).encode("utf-8")))
                try:
                    while not communication.done():
                        remaining = timeout - (time.perf_counter() - started)
                        if remaining <= 0:
                            timed_out = True
                            break
                        await asyncio.wait({communication}, timeout=min(1, remaining))
                        if progress and report.exists():
                            await account_requests()
                            await progress(self.coverage(report.read_bytes()))
                finally:
                    if proc.returncode is None:
                        proc.kill()
                    await communication
                    await account_requests()
                raw = report.read_bytes() if report.exists() else b""
            except OSError:
                raw = b""
        coverage = self.coverage(raw)
        observations = self.parse(raw, lineage)
        complete = coverage["complete"] and coverage["unprocessed"] == 0 and not coverage["controls_pending"] and proc and proc.returncode == 0
        partial = not complete or coverage["unknown"] > 0 or coverage["controls_unknown"] > 0
        error = ("Time budget reached; partial results retained" if timed_out else
                 "Some sites could not be checked" if coverage["unknown"] else
                 "Some control checks could not be completed" if coverage["controls_unknown"] else
                 "Maigret worker did not complete" if not complete else None)
        return ProviderExecutionResult(raw_content=raw, observations=observations,
            exit_code=0 if complete else 124 if timed_out else 1,
            outcome="PARTIAL" if partial and coverage["checked"] else "FAILED" if partial else "COMPLETED",
            error_message=error, metadata={"coverage": coverage, "requests": accounted},
            mime_type="application/x-ndjson", duration_ms=(time.perf_counter()-started)*1000,
            raw_items_count=coverage["checked"], accepted_count=len(observations))

    def parse(self, raw_content, lineage):
        results, seen = [], set()
        username = lineage.parent_observable_value
        if not username: return results
        # Later records enrich completed sites; retain their final status and fields.
        sites = {r.get("sitename") or r.get("site_name"): r for r in self.rows(raw_content)
                 if r.get("sitename") or r.get("site_name")}
        for row in sites.values():
            if self.state(row) not in ("found", "claimed"): continue
            if row.get("negative_control", "not_required") not in ("not_required", "available"):
                continue
            site = row.get("sitename") or row.get("site_name")
            status = row.get("status")
            url = row.get("url_user") or row.get("url") or (status.get("url") if isinstance(status, dict) else None)
            if not isinstance(site, str) or not isinstance(url, str): continue
            try:
                parsed = urlsplit(url)
                if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username: continue
            except ValueError:
                continue
            if (site.casefold(), url) in seen: continue
            seen.add((site.casefold(), url))
            account = f"{username}@{site.lower()}"
            evidence = dict(row, match_basis="username_only", profile_url=url,
                            identity_verified=False, platform=site)
            for typ, value, parent in ((ObservableType.ACCOUNT, account, username),
                                       (ObservableType.URL, url, account)):
                results.append(Observation(observable=self.normalize({"type": typ, "value": value,
                        "namespace": site.casefold() if typ == ObservableType.ACCOUNT else ""}),
                    lineage=lineage.model_copy(update={"upstream_source": f"maigret_{site.lower()}",
                        "upstream_family": "SOCIAL_MEDIA", "parent_observable_value": parent,
                        "parent_observable_type": ObservableType.ACCOUNT if parent == account else lineage.parent_observable_type,
                        "parent_namespace": site.casefold() if parent == account else lineage.parent_namespace}),
                    confidence=0.80, raw_data=evidence))
        return results

    def normalize(self, raw_item):
        return NormalizedObservable(type=raw_item["type"], value=raw_item["value"], namespace=raw_item.get("namespace", ""))
