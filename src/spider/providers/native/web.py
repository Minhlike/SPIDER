"""Authorized, low-impact HTTP metadata collection for a domain report."""
from __future__ import annotations

import json
import re
from typing import Any, List
from urllib.parse import urlsplit, urlunsplit

import httpx

from spider.models.enums import NetworkClass, ObservableType, ProviderState
from spider.models.observable import NormalizedObservable
from spider.models.observation import Observation
from spider.models.provenance import SourceLineage
from spider.providers.base import BaseProviderAdapter, ProviderExecutionResult, ProviderHealth
from spider.providers.transport import provider_client


_TITLE = re.compile(r"<title[^>]*>\s*(.*?)\s*</title", re.IGNORECASE | re.DOTALL)


def _public_url(value: str) -> str | None:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return None
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


class NativeWebMetadataAdapter(BaseProviderAdapter):
    """Collect a single, explicitly authorized HTTPS response without crawling."""

    request_budget_supported = True

    def provider_id(self) -> str:
        return "native_web"

    def version(self) -> str:
        return "1.0.0"

    def adapter_version(self) -> str:
        return "1.0.0"

    def capabilities(self) -> List[str]:
        return ["WEB_METADATA"]

    def network_class(self) -> NetworkClass:
        return NetworkClass.TARGET_DIRECT

    def accepts(self) -> List[ObservableType]:
        return [ObservableType.DOMAIN, ObservableType.HOSTNAME]

    def produces(self) -> List[ObservableType]:
        return [ObservableType.URL]

    async def health(self) -> ProviderHealth:
        return ProviderHealth(state=ProviderState.READY,
                              message="Authorized single-request HTTPS metadata collector available")

    def build_command(self, target: NormalizedObservable) -> List[str]:
        return ["internal", "https_metadata", target.canonical_value]

    async def execute(self, target: NormalizedObservable, lineage: SourceLineage,
                      **kwargs) -> ProviderExecutionResult:
        url = f"https://{target.canonical_value}/"
        try:
            async with provider_client(self.provider_id(), kwargs, timeout=10,
                                       follow_redirects=False,
                                       transport=kwargs.get("transport")) as client:
                response = await client.get(url, headers={"User-Agent": "SPIDER/2.0 domain metadata"},
                                            extensions={"spider_purpose": "authorized_web_metadata",
                                                        "spider_identifier": target})
            final_url = _public_url(str(response.url))
            if final_url is None:
                raise ValueError("response URL is not a public HTTPS URL")
            body = response.content[:128_000].decode(response.encoding or "utf-8", errors="replace")
            match = _TITLE.search(body)
            title = " ".join(match.group(1).split())[:300] if match else ""
            headers = response.headers
            summary = {
                "record_kind": "authorized_web_metadata",
                "url": final_url,
                "http_status": response.status_code,
                "redirect_location": _public_url(headers.get("location", "")),
                "title": title,
                "server": headers.get("server", "")[:200],
                "x_powered_by": headers.get("x-powered-by", "")[:200],
                "generator": headers.get("x-generator", "")[:200],
                "content_type": headers.get("content-type", "")[:200],
                "has_hsts": bool(headers.get("strict-transport-security")),
                "has_csp": bool(headers.get("content-security-policy")),
            }
            raw = json.dumps(summary, ensure_ascii=False, separators=(",", ":")).encode()
            return ProviderExecutionResult(raw_content=raw, observations=self.parse(raw, lineage),
                                           outcome="COMPLETED", mime_type="application/json")
        except (httpx.HTTPError, ValueError):
            return ProviderExecutionResult(raw_content=b"{}", observations=[], outcome="PARTIAL",
                                           error_message="Authorized HTTPS metadata request was unavailable",
                                           metadata={"collection_reason": "NETWORK_OR_RESPONSE_ERROR"})

    def parse(self, raw_content: bytes, lineage: SourceLineage) -> List[Observation]:
        try:
            summary = json.loads(raw_content.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return []
        url = summary.get("url") if isinstance(summary, dict) else None
        if not isinstance(url, str) or not _public_url(url):
            return []
        return [Observation(
            observable=self.normalize({"type": ObservableType.URL, "value": url}),
            lineage=lineage.model_copy(update={"upstream_source": "authorized_https_metadata",
                                                "upstream_family": "WEB_METADATA"}),
            confidence=0.98,
            raw_data=summary,
        )]

    def normalize(self, raw_item: Any) -> NormalizedObservable:
        return NormalizedObservable(type=raw_item["type"], value=raw_item["value"])
