import json
import time
from pathlib import Path
from typing import Any, List, Optional

from spider.providers.base import BaseProviderAdapter, ProviderHealth, ProviderExecutionResult
from spider.models.enums import ObservableType, NetworkClass, ProviderState
from spider.models.observable import NormalizedObservable
from spider.models.observation import Observation
from spider.models.provenance import SourceLineage
from spider.storage.key_store import KeyStoreError
from . import api_access as access

UNCOVER_ENGINES = list(access.REQUIREMENTS)


class UncoverAdapter(BaseProviderAdapter):
    request_budget_supported = True
    def __init__(self, binary_path: Optional[str] = None, key_loader=None):
        self.binary_path = Path(binary_path) if binary_path else access.PRIVATE_BINARY
        self.key_loader = key_loader or access.saved_keys

    def provider_id(self) -> str:
        return "uncover"

    def version(self) -> str:
        return "v1.2.1"

    def adapter_version(self) -> str:
        return "1.2.0"

    def capabilities(self) -> List[str]:
        return ["INTERNET_INTELLIGENCE"]

    def network_class(self) -> NetworkClass:
        return NetworkClass.THIRD_PARTY_ONLY

    def accepts(self) -> List[ObservableType]:
        return [ObservableType.DOMAIN, ObservableType.IP_ADDRESS, ObservableType.ORGANIZATION]

    def produces(self) -> List[ObservableType]:
        return [ObservableType.IP_ADDRESS, ObservableType.HOSTNAME, ObservableType.URL]

    def _keys(self):
        return access.effective_keys(self.key_loader())

    def _has_keys(self, engine: Optional[str] = None) -> bool:
        presence = access.engine_presence(self._keys())
        return presence[engine]["configured"] if engine else any(p["configured"] for p in presence.values())

    async def health(self) -> ProviderHealth:
        try:
            engines = access.engine_presence(self._keys())
        except KeyStoreError:
            return ProviderHealth(state=ProviderState.BROKEN, message="Protected credential storage unavailable",
                                  live_verified=False, credential_state="UNAVAILABLE")
        configured = any(item["configured"] for item in engines.values())
        runtime = access.verified_runtime(self.binary_path)
        state = ProviderState.READY if configured else ProviderState.MISSING_CREDENTIAL
        if not runtime:
            state = ProviderState.MISSING_RUNTIME
        return ProviderHealth(state=state, provider_version=self.version(), adapter_version=self.adapter_version(),
            runtime_path=str(self.binary_path), runtime_exists=self.binary_path.exists(),
            runtime_version_verified=runtime, live_verified=False, credential_state="UNTESTED" if configured else "MISSING_CREDENTIAL",
            message="Uncover v1.2.1 private runner: credentials configured; connection not tested" if configured and runtime
                    else "Uncover v1.2.1: missing complete credentials or verified private runtime",
            details={"engines": engines, "connection_test": "/api/settings/test/{engine}"})

    @staticmethod
    def query_for(target: NormalizedObservable, engine: str) -> str:
        value = json.dumps(target.canonical_value, ensure_ascii=False)
        if target.type == ObservableType.DOMAIN:
            return {"shodan": f"hostname:{value}", "censys": f"web.hostname={value}", "fofa": f"domain={value}"}[engine]
        if target.type == ObservableType.IP_ADDRESS:
            return {"shodan": f"net:{value}", "censys": f"host.ip={value}", "fofa": f"ip={value}"}[engine]
        return value

    def build_command(self, target: NormalizedObservable, engine: str = "shodan") -> List[str]:
        return [str(self.binary_path.resolve()), "-engine", engine, "-mode", "search", "-q", self.query_for(target, engine), "-limit", "10"]

    async def execute(self, target: NormalizedObservable, lineage: SourceLineage, **kwargs) -> ProviderExecutionResult:
        started = time.monotonic()
        try:
            keys = self._keys()
        except KeyStoreError:
            return ProviderExecutionResult(raw_content=b"[]", observations=[], exit_code=1, outcome="FAILED",
                                           error_message="Protected credential storage unavailable")
        presence = access.engine_presence(keys)
        statuses, rows = {}, []
        timeout = max(0.1, float(kwargs.get("timeout_seconds", 60)))
        ledger, budget = kwargs.get("request_ledger"), kwargs.get("execution_budget")
        recorder = kwargs.get("egress_recorder")
        request_count = 0
        try:
            for engine in UNCOVER_ENGINES:
                remaining = timeout - (time.monotonic() - started)
                if not presence[engine]["configured"]:
                    result = access.result_state(engine, "MISSING_CREDENTIAL", "REQUIRED_FIELDS_MISSING", "search")
                elif remaining <= 0:
                    result = access.result_state(engine, "NETWORK_ERROR", "TIMEOUT", "search")
                elif ledger is not None and ledger.requests_count >= budget.max_requests:
                    result = access.result_state(engine, "PLAN/QUOTA_LIMIT", "PAGE_LIMIT", "search")
                else:
                    result = await access.run_engine(engine, keys, mode="search", query=self.query_for(target, engine),
                        binary=self.binary_path, timeout=min(23, remaining))
                    journal = result.get("request_journal", [])
                    if len(journal) != 1:
                        result = access.result_state(engine, "NETWORK_ERROR", "UNEXPECTED_RESPONSE", "search")
                    else:
                        entry = journal[0]
                        if ledger is not None:
                            ledger.request(budget, self.provider_id(), "HTTP", f"{engine}_search")
                        request_count += 1
                        if recorder:
                            event = await recorder.begin(entry["destination"], entry["purpose"], credentialed=True)
                            await recorder.finish(event, entry["outcome"])
                rows.extend(result.pop("results"))
                statuses[engine] = result
            raw = "\n".join(json.dumps(row) for row in rows).encode()
            observations = self.parse(raw, lineage)
            attempted = [r for e, r in statuses.items() if presence[e]["configured"]]
            successes = sum(r["state"] == "VALID" for r in attempted)
            outcome = "COMPLETED" if attempted and successes == len(attempted) else "PARTIAL" if successes else "FAILED"
            return ProviderExecutionResult(raw_content=raw, observations=observations,
                exit_code=0 if outcome == "COMPLETED" else 1, outcome=outcome,
                error_message=None if outcome == "COMPLETED" else "Uncover engines unavailable; see per-engine status",
                metadata={"engines": statuses, "bounded_to_first_page": True,
                          "request_count": request_count, "request_journal_verified": True},
                raw_items_count=len(rows), accepted_count=len(observations), mime_type="application/x-ndjson",
                duration_ms=(time.monotonic()-started)*1000)
        finally:
            keys.clear()

    def parse(self, raw_content: bytes, lineage: SourceLineage) -> List[Observation]:
        rows = []
        for line in raw_content.decode("utf-8", errors="replace").splitlines():
            try:
                row = json.loads(line)
                if isinstance(row, dict):
                    row.setdefault("engine", row.get("source", "uncover"))
                    rows.append(row)
            except ValueError:
                pass
        results = []
        for row in access.clean_rows(rows, {}):
            for field, kind, confidence in (("ip", ObservableType.IP_ADDRESS, .9),
                                            ("host", ObservableType.HOSTNAME, .85), ("url", ObservableType.URL, .85)):
                value = row.get(field)
                if not value or (field == "host" and value == row.get("ip")):
                    continue
                results.append(Observation(observable=self.normalize({"type": kind, "value": value}),
                    lineage=lineage.model_copy(update={"upstream_source": f"uncover_{row['engine']}",
                        "upstream_family": "INTERNET_SCANNER",
                        "parent_observable_value": lineage.parent_observable_value if field == "ip" else row.get("ip") or lineage.parent_observable_value}),
                    confidence=confidence, raw_data=row))
        return results

    def normalize(self, raw_item: Any) -> NormalizedObservable:
        return NormalizedObservable(type=raw_item["type"], value=raw_item["value"])
