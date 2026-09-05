"""Credentialed WhatIsMyIP v1 API adapter.

The API key is sent only in the X-API-KEY header.  It is never placed in a URL,
artifact, provider result, exception, or log message.
"""
from __future__ import annotations

import ipaddress
import json
import os
import time
from typing import Any, Callable, List, Mapping
from urllib.parse import quote

import httpx

from spider.models.budget import RequestBudgetExceeded
from spider.models.enums import NetworkClass, ObservableType, ProviderState
from spider.models.observable import NormalizedObservable
from spider.models.observation import Observation
from spider.models.provenance import SourceLineage
from spider.providers.base import BaseProviderAdapter, ProviderExecutionResult, ProviderHealth
from spider.providers.transport import provider_client

BASE_URL = "https://wimi-api.whatismyip.com"
BASE_URL_V4 = "https://wimi-api-v4.whatismyip.com"
BASE_URL_V6 = "https://wimi-api-v6.whatismyip.com"
KEY_NAME = "WHATISMYIP_API_KEY"


def saved_api_key() -> str:
    """Prefer DPAPI settings and allow an explicitly injected test environment."""
    from spider.web.api.settings import load_settings
    stored = str(load_settings().get("api_keys", {}).get(KEY_NAME, "")).strip()
    if stored:
        return stored
    return os.environ.get(KEY_NAME, "").strip()


def _state_for_status(status: int) -> tuple[str, str]:
    if status == 401:
        return "INVALID_KEY", "AUTH_REJECTED"
    if status == 403:
        return "DISABLED_KEY", "KEY_DISABLED_OR_REVOKED"
    if status == 429:
        return "QUOTA_LIMIT", "DAILY_LIMIT_REACHED"
    if status >= 500:
        return "NETWORK_ERROR", "UPSTREAM_UNAVAILABLE"
    return "NETWORK_ERROR", "UNEXPECTED_RESPONSE"


def _safe_result(state: str, reason: str) -> dict[str, Any]:
    return {"engine": "whatismyip", "state": state, "reason": reason,
            "scope": "account", "cached": False}


async def check_api_key(key: str, *, transport=None, timeout: float = 5.0) -> dict[str, Any]:
    if not key.strip():
        return _safe_result("MISSING_CREDENTIAL", "REQUIRED_FIELDS_MISSING")
    try:
        async with httpx.AsyncClient(
            base_url=BASE_URL,
            headers={"X-API-KEY": key, "Accept": "application/json"},
            timeout=timeout,
            trust_env=False,
            transport=transport,
        ) as client:
            response = await client.get("/ip")
        if response.status_code != 200:
            return _safe_result(*_state_for_status(response.status_code))
        data = response.json()
        if not isinstance(data, dict) or not isinstance(data.get("ip"), str):
            return _safe_result("NETWORK_ERROR", "PARSER_DRIFT")
        address = ipaddress.ip_address(data["ip"])
        if not address.is_global:
            return _safe_result("NETWORK_ERROR", "INVALID_UPSTREAM_IP")
        return _safe_result("VALID", "REQUEST_ACCEPTED")
    except (httpx.HTTPError, ValueError, TypeError):
        return _safe_result("NETWORK_ERROR", "CONNECTION_FAILED")


async def fetch_public_address(key: str, version: int = 4, *, transport=None,
                               timeout: float = 4.0) -> dict[str, Any]:
    if not key.strip():
        raise ValueError("MISSING_CREDENTIAL")
    base_url = BASE_URL_V6 if version == 6 else BASE_URL_V4
    try:
        async with httpx.AsyncClient(
            base_url=base_url,
            headers={"X-API-KEY": key, "Accept": "application/json"},
            timeout=timeout,
            trust_env=False,
            transport=transport,
        ) as client:
            response = await client.get("/ip")
        if response.status_code != 200:
            raise ValueError(_state_for_status(response.status_code)[0])
        data = response.json()
        address = ipaddress.ip_address(data.get("ip", ""))
        if address.version != version or not address.is_global:
            raise ValueError("PUBLIC_ADDRESS_UNAVAILABLE")
        return {"ip": str(address), "version": address.version}
    except httpx.HTTPError:
        raise ValueError("NETWORK_ERROR") from None
    except (KeyError, TypeError, json.JSONDecodeError):
        raise ValueError("PARSER_DRIFT") from None


