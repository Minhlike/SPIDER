import asyncio
import json
import logging
import os
import sys
import time
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
        self.python_exec = python_exec or sys.executable or "python"

    def provider_id(self) -> str:
        return "maigret"

    def version(self) -> str:
        return "v0.6.5"

    def adapter_version(self) -> str:
        return "2.0.0"

    def capabilities(self) -> List[str]:
        return ["USERNAME_DISCOVERY"]

    def network_class(self) -> NetworkClass:
        return NetworkClass.THIRD_PARTY_ONLY

    def accepts(self) -> List[ObservableType]:
        return [ObservableType.USERNAME]

    def produces(self) -> List[ObservableType]:
        return [ObservableType.ACCOUNT, ObservableType.URL]

    async def health(self) -> ProviderHealth:
        start_t = time.perf_counter()
        try:
            proc = await asyncio.create_subprocess_exec(
                self.python_exec,
                "-m", "maigret",
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            latency = (time.perf_counter() - start_t) * 1000
            out_str = stdout.decode(errors="ignore")
            if proc.returncode == 0 and "0.6.5" in out_str:
                return ProviderHealth(
                    state=ProviderState.READY,
                    provider_version="0.6.5",
                    runtime_path=self.python_exec,
                    runtime_exists=True,
                    runtime_version_verified=True,
                    latency_ms=latency,
                    message="Maigret v0.6.5 package operational on Windows"
                )
            return ProviderHealth(
                state=ProviderState.MISSING_RUNTIME,
                message=f"Maigret check failed with exit code {proc.returncode}"
            )
        except Exception as e:
            return ProviderHealth(
                state=ProviderState.BROKEN,
                message=f"Maigret health check exception: {str(e)}"
            )

    def build_command(self, target: NormalizedObservable) -> List[str]:
        return [
            self.python_exec,
            "-m", "maigret",
            target.canonical_value,
            "--dns-resolver", "threaded",
            "--no-color",
            "--top-sites", "15",
            "-J", "ndjson",
            "--timeout", "4"
        ]

    async def execute(self, target: NormalizedObservable, lineage: SourceLineage, **kwargs) -> ProviderExecutionResult:
        cmd = self.build_command(target)
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        start_t = time.perf_counter()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=20.0)
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except Exception:
                    pass
                return ProviderExecutionResult(
                    raw_content=b"Maigret task timed out",
                    observations=[],
                    exit_code=124,
                    error_message="Maigret task timed out after 20s",
                    mime_type="text/plain"
                )
            duration = (time.perf_counter() - start_t) * 1000
            observations = self.parse(stdout, lineage)
            return ProviderExecutionResult(
                raw_content=stdout,
                observations=observations,
                exit_code=proc.returncode or 0,
                error_message=stderr.decode(errors="ignore") if proc.returncode != 0 else None,
                mime_type="application/x-ndjson",
                duration_ms=duration,
                raw_items_count=len(observations),
                accepted_count=len(observations)
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

        username = lineage.parent_observable_value or "unknown"

        # Format 1: Full JSON object (from frozen fixture or json export)
        if text.startswith("{") and "\"sites\"" in text:
            try:
                data = json.loads(text)
                sites = data.get("sites", {})
                username = data.get("username", username)
                for site_name, site_info in sites.items():
                    if not isinstance(site_info, dict):
                        continue
                    status = str(site_info.get("status", "")).lower()
                    user_url = site_info.get("url_user") or site_info.get("url")
                    if status in ("found", "claimed", "ok") or user_url:
                        account_handle = f"{username}@{site_name.lower()}"
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
            except json.JSONDecodeError:
                pass

        # Format 2: NDJSON stream format (line by line)
        for line in text.splitlines():
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            site_name = data.get("site_name") or data.get("sitename") or "unknown_site"
            user_url = data.get("url_user") or data.get("url")
            status = str(data.get("status", "")).lower()

            if status in ("found", "claimed", "ok") or user_url:
                account_handle = f"{username}@{site_name.lower()}"
                obs_account = self.normalize({"type": ObservableType.ACCOUNT, "value": account_handle})
                acc_lineage = lineage.model_copy(update={
                    "upstream_source": f"maigret_{site_name.lower()}",
                    "upstream_family": "SOCIAL_MEDIA",
                    "parent_observable_value": username
                })
                results.append(Observation(
                    observable=obs_account,
                    lineage=acc_lineage,
                    confidence=0.80,
                    raw_data=data
                ))

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
                        confidence=0.85,
                        raw_data=data
                    ))

        return results

    def normalize(self, raw_item: Any) -> NormalizedObservable:
        return NormalizedObservable(
            type=raw_item["type"],
            value=raw_item["value"]
        )
