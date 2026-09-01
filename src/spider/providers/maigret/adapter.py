import asyncio
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from spider.providers.base import BaseProviderAdapter, ProviderHealth, ProviderExecutionResult
from spider.models.enums import ObservableType, NetworkClass, ProviderState
from spider.models.observable import NormalizedObservable
from spider.models.observation import Observation
from spider.models.provenance import SourceLineage

logger = logging.getLogger(__name__)

class MaigretAdapter(BaseProviderAdapter):
    def __init__(self, python_exec: Optional[str] = None):
        self.python_exec = python_exec or "python"

    def provider_id(self) -> str:
        return "maigret"

    def version(self) -> str:
        return "v0.6.5"

    def adapter_version(self) -> str:
        return "1.0.0"

    def capabilities(self) -> List[str]:
        return ["USERNAME_DISCOVERY"]

    def network_class(self) -> NetworkClass:
        return NetworkClass.THIRD_PARTY_ONLY

    def accepts(self) -> List[ObservableType]:
        return [ObservableType.USERNAME]

    def produces(self) -> List[ObservableType]:
        return [ObservableType.ACCOUNT, ObservableType.URL]

    async def health(self) -> ProviderHealth:
        return ProviderHealth(state=ProviderState.READY, message="Maigret v0.6.5 operational")

    def build_command(self, target: NormalizedObservable) -> List[str]:
        return [
            self.python_exec,
            "-m", "maigret",
            target.canonical_value,
            "--json", "raw",
            "-a"
        ]

    async def execute(self, target: NormalizedObservable, lineage: SourceLineage, **kwargs) -> ProviderExecutionResult:
        cmd = self.build_command(target)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            observations = self.parse(stdout, lineage)
            return ProviderExecutionResult(
                raw_content=stdout,
                observations=observations,
                exit_code=proc.returncode or 0,
                error_message=stderr.decode(errors="ignore") if proc.returncode != 0 else None,
                mime_type="application/json"
            )
        except Exception as ex:
            logger.error(f"Maigret execution error: {ex}")
            return ProviderExecutionResult(
                raw_content=str(ex).encode("utf-8"),
                observations=[],
                exit_code=1,
                error_message=str(ex),
                mime_type="text/plain"
            )

    def parse(self, raw_content: bytes, lineage: SourceLineage) -> List[Observation]:
        results: List[Observation] = []
        text = raw_content.decode("utf-8", errors="ignore").strip()
        if not text:
            return results

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return results

        username = data.get("username", lineage.parent_observable_value or "unknown")
        sites = data.get("sites", {})

        for site_name, site_info in sites.items():
            if not isinstance(site_info, dict):
                continue
            status = site_info.get("status", "")
            if status.lower() == "found":
                account_handle = f"{username}@{site_name}"
                user_url = site_info.get("url_user")

                # 1. ACCOUNT Observable
                obs_account = self.normalize({"type": ObservableType.ACCOUNT, "value": account_handle})
                acc_lineage = lineage.model_copy(update={
                    "upstream_source": f"maigret_{site_name.lower()}",
                    "upstream_family": "SOCIAL_MEDIA",
                    "parent_observable_value": username
                })
                results.append(Observation(
                    observable=obs_account,
                    lineage=acc_lineage,
                    confidence=0.85,
                    raw_data=site_info
                ))

                # 2. URL Observable if available
                if user_url:
                    obs_url = self.normalize({"type": ObservableType.URL, "value": user_url})
                    url_lineage = lineage.model_copy(update={
                        "upstream_source": f"maigret_{site_name.lower()}",
                        "upstream_family": "SOCIAL_MEDIA",
                        "parent_observable_value": account_handle
                    })
                    results.append(Observation(
                        observable=obs_url,
                        lineage=url_lineage,
                        confidence=0.9,
                        raw_data=site_info
                    ))

        return results

    def normalize(self, raw_item: Any) -> NormalizedObservable:
        return NormalizedObservable(
            type=raw_item["type"],
            value=raw_item["value"]
        )
