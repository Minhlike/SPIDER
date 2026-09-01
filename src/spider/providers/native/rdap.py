import asyncio
import json
import logging
import urllib.request
import urllib.parse
from typing import List, Dict, Any, Optional
from spider.providers.base import BaseProviderAdapter, ProviderHealth, ProviderExecutionResult
from spider.models.enums import ObservableType, NetworkClass, ProviderState
from spider.models.observable import NormalizedObservable
from spider.models.observation import Observation
from spider.models.provenance import SourceLineage

logger = logging.getLogger(__name__)

class NativeRdapAdapter(BaseProviderAdapter):
    def provider_id(self) -> str:
        return "native_rdap"

    def version(self) -> str:
        return "1.0.0"

    def adapter_version(self) -> str:
        return "1.0.0"

    def capabilities(self) -> List[str]:
        return ["REGISTRY_LOOKUP", "INFRASTRUCTURE_DISCOVERY"]

    def network_class(self) -> NetworkClass:
        return NetworkClass.THIRD_PARTY_ONLY

    def accepts(self) -> List[ObservableType]:
        return [ObservableType.IP_ADDRESS, ObservableType.ASN, ObservableType.DOMAIN]

    def produces(self) -> List[ObservableType]:
        return [ObservableType.ASN, ObservableType.CIDR, ObservableType.ORGANIZATION]

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            state=ProviderState.READY,
            message="Native RDAP public registry client operational"
        )

    def build_command(self, target: NormalizedObservable) -> List[str]:
        return ["internal", "rdap_query", target.canonical_value]

    async def execute(self, target: NormalizedObservable, lineage: SourceLineage, **kwargs) -> ProviderExecutionResult:
        val = target.canonical_value
        obs_type = target.type
        loop = asyncio.get_running_loop()

        def _fetch_rdap_sync() -> Dict[str, Any]:
            if obs_type == ObservableType.IP_ADDRESS:
                url = f"https://rdap.arin.net/registry/ip/{val}"
            elif obs_type == ObservableType.ASN:
                asn_num = val.upper().replace("AS", "")
                url = f"https://rdap.arin.net/registry/autnum/{asn_num}"
            else:
                url = f"https://rdap.org/domain/{val}"

            req = urllib.request.Request(url, headers={"User-Agent": "SPIDER-OSINT/2.0", "Accept": "application/rdap+json,application/json"})
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    return json.loads(resp.read().decode("utf-8", errors="ignore"))
            except Exception as e:
                # Fallback to BGPView API if ARIN RDAP 404s/redirects
                if obs_type == ObservableType.IP_ADDRESS:
                    try:
                        bgp_url = f"https://api.bgpview.io/ip/{val}"
                        b_req = urllib.request.Request(bgp_url, headers={"User-Agent": "SPIDER-OSINT/2.0"})
                        with urllib.request.urlopen(b_req, timeout=5) as resp:
                            return json.loads(resp.read().decode("utf-8", errors="ignore"))
                    except Exception:
                        pass
                return {"error": str(e), "target": val}

        try:
            data = await loop.run_in_executor(None, _fetch_rdap_sync)
            raw_bytes = json.dumps(data, indent=2).encode("utf-8")
            observations = self.parse(raw_bytes, lineage)
            return ProviderExecutionResult(
                raw_content=raw_bytes,
                observations=observations,
                exit_code=0,
                mime_type="application/json"
            )
        except Exception as ex:
            logger.error(f"RDAP error: {ex}")
            return ProviderExecutionResult(
                raw_content=str(ex).encode("utf-8"),
                observations=[],
                exit_code=1,
                error_message=str(ex),
                mime_type="text/plain"
            )

    def parse(self, raw_content: bytes, lineage: SourceLineage) -> List[Observation]:
        results: List[Observation] = []
        try:
            data = json.loads(raw_content.decode("utf-8"))
        except Exception:
            return results

        if "error" in data:
            return results

        parent_val = lineage.parent_observable_value

        # Parse BGPView response format if present
        if "data" in data and isinstance(data["data"], dict):
            b_data = data["data"]
            # ASN
            for prefix in b_data.get("prefixes", []):
                asn_info = prefix.get("asn", {})
                asn_num = asn_info.get("asn")
                asn_name = asn_info.get("name")
                cidr_str = prefix.get("prefix")

                if asn_num:
                    obs_asn = self.normalize({"type": ObservableType.ASN, "value": f"AS{asn_num}"})
                    asn_lin = lineage.model_copy(update={"upstream_source": "bgpview_rdap", "upstream_family": "ROUTING_REGISTRY", "parent_observable_value": parent_val})
                    results.append(Observation(observable=obs_asn, lineage=asn_lin, confidence=0.92, raw_data=asn_info))

                if cidr_str:
                    obs_cidr = self.normalize({"type": ObservableType.CIDR, "value": cidr_str})
                    cidr_lin = lineage.model_copy(update={"upstream_source": "bgpview_rdap", "upstream_family": "ROUTING_REGISTRY", "parent_observable_value": f"AS{asn_num}" if asn_num else parent_val})
                    results.append(Observation(observable=obs_cidr, lineage=cidr_lin, confidence=0.92, raw_data=prefix))

                if asn_name:
                    obs_org = self.normalize({"type": ObservableType.ORGANIZATION, "value": asn_name})
                    org_lin = lineage.model_copy(update={"upstream_source": "bgpview_rdap", "upstream_family": "ROUTING_REGISTRY", "parent_observable_value": f"AS{asn_num}" if asn_num else parent_val})
                    results.append(Observation(observable=obs_org, lineage=org_lin, confidence=0.90, raw_data=asn_info))

        # Parse Standard RFC 7483 RDAP response format
        name = data.get("name")
        handle = data.get("handle")
        if name and not results:
            obs_org = self.normalize({"type": ObservableType.ORGANIZATION, "value": name})
            item_lin = lineage.model_copy(update={"upstream_source": "arin_rdap", "upstream_family": "ROUTING_REGISTRY", "parent_observable_value": parent_val})
            results.append(Observation(observable=obs_org, lineage=item_lin, confidence=0.90, raw_data=data))

        return results

    def normalize(self, raw_item: Any) -> NormalizedObservable:
        return NormalizedObservable(
            type=raw_item["type"],
            value=raw_item["value"]
        )