class WhatIsMyIPAdapter(BaseProviderAdapter):
    request_budget_supported = True

    def __init__(self, key_loader: Callable[[], str] | None = None, transport=None):
        self.key_loader = key_loader or saved_api_key
        self.transport = transport

    def provider_id(self) -> str:
        return "whatismyip"

    def version(self) -> str:
        return "v1"

    def adapter_version(self) -> str:
        return "1.0.0"

    def capabilities(self) -> List[str]:
        return ["IP_ENRICHMENT"]

    def network_class(self) -> NetworkClass:
        return NetworkClass.THIRD_PARTY_ONLY

    def accepts(self) -> List[ObservableType]:
        return [ObservableType.IP_ADDRESS, ObservableType.IPV6_ADDRESS]

    def produces(self) -> List[ObservableType]:
        return [ObservableType.IP_ADDRESS, ObservableType.IPV6_ADDRESS,
                ObservableType.ASN, ObservableType.ORGANIZATION]

    async def health(self) -> ProviderHealth:
        configured = bool(self.key_loader())
        return ProviderHealth(
            state=ProviderState.DEGRADED if configured else ProviderState.MISSING_CREDENTIAL,
            provider_version=self.version(),
            adapter_version=self.adapter_version(),
            credential_state="UNTESTED" if configured else "MISSING_CREDENTIAL",
            message=("WhatIsMyIP key configured; connection not tested" if configured
                     else "WhatIsMyIP API key is not configured"),
            live_verified=False,
            contract_verified=False,
            details={"connection_test": "/api/settings/test/whatismyip"},
        )

    def build_command(self, target: NormalizedObservable) -> List[str]:
        return ["internal", "whatismyip_lookup", target.canonical_value]

    async def execute(self, target: NormalizedObservable, lineage: SourceLineage,
                      **kwargs) -> ProviderExecutionResult:
        started = time.monotonic()
        try:
            address = ipaddress.ip_address(target.canonical_value)
        except ValueError:
            return ProviderExecutionResult(raw_content=b"", observations=[], exit_code=1,
                outcome="FAILED", error_message="Invalid IP address")
        if not address.is_global:
            return ProviderExecutionResult(raw_content=b"{}", observations=[], exit_code=0,
                outcome="COMPLETED", metadata={"collection_state": "LOCAL_ONLY_ADDRESS",
                                                "request_count": 0})

        key = self.key_loader().strip()
        if not key:
            return ProviderExecutionResult(raw_content=b"{}", observations=[], exit_code=1,
                outcome="PARTIAL", error_message="WhatIsMyIP credential is not configured",
                metadata={"credential_state": "MISSING_CREDENTIAL", "request_count": 0})

        timeout = min(8.0, max(0.5, float(kwargs.get("timeout_seconds", 8.0))))
        responses: dict[str, Any] = {}
        statuses: dict[str, int] = {}
        partial_reason = None
        try:
            async with provider_client(
                self.provider_id(), kwargs, base_url=BASE_URL, timeout=timeout,
                headers={"X-API-KEY": key, "Accept": "application/json"},
                transport=kwargs.get("transport") or self.transport,
            ) as client:
                encoded = quote(str(address), safe=":")
                lookup = await client.get(
                    f"/ip-address-lookup/{encoded}",
                    extensions={"spider_purpose": "ip_geolocation_lookup",
                                "spider_identifier": target},
                )
                statuses["lookup"] = lookup.status_code
                if lookup.status_code != 200:
                    state, reason = _state_for_status(lookup.status_code)
                    return ProviderExecutionResult(raw_content=b"{}", observations=[], exit_code=1,
                        outcome="PARTIAL", error_message="WhatIsMyIP lookup unavailable",
                        metadata={"credential_state": state, "collection_state": reason})
                data = lookup.json()
                if not isinstance(data, dict) or str(data.get("ip", "")) != str(address):
                    raise ValueError("Invalid lookup response")
                responses["lookup"] = data

                # Proxy intelligence is useful but secondary. Preserve the lookup
                # if the request budget is exhausted or this endpoint is unavailable.
                try:
                    proxy = await client.get(
                        f"/proxy-check/{encoded}",
                        extensions={"spider_purpose": "ip_proxy_classification",
                                    "spider_identifier": target},
                    )
                    statuses["proxy"] = proxy.status_code
                    if proxy.status_code == 200:
                        proxy_data = proxy.json()
                        response_ip = proxy_data.get("ip") if isinstance(proxy_data, dict) else None
                        # The live v1 endpoint currently omits IP because it is
                        # already bound by the request path. Accept either form,
                        # but reject a conflicting echoed address.
                        if (isinstance(proxy_data, dict)
                                and (response_ip is None or str(response_ip) == str(address))):
                            proxy_data = {**proxy_data, "ip": str(address)}
                            responses["proxy"] = proxy_data
                        else:
                            partial_reason = "PARSER_DRIFT"
                    else:
                        partial_reason = _state_for_status(proxy.status_code)[1]
                except RequestBudgetExceeded:
                    partial_reason = "REQUEST_LIMIT"

            raw = json.dumps(responses, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            observations = self.parse(raw, lineage)
            return ProviderExecutionResult(
                raw_content=raw,
                observations=observations,
                exit_code=0,
                outcome="PARTIAL" if partial_reason else "COMPLETED",
                error_message="Proxy classification unavailable" if partial_reason else None,
                metadata={"collection_state": partial_reason or "COMPLETE",
                          "endpoint_status": statuses},
                raw_items_count=len(responses),
                accepted_count=len(observations),
                duration_ms=(time.monotonic() - started) * 1000,
            )
        except (httpx.HTTPError, ValueError, TypeError, json.JSONDecodeError):
            return ProviderExecutionResult(raw_content=b"{}", observations=[], exit_code=1,
                outcome="PARTIAL", error_message="WhatIsMyIP response unavailable or invalid",
                metadata={"collection_state": "NETWORK_OR_PARSER_ERROR"})
        finally:
            key = ""

    def parse(self, raw_content: bytes, lineage: SourceLineage) -> List[Observation]:
        try:
            envelope = json.loads(raw_content.decode("utf-8"))
            lookup = envelope.get("lookup", {})
            if not isinstance(lookup, dict):
                return []
            address = ipaddress.ip_address(str(lookup.get("ip", "")))
        except (ValueError, TypeError, json.JSONDecodeError):
            return []

        proxy = envelope.get("proxy") if isinstance(envelope.get("proxy"), dict) else {}
        normalized = {
            "record_kind": "whatismyip_ip_intelligence",
            "ip": str(address),
            "country": lookup.get("country"),
            "region": lookup.get("region"),
            "city": lookup.get("city"),
            "postal_code": lookup.get("postal_code"),
            "isp": lookup.get("isp"),
            "asn": lookup.get("asn"),
            "latitude": lookup.get("latitude"),
            "longitude": lookup.get("longitude"),
            "time_zone": lookup.get("time_zone"),
            "is_proxy": proxy.get("is_proxy"),
            "proxy_type": proxy.get("proxy_type"),
            "proxy_type_description": proxy.get("proxy_type_description"),
            "proxy_level": proxy.get("proxy_level"),
            "proxy_range": proxy.get("proxy_range"),
            "is_vpn": proxy.get("is_vpn"),
            "is_datacenter": proxy.get("is_datacenter"),
            "is_residential": proxy.get("is_residential"),
            "proxy_provider": proxy.get("provider"),
        }
        item_lineage = lineage.model_copy(update={
            "upstream_source": "whatismyip_api",
            "upstream_family": "IP_GEOLOCATION",
        })
        ip_type = ObservableType.IPV6_ADDRESS if address.version == 6 else ObservableType.IP_ADDRESS
        results = [Observation(
            observable=self.normalize({"type": ip_type, "value": str(address)}),
            lineage=item_lineage,
            confidence=0.72,
            raw_data=normalized,
        )]
        asn = str(lookup.get("asn") or "").strip().upper()
        if asn:
            results.append(Observation(
                observable=self.normalize({"type": ObservableType.ASN, "value": asn}),
                lineage=item_lineage,
                confidence=0.85,
                raw_data=normalized,
            ))
        isp = str(lookup.get("isp") or "").strip()
        if isp:
            results.append(Observation(
                observable=self.normalize({"type": ObservableType.ORGANIZATION, "value": isp}),
                lineage=item_lineage,
                confidence=0.78,
                raw_data=normalized,
            ))
        return results

    def normalize(self, raw_item: Mapping[str, Any]) -> NormalizedObservable:
        return NormalizedObservable(type=raw_item["type"], value=raw_item["value"])
