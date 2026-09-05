"""Public Gravatar profile lookup by a derived SHA-256 email identifier."""
import hashlib
import json
import re
import time
from urllib.parse import unquote, urlsplit, urlunsplit

import httpx

from spider.models.budget import RequestBudgetExceeded
from spider.models.enums import NetworkClass, ObservableType, ProviderState
from spider.models.observable import NormalizedObservable
from spider.models.observation import Observation
from spider.providers.base import BaseProviderAdapter, ProviderExecutionResult, ProviderHealth
from spider.providers.transport import provider_client


_GRAVATAR_HOSTS = {"gravatar.com", "www.gravatar.com"}
_HANDLE = re.compile(r"[A-Za-z0-9_.-]{1,100}")
_SERVICE = re.compile(r"[a-z0-9_-]{1,50}")


def gravatar_email_hash(email: str) -> str:
    """Follow Gravatar's documented trim, lowercase, SHA-256 contract."""
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def _safe_url(value, *, hosts=None, forbidden=""):
    if not isinstance(value, str) or len(value) > 2048:
        return ""
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return ""
    hostname = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or not hostname or parsed.username or parsed.password:
        return ""
    if hosts is not None and hostname not in hosts:
        return ""
    if forbidden and forbidden.casefold() in unquote(value).casefold():
        return ""
    # Query strings and fragments are not evidence here and can contain identifiers.
    return urlunsplit(("https", hostname, parsed.path or "/", "", ""))


def _safe_text(value, limit, forbidden=""):
    text = value if isinstance(value, str) else ""
    text = " ".join(text.split())[:limit]
    if forbidden:
        text = re.sub(re.escape(forbidden), "[redacted-email]", text,
                      flags=re.IGNORECASE)
    return text


