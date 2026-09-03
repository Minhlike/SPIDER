"""Public profile evidence, using GitHub's documented unauthenticated API."""
import json
import re
import time

import httpx

from spider.models.enums import NetworkClass, ObservableType, ProviderState
from spider.models.observable import NormalizedObservable
from spider.models.observation import Observation
from spider.providers.base import BaseProviderAdapter, ProviderExecutionResult, ProviderHealth


class PublicProfilesAdapter(BaseProviderAdapter):
    def __init__(self, transport=None):
        self.transport = transport

    def provider_id(self): return "github_public"
    def version(self): return "2022-11-28"
    def adapter_version(self): return "2.1.0"
    def capabilities(self): return ["PUBLIC_PROFILE_LOOKUP"]
    def network_class(self): return NetworkClass.THIRD_PARTY_ONLY
    def accepts(self): return [ObservableType.EMAIL, ObservableType.USERNAME]
    def produces(self): return [ObservableType.ACCOUNT, ObservableType.URL, ObservableType.USERNAME]
    def build_command(self, target): return []

    async def health(self):
        return ProviderHealth(state=ProviderState.READY_LIMITED, live_verified=False,
            provider_version=self.version(), credential_state="NOT_REQUIRED",
            message="Public GitHub profiles only; subject to API rate limits")

    async def execute(self, target, lineage, **kwargs):
        started = time.perf_counter()
        rows, requests, checked = [], 0, 0
        selected, incomplete, error = 0, False, None
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": self.version(),
                   "User-Agent": "SPIDER-public-footprint/2.1"}
        try:
            async with httpx.AsyncClient(base_url="https://api.github.com", headers=headers,
                    timeout=min(10, kwargs.get("timeout_seconds", 30)), follow_redirects=False,
                    transport=self.transport) as client:
                if target.type == ObservableType.EMAIL:
                    requests += 1
                    response = await client.get("/search/users", params={
                        "q": f'"{target.canonical_value}" in:email', "per_page": 10})
                    response.raise_for_status()
                    data = response.json()
                    if not isinstance(data.get("items"), list): raise ValueError("Invalid response")
                    logins = [r.get("login") for r in data["items"] if isinstance(r, dict)]
                    selected = data.get("total_count", len(logins))
                    incomplete = bool(data.get("incomplete_results")) or selected > len(logins)
                else:
                    logins, selected = [target.canonical_value], 1
                for login in logins[:10]:
                    if not isinstance(login, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", login):
                        incomplete = True
                        continue
                    requests += 1
                    response = await client.get(f"/users/{login}")
                    if response.status_code == 404:
                        checked += 1
                        continue
                    response.raise_for_status()
                    profile = response.json()
                    if str(profile.get("login", "")).casefold() != login.casefold():
                        incomplete = True
                        continue
                    checked += 1
                    public_email = profile.get("email")
                    exact = isinstance(public_email, str) and public_email.strip().casefold() == target.canonical_value.casefold()
                    if target.type == ObservableType.EMAIL and not exact: continue
                    # Store only supported public evidence fields, not full HTTP responses.
                    rows.append({"login": login, "platform": "GitHub",
                        "profile_url": f"https://github.com/{login}",
                        "display_name": str(profile.get("name") or "")[:200],
                        "bio": str(profile.get("bio") or "")[:1000],
                        "website": str(profile.get("blog") or "")[:500],
                        "match_basis": "exact_public_email" if exact else "username_only",
                        "identity_verified": False,
                        "public_email": public_email if exact else None})
        except httpx.HTTPStatusError as exc:
            error = "GitHub rate limited or denied the request" if exc.response.status_code in (403, 429) else "GitHub public profile request failed"
            incomplete = True
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            error, incomplete = "GitHub public profile response unavailable or invalid", True
        raw = json.dumps({"profiles": rows}, ensure_ascii=False).encode()
        observations = self.parse(raw, lineage)
        return ProviderExecutionResult(raw_content=raw, observations=observations,
            exit_code=1 if error and not rows else 0,
            outcome="PARTIAL" if incomplete else "COMPLETED", error_message=error,
            duration_ms=(time.perf_counter()-started)*1000,
            metadata={"requests": requests, "profiles_checked": checked,
                      "candidates_selected": selected, "incomplete": incomplete,
                      "scope": "GitHub public profiles"},
            raw_items_count=checked, accepted_count=len(observations))

    def parse(self, raw_content, lineage):
        observations = []
        try:
            rows = json.loads(raw_content).get("profiles", [])
        except (ValueError, AttributeError):
            return []
        for row in rows:
            login = row.get("login", "")
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", login): continue
            is_email = "@" in (lineage.parent_observable_value or "")
            if is_email and (row.get("match_basis") != "exact_public_email" or
                    str(row.get("public_email", "")).casefold() != lineage.parent_observable_value.casefold()): continue
            account = f"{login}@github"
            values = [(ObservableType.ACCOUNT, account, lineage.parent_observable_value),
                      (ObservableType.URL, f"https://github.com/{login}", account)]
            # An explicitly published email can provide a handle for the next depth.
            if is_email: values.append((ObservableType.USERNAME, login, account))
            for typ, value, parent in values:
                observations.append(Observation(observable=self.normalize({"type": typ, "value": value}),
                    lineage=lineage.model_copy(update={"upstream_source": "github_public_profile",
                        "upstream_family": "GITHUB_PUBLIC", "parent_observable_value": parent}),
                    confidence=0.95 if is_email else 0.80, raw_data=row))
        return observations

    def normalize(self, raw_item):
        return NormalizedObservable(type=raw_item["type"], value=raw_item["value"])