class GravatarPublicProfileAdapter(BaseProviderAdapter):
    """Resolve only user-published Gravatar data; this does not prove legal identity."""

    request_budget_supported = True

    def __init__(self, transport=None):
        self.transport = transport

    def provider_id(self): return "gravatar_public"
    def version(self): return "v3"
    def adapter_version(self): return "1.0.0"
    def capabilities(self): return ["EMAIL_PUBLIC_PROFILE_LOOKUP"]
    def network_class(self): return NetworkClass.THIRD_PARTY_ONLY
    def accepts(self): return [ObservableType.EMAIL]
    def produces(self): return [ObservableType.ACCOUNT, ObservableType.URL]
    def build_command(self, target): return []

    async def health(self):
        return ProviderHealth(
            state=ProviderState.READY_LIMITED,
            provider_version=self.version(),
            credential_state="NOT_REQUIRED",
            live_verified=False,
            message="Public Gravatar profile data only; owner identity remains unverified",
        )

    async def execute(self, target, lineage, **kwargs):
        started = time.perf_counter()
        ledger = kwargs.get("request_ledger")
        starting_requests = ledger.attributed_requests_count if ledger is not None else 0
        if target.type != ObservableType.EMAIL:
            return ProviderExecutionResult(
                raw_content=b'{"profiles":[]}', observations=[], exit_code=1,
                outcome="FAILED", error_message="Unsupported observable type",
                metadata={"requests": 0, "collection_reason": "UNSUPPORTED_INPUT_TYPE"})
        email = target.canonical_value
        identifier_hash = gravatar_email_hash(email)
        derived_identifier = NormalizedObservable(
            type=ObservableType.EMAIL_SHA256,
            value=identifier_hash,
            namespace="gravatar_email_sha256",
        )
        rows = []
        outcome, error, reason = "COMPLETED", None, "NO_PUBLIC_PRIMARY_EMAIL_PROFILE"
        negative_verified = False
        try:
            async with provider_client(
                self.provider_id(), kwargs,
                base_url="https://api.gravatar.com/v3",
                headers={"Accept": "application/json", "User-Agent": "SPIDER-public-profile/2.0"},
                timeout=min(10, kwargs.get("timeout_seconds", 30)),
                follow_redirects=False,
                transport=self.transport,
            ) as client:
                async with client.stream(
                    "GET", f"/profiles/{identifier_hash}",
                    extensions={
                        "spider_identifier": derived_identifier,
                        "spider_purpose": "public_profile_lookup",
                    },
                ) as response:
                    if response.status_code == 404:
                        negative_verified = True
                    elif response.status_code == 429:
                        outcome, error, reason = "PARTIAL", "Gravatar rate limit reached", "RATE_LIMIT"
                    elif response.status_code in (401, 403):
                        outcome, error, reason = "PARTIAL", "Gravatar public profile request denied", "ACCESS_DENIED"
                    elif response.status_code >= 500:
                        outcome, error, reason = "PARTIAL", "Gravatar service unavailable", "UPSTREAM_ERROR"
                    else:
                        response.raise_for_status()
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(body) + len(chunk) > 262_144:
                                raise ValueError("Profile response exceeds size limit")
                            body.extend(chunk)
                        data = json.loads(body)
                        rows = self._allowlisted_rows(data, identifier_hash, email)
                        if not rows:
                            outcome, error, reason = "PARTIAL", "Gravatar profile response was invalid", "UNEXPECTED_RESPONSE"
                        else:
                            reason = "PUBLIC_PROFILE_FOUND"
        except RequestBudgetExceeded:
            outcome, error, reason = "PARTIAL", "Network request budget exhausted", "REQUEST_LIMIT"
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            outcome, error, reason = "PARTIAL", "Gravatar public profile response unavailable", "NETWORK_OR_RESPONSE_ERROR"

        raw = json.dumps({"profiles": rows}, ensure_ascii=False, separators=(",", ":")).encode()
        observations = self.parse(raw, lineage)
        requests = (ledger.attributed_requests_count - starting_requests) if ledger is not None else (
            0 if reason == "REQUEST_LIMIT" else 1)
        return ProviderExecutionResult(
            raw_content=raw,
            observations=observations,
            exit_code=0 if outcome == "COMPLETED" else 1,
            outcome=outcome,
            error_message=error,
            duration_ms=(time.perf_counter() - started) * 1000,
            raw_items_count=len(rows),
            accepted_count=len(observations),
            metadata={
                "requests": requests,
                "specific_negative_verified": negative_verified,
                "collection_reason": reason,
                "scope": "Public Gravatar profile for the primary email hash",
                "identifier_disclosed": "SHA256_EMAIL",
            },
        )

    @staticmethod
    def _allowlisted_rows(data, expected_hash, email):
        if not isinstance(data, dict) or data.get("hash") != expected_hash:
            return []
        profile_url = _safe_url(data.get("profile_url"), hosts=_GRAVATAR_HOSTS, forbidden=email)
        if not profile_url:
            return []
        slug = unquote(urlsplit(profile_url).path).strip("/").split("/")[-1]
        if not _HANDLE.fullmatch(slug):
            return []
        common = {
            "platform": "Gravatar",
            "profile_url": profile_url,
            "display_name": _safe_text(data.get("display_name"), 200, email),
            "bio": _safe_text(data.get("description"), 1000, email),
            "location": _safe_text(data.get("location"), 200, email),
            "job_title": _safe_text(data.get("job_title"), 200, email),
            "company": _safe_text(data.get("company"), 200, email),
            "website": "",
            "match_basis": "email_hash_public_profile",
            "identity_verified": False,
            "account": f"{slug}@gravatar",
        }
        links = data.get("links") if isinstance(data.get("links"), list) else []
        for link in links[:20]:
            if isinstance(link, dict):
                common["website"] = _safe_url(link.get("url"), forbidden=email)
                if common["website"]:
                    break
        rows = [common]
        verified = data.get("verified_accounts") if isinstance(data.get("verified_accounts"), list) else []
        for item in verified[:30]:
            if not isinstance(item, dict) or item.get("is_hidden") is True:
                continue
            service = str(item.get("service_type") or "").casefold()
            url = _safe_url(item.get("url"), forbidden=email)
            if not _SERVICE.fullmatch(service) or not url:
                continue
            handle = unquote(urlsplit(url).path).rstrip("/").split("/")[-1].lstrip("@")
            if not _HANDLE.fullmatch(handle):
                continue
            rows.append({
                "platform": _safe_text(item.get("service_label"), 100, email) or service,
                "profile_url": url,
                "display_name": common["display_name"],
                "bio": "",
                "website": "",
                "match_basis": "verified_account_from_email_profile",
                "identity_verified": False,
                "account": f"{handle}@{service}",
                "verification_state": "SERVICE_VERIFIED_LINK",
            })
        return rows

    def parse(self, raw_content, lineage):
        try:
            rows = json.loads(raw_content).get("profiles", [])
        except (ValueError, AttributeError):
            return []
        observations = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict) or row.get("match_basis") not in {
                "email_hash_public_profile", "verified_account_from_email_profile"
            }:
                continue
            account = row.get("account", "")
            url = _safe_url(row.get("profile_url"))
            if not isinstance(account, str) or "@" not in account or not url:
                continue
            namespace = account.rsplit("@", 1)[-1].casefold()
            account_observable = self.normalize({"type": ObservableType.ACCOUNT,
                "value": account, "namespace": namespace})
            account_lineage = lineage.model_copy(update={
                "upstream_source": "gravatar_public_profile",
                "upstream_family": "PUBLIC_PROFILE",
            })
            observations.append(Observation(observable=account_observable,
                lineage=account_lineage, confidence=0.95 if namespace == "gravatar" else 0.90,
                raw_data=row))
            observations.append(Observation(
                observable=self.normalize({"type": ObservableType.URL, "value": url}),
                lineage=account_lineage.with_parent(account, ObservableType.ACCOUNT, namespace),
                confidence=0.95 if namespace == "gravatar" else 0.90,
                raw_data=row,
            ))
        return observations

    def normalize(self, raw_item):
        return NormalizedObservable(type=raw_item["type"], value=raw_item["value"],
                                    namespace=raw_item.get("namespace", ""))
