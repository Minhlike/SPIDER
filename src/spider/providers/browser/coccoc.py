import asyncio
import json
import os
import re
import secrets
import time
import hashlib
from pathlib import Path
from urllib.parse import quote_plus, unquote, urlsplit, urlunsplit

from spider.models.budget import RequestBudgetExceeded
from spider.models.enums import NetworkClass, ObservableType, ProviderState
from spider.models.observable import NormalizedObservable
from spider.models.observation import Observation
from spider.models.base import utc_now
from spider.providers.base import BaseProviderAdapter, ProviderExecutionResult, ProviderHealth


DIRECT_USERNAME_SOURCES = (
    ("Facebook", "facebook.com", "https://www.facebook.com/{username}"),
    ("Instagram", "instagram.com", "https://www.instagram.com/{username}/"),
    ("Threads", "threads.com", "https://www.threads.com/@{username}"),
    ("TikTok", "tiktok.com", "https://www.tiktok.com/@{username}"),
    ("YouTube", "youtube.com", "https://www.youtube.com/@{username}"),
    ("LinkedIn", "linkedin.com", "https://www.linkedin.com/in/{username}"),
    ("GitHub", "github.com", "https://github.com/{username}"),
    ("X/Twitter", "x.com", "https://x.com/{username}"),
)
SEARCH_SOURCES = (("Zalo", "zalo.me"), ("Tinhte", "tinhte.vn"), ("VOZ", "voz.vn"))
SEARCH_ENGINE_NAME = "Cốc Cốc Search"
SEARCH_ENGINE_URL = "https://coccoc.com/search?query={query}"
SEARCH_FALLBACK_SOURCES = frozenset({"Instagram", "Threads", "TikTok"})
ALLOWED_RESULT_HOSTS = frozenset(
    [host for _, host, _ in DIRECT_USERNAME_SOURCES] + [host for _, host in SEARCH_SOURCES]
)
NEGATIVE_MARKERS = (
    "page not found", "profile not found", "account not found", "doesn't exist",
    "isn't available", "không tìm thấy trang", "nội dung này hiện không dùng được",
)
LOGIN_MARKERS = ("log in", "login", "đăng nhập")
RATE_LIMIT_MARKERS = ("too many requests", "rate limit", "try again later", "thử lại sau")
CHALLENGE_MARKERS = ("captcha", "verify you are human", "security check", "kiểm tra bảo mật")
FATAL_BROWSER_REASONS = frozenset({
    "PROFILE_IN_USE", "MISSING_RUNTIME", "BROWSER_CLOSED", "BROWSER_START_FAILED",
    "BROWSER_NETWORK_UNAVAILABLE",
})


def coccoc_installation():
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    candidates = [
        local / "CocCoc/Browser/Application/browser.exe",
        Path(os.environ.get("ProgramFiles", "")) / "CocCoc/Browser/Application/browser.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "CocCoc/Browser/Application/browser.exe",
    ]
    executable = next((path for path in candidates if path.is_file()), None)
    return executable, local / "CocCoc/Browser/User Data"


def coccoc_profile(user_data: Path) -> str:
    try:
        state = json.loads((user_data / "Local State").read_text(encoding="utf-8"))
        name = state.get("profile", {}).get("last_used", "Default")
    except (OSError, ValueError, TypeError):
        name = "Default"
    if not isinstance(name, str) or not re.fullmatch(r"(?:Default|Profile \d+)", name):
        name = "Default"
    return name if (user_data / name).is_dir() else "Default"


def host_matches(url, expected_host):
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").casefold()
        if parsed.scheme not in ("http", "https") or parsed.username or parsed.password:
            return False
        if parsed.port not in (None, 80, 443):
            return False
    except (ValueError, TypeError):
        return False
    return host == expected_host or host.endswith("." + expected_host)


def safe_result_url(url):
    try:
        parsed = urlsplit(url)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname
                or parsed.username or parsed.password or parsed.port not in (None, 80, 443)):
            return None
        netloc = parsed.hostname + (f":{parsed.port}" if parsed.port else "")
        return urlunsplit((parsed.scheme, netloc, parsed.path or "/", "", ""))
    except (ValueError, TypeError):
        return None


def coccoc_search_url(query: str) -> str:
    """Build the public Cốc Cốc Search URL without retaining the query in evidence."""
    return SEARCH_ENGINE_URL.format(query=quote_plus(query))


def candidate_has_username(url: str, username: str) -> bool:
    """Require an exact profile route, never a substring or post route."""
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").casefold()
        parts = [part.casefold() for part in unquote(parsed.path).split("/") if part]
    except (TypeError, ValueError):
        return False
    username_key = username.lstrip("@").casefold()
    if not username_key:
        return False
    if host_matches(url, "linkedin.com"):
        return len(parts) == 2 and parts == ["in", username_key]
    if host_matches(url, "instagram.com") or host_matches(url, "facebook.com") \
            or host_matches(url, "github.com") or host_matches(url, "x.com"):
        return parts == [username_key]
    if host_matches(url, "threads.com") or host_matches(url, "tiktok.com") \
            or host_matches(url, "youtube.com"):
        return parts == [f"@{username_key}"]
    if host_matches(url, "zalo.me"):
        return parts == [username_key]
    return False


def indexed_profile_candidates(links, username: str) -> dict[str, str]:
    """Keep only public profile-shaped URLs for the priority social sites."""
    candidates = {}
    for source, host, _ in DIRECT_USERNAME_SOURCES:
        if source not in SEARCH_FALLBACK_SOURCES:
            continue
        for link in links:
            safe = safe_result_url(link)
            if safe and host_matches(safe, host) and candidate_has_username(safe, username):
                candidates.setdefault(source, safe)
                break
    return candidates


def select_search_candidate(links, host: str, identifier: str, require_text=False):
    """Select a host result using link-local text, never the SERP query echo."""
    identifier_key = identifier.casefold()
    for item in links:
        href = item.get("href") if isinstance(item, dict) else item
        anchor_text = item.get("text", "") if isinstance(item, dict) else ""
        safe = safe_result_url(href)
        if not safe or not host_matches(safe, host):
            continue
        if require_text and identifier_key not in f"{unquote(safe)}\n{anchor_text}".casefold():
            continue
        return safe
    return None


def apply_indexed_profile_candidates(rows, candidates, search_outcome):
    """Use search only as a lower-confidence fallback, never to erase a definite absence."""
    merged = []
    for row in rows:
        result = dict(row)
        source = result.get("source")
        candidate = candidates.get(source)
        if (candidate and result.get("state") not in {"NOT_FOUND", "CANDIDATE"}
                and source in SEARCH_FALLBACK_SOURCES):
            result["search_fallback_outcome"] = "COCCOC_SEARCH_RESULT"
            merged.append(result)
            merged.append({"kind": "search_lead", "source": source,
                           "state": "CANDIDATE", "reason": "COCCOC_SEARCH_RESULT",
                           "url": candidate, "account_candidate": False,
                           "search_engine": SEARCH_ENGINE_NAME,
                           "direct_outcome": row.get("state"),
                           "direct_reason": row.get("reason")})
            continue
        elif source in SEARCH_FALLBACK_SOURCES:
            result["search_fallback_outcome"] = search_outcome
        merged.append(result)
    return merged


def classify_direct_candidate(expected_host: str, username: str, status: int | None,
                              final_url: str, title: str, body: str) -> str:
    return classify_direct_result(expected_host, username, status, final_url, title, body)[0]


def classify_direct_result(expected_host: str, username: str, status: int | None,
                           final_url: str, title: str, body: str,
                           declared_urls=()) -> tuple[str, str]:
    text = f"{title}\n{body[:100000]}".casefold()
    if status == 429 or any(marker in text for marker in RATE_LIMIT_MARKERS):
        return "RATE_LIMITED", "RATE_LIMIT"
    if status in (401, 403) or any(marker in text for marker in CHALLENGE_MARKERS):
        return "BLOCKED", "CHALLENGE_OR_ACCESS_DENIED"
    if status in (404, 410):
        return "NOT_FOUND", "HTTP_NOT_FOUND"
    try:
        path = unquote(urlsplit(final_url).path).casefold()
    except ValueError:
        return "UNKNOWN", "INVALID_FINAL_URL"
    login_surface = f"{title}\n{urlsplit(final_url).path}".casefold()
    if any(marker in login_surface for marker in LOGIN_MARKERS):
        return "LOGIN_REQUIRED", "LOGIN_WALL"
    if (status is not None and 200 <= status < 400
            and any(marker in text for marker in NEGATIVE_MARKERS)):
        return "NOT_FOUND", "NEGATIVE_PAGE_MARKER"
    if (status is not None and 200 <= status < 400 and host_matches(final_url, expected_host)
            and candidate_has_username(final_url, username)
            and username.lstrip("@").casefold() in text):
        return "CANDIDATE", "PROFILE_PAGE_SIGNALS"
    return "UNKNOWN", "INSUFFICIENT_PAGE_SIGNALS"


def apply_negative_control(row, control_state):
    result = {**row, "control_state": control_state}
    if control_state == "NOT_FOUND":
        result.update(state="CANDIDATE", reason="NEGATIVE_CONTROL_DIFFERENTIAL")
    elif control_state == "CANDIDATE":
        result["reason"] = "NON_UNIQUE_RESPONSE"
    return result


def browser_start_reason(exc: BaseException) -> str:
    """Return a fixed, non-sensitive browser start state for the UI and audit."""
    text = str(exc).casefold()
    if any(marker in text for marker in ("already in use", "singleton", "user data directory", "profile in use")):
        return "PROFILE_IN_USE"
    if any(marker in text for marker in ("executable doesn't exist", "executable not found")):
        return "MISSING_RUNTIME"
    if "browser has been closed" in text or "target page, context or browser has been closed" in text:
        return "BROWSER_CLOSED"
    return "BROWSER_START_FAILED"


class CocCocBrowserAdapter(BaseProviderAdapter):
    request_budget_supported = True

    def provider_id(self): return "coccoc_browser"
    def version(self): return "local-coccoc"
    def adapter_version(self): return "1.3.0"
    def capabilities(self): return ["BROWSER_PERSONAL_DISCOVERY"]
    def network_class(self): return NetworkClass.THIRD_PARTY_ONLY
    def accepts(self): return [ObservableType.EMAIL, ObservableType.USERNAME]
    def produces(self): return [ObservableType.ACCOUNT, ObservableType.URL]
    def build_command(self, target): return []

    async def health(self):
        executable, user_data = coccoc_installation()
        ready = bool(executable and user_data.is_dir())
        return ProviderHealth(
            state=ProviderState.READY_LIMITED if ready else ProviderState.MISSING_RUNTIME,
            runtime_path=str(executable) if executable else None,
            runtime_exists=ready,
            live_verified=False,
            message=("Cốc Cốc is available; signed-in search requires explicit user action"
                     if ready else "Cốc Cốc executable or user profile was not found"),
        )

    async def _collect(self, target, options):
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return [], "MISSING_RUNTIME"
        executable, user_data = coccoc_installation()
        if not executable or not user_data.is_dir():
            return [], "MISSING_RUNTIME"

        ledger, budget = options.get("request_ledger"), options.get("execution_budget")
        recorder = options.get("egress_recorder")
        exhausted = False
        receipts, finish_tasks = {}, []
        leases = {}
        origin_limits = options.get("origin_limits")

        async with async_playwright() as playwright:
            context = None
            try:
                context = await playwright.chromium.launch_persistent_context(
                    str(user_data), executable_path=str(executable), headless=False,
                    accept_downloads=False, service_workers="block",
                    args=[f"--profile-directory={coccoc_profile(user_data)}"],
                )
                await context.add_init_script("""
                    window.WebSocket = class { constructor() { throw new Error('disabled by request budget'); } };
                    window.EventSource = class { constructor() { throw new Error('disabled by request budget'); } };
                    navigator.sendBeacon = () => false;
                """)

                async def intercept(route):
                    nonlocal exhausted
                    request = route.request
                    if request.resource_type in {"image", "media", "font"}:
                        await route.abort()
                        return
                    if origin_limits:
                        leases[id(request)] = await origin_limits.acquire(urlsplit(request.url).hostname or "unknown")
                    try:
                        if ledger is not None:
                            ledger.request(budget, self.provider_id(), "HTTP", "browser_navigation")
                    except RequestBudgetExceeded:
                        lease = leases.pop(id(request), None)
                        if lease:
                            lease.release()
                        exhausted = True
                        await route.abort()
                        return
                    if recorder:
                        host = (urlsplit(request.url).hostname or "unknown").casefold()
                        receipts[id(request)] = await recorder.begin(
                            host, "browser_personal_discovery", credentialed=True
                        )
                    await route.continue_()

                async def finish(request, outcome):
                    if origin_limits and outcome == "HTTP_429":
                        origin_limits.feedback(urlsplit(request.url).hostname or "unknown", 429)
                    receipt = receipts.pop(id(request), None)
                    if receipt and recorder:
                        await recorder.finish(receipt, outcome)

                def release(request):
                    lease = leases.pop(id(request), None)
                    if lease:
                        lease.release()

                context.on("requestfinished", release)
                context.on("requestfailed", release)
                context.on("response", lambda response: finish_tasks.append(
                    asyncio.create_task(finish(response.request, f"HTTP_{response.status}"))))
                context.on("requestfailed", lambda request: finish_tasks.append(
                    asyncio.create_task(finish(request, "NETWORK_ERROR"))))
                await context.route("http://**/*", intercept)
                await context.route("https://**/*", intercept)
                # This is a fresh persistent context launched by SPIDER.  Close
                # its default tab before opening work so direct checks can never
                # exceed the three SPIDER-owned tab budget.
                for initial in list(context.pages):
                    await initial.close()
                rows = []
                timeout_ms = int(min(15, max(3, options.get("timeout_seconds", 180) / 12)) * 1000)

                if target.type == ObservableType.USERNAME:
                    username = target.canonical_value.lstrip("@")
                    parallel_tabs = min(3, max(1, int(options.get("browser_parallel_tabs", 3))))
                    direct_rows = await self._collect_direct_sources(
                        context, username, timeout_ms, lambda: exhausted, parallel_tabs
                    )
                    if not exhausted:
                        page = await context.new_page()
                        try:
                            direct_rows = await self._search_direct_fallbacks(
                                page, username, direct_rows, lambda: exhausted, timeout_ms
                            )
                        finally:
                            await page.close()
                        direct_rows = await self._revalidate_search_leads(
                            context, username, direct_rows, lambda: exhausted, timeout_ms,
                            parallel_tabs
                        )
                        rows.extend(direct_rows)
                        page = await context.new_page()
                        try:
                            rows.extend(await self._search_sources(
                                page, username, lambda: exhausted, timeout_ms))
                        finally:
                            await page.close()
                    else:
                        rows.extend(direct_rows)
                else:
                    page = await context.new_page()
                    sources = tuple((source, host) for source, host, _ in DIRECT_USERNAME_SOURCES) + SEARCH_SOURCES
                    try:
                        for source, host in sources:
                            if exhausted:
                                break
                            rows.append(await self._search_one(
                                page, source, host, target.canonical_value, timeout_ms, require_text=True
                            ))
                    finally:
                        await page.close()
                return rows, "REQUEST_LIMIT" if exhausted else None
            except Exception as exc:
                # Do not put Playwright/profile paths or browser diagnostics in
                # a case report, an API response, or a log artifact.
                return [], browser_start_reason(exc)
            finally:
                if context is not None:
                    try:
                        await context.close()
                    except Exception:
                        pass
                await asyncio.sleep(0)
                if finish_tasks:
                    await asyncio.gather(*finish_tasks, return_exceptions=True)
                for lease in list(leases.values()):
                    lease.release()
                if recorder:
                    for receipt in list(receipts.values()):
                        await recorder.finish(receipt, "NO_RESPONSE")

    async def _collect_direct_sources(self, context, username, timeout_ms,
                                      is_exhausted, parallel_tabs=3):
        semaphore = asyncio.Semaphore(min(3, max(1, int(parallel_tabs))))

        async def inspect(definition):
            source, host, template = definition
            async with semaphore:
                if is_exhausted():
                    return {"kind": "site", "source": source, "state": "UNPROCESSED",
                            "reason": "REQUEST_LIMIT", "url": None, "http_status": None}
                requested_url = template.format(username=username)
                row = await self._inspect_direct_source(
                    context, source, host, username, requested_url, timeout_ms
                )
                # A control is sequential with its target so each origin sees at
                # most one active SPIDER tab even while other origins proceed.
                if (row["state"] == "UNKNOWN" and
                        row["reason"] == "INSUFFICIENT_PAGE_SIGNALS" and
                        isinstance(row.get("http_status"), int) and
                        200 <= row["http_status"] < 400 and not is_exhausted()):
                    control = "spidercheck" + secrets.token_hex(8)
                    control_row = await self._inspect_direct_source(
                        context, source, host, control,
                        template.format(username=control), timeout_ms
                    )
                    row = apply_negative_control(row, control_row["state"])
                return row

        return list(await asyncio.gather(*(inspect(item) for item in DIRECT_USERNAME_SOURCES)))

    async def _inspect_direct_source(self, context, source, host, username, requested_url,
                                     timeout_ms):
        page, status = None, None
        try:
            page = await context.new_page()
            try:
                response = await page.goto(requested_url, wait_until="domcontentloaded",
                                           timeout=timeout_ms)
            except Exception as exc:
                return {"kind": "site", "source": source, "state": "NETWORK_ERROR",
                        "reason": "NAVIGATION_TIMEOUT" if exc.__class__.__name__ == "TimeoutError"
                                  else "NAVIGATION_ERROR",
                        "url": requested_url, "http_status": None}
            status = response.status if response else None
            try:
                await page.wait_for_timeout(1200)
                title = await page.title()
            except Exception:
                title = ""
            try:
                body = await page.locator("body").inner_text(timeout=3000)
            except Exception:
                body = ""
            final_url = page.url
            try:
                declared_urls = await page.locator(
                    'meta[property="og:url"], link[rel="canonical"]'
                ).evaluate_all("els => els.slice(0, 10).map(el => el.content || el.href || '')")
            except Exception:
                declared_urls = []
            state, reason = classify_direct_result(
                host, username, status, final_url, title, body, declared_urls
            )
        except Exception:
            final_url = requested_url
            state, reason = "UNKNOWN", "BROWSER_ERROR"
        finally:
            if page is not None:
                try:
                    await page.close()
                except Exception:
                    pass
        return {"kind": "site", "source": source, "state": state,
                "reason": reason,
                "url": safe_result_url(final_url) if state == "CANDIDATE" else requested_url,
                "http_status": status,
                "content_sha256": hashlib.sha256(f"{title}\n{body}".encode("utf-8", "replace")).hexdigest()}

    async def _search_sources(self, page, identifier, is_exhausted, timeout_ms):
        rows = []
        for source, host in SEARCH_SOURCES:
            if is_exhausted():
                break
            rows.append(await self._search_one(page, source, host, identifier, timeout_ms))
        return rows

    async def _search_direct_fallbacks(self, page, username, direct_rows, is_exhausted, timeout_ms):
        """Recover index-visible social profiles when a direct platform page is unreadable.

        The search result is deliberately a candidate, not proof that the same
        person owns the account.  It is safe to retain a platform's explicit
        NOT_FOUND result over an index entry, which may be stale.
        """
        if is_exhausted():
            return apply_indexed_profile_candidates(direct_rows, {}, "REQUEST_LIMIT")
        try:
            await page.goto(coccoc_search_url(f'"{username}"'), wait_until="domcontentloaded",
                            timeout=min(timeout_ms, 8000))
            links = await page.locator("a[href]").evaluate_all(
                "els => els.slice(0, 500).map(a => ({href: a.href, text: a.innerText || a.textContent || ''}))"
            )
        except Exception:
            return apply_indexed_profile_candidates(direct_rows, {}, "SEARCH_ENGINE_UNAVAILABLE")
        candidates = indexed_profile_candidates(links, username)
        return apply_indexed_profile_candidates(
            direct_rows, candidates, "COCCOC_SEARCH_RESULT" if candidates else "NO_EXACT_SEARCH_RESULT"
        )

    async def _revalidate_search_leads(self, context, username, rows, is_exhausted,
                                       timeout_ms, parallel_tabs=3):
        """Open exact indexed profile routes before promoting a lead to ACCOUNT."""
        leads = [dict(row) for row in rows if row.get("kind") == "search_lead"]
        direct = [dict(row) for row in rows if row.get("kind") != "search_lead"]
        positions = {row.get("source"): index for index, row in enumerate(direct)}
        hosts = {source: host for source, host, _ in DIRECT_USERNAME_SOURCES}
        semaphore = asyncio.Semaphore(min(3, max(1, int(parallel_tabs))))

        async def inspect(lead):
            lead["account_candidate"] = False
            if is_exhausted():
                lead.update(revalidation_state="UNPROCESSED",
                            revalidation_reason="REQUEST_LIMIT")
                return lead, None
            source, candidate = lead.get("source"), safe_result_url(lead.get("url"))
            if source not in hosts or not candidate or not candidate_has_username(candidate, username):
                lead.update(revalidation_state="UNKNOWN",
                            revalidation_reason="INVALID_PROFILE_ROUTE")
                return lead, None
            async with semaphore:
                checked = await self._inspect_direct_source(
                    context, source, hosts[source], username, candidate, timeout_ms)
            lead.update(revalidation_state=checked.get("state", "UNKNOWN"),
                        revalidation_reason=checked.get("reason", "NOT_YET_VERIFIED"))
            if checked.get("state") != "CANDIDATE":
                return lead, None
            checked.update(kind="site", reason="SEARCH_LEAD_REVALIDATED",
                           search_lead_url=candidate, search_engine=SEARCH_ENGINE_NAME,
                           account_candidate=True,
                           direct_outcome=lead.get("direct_outcome"),
                           direct_reason=lead.get("direct_reason"))
            return lead, checked

        checked = await asyncio.gather(*(inspect(lead) for lead in leads))
        output_leads = []
        for lead, promoted in checked:
            output_leads.append(lead)
            if promoted is not None and promoted.get("source") in positions:
                direct[positions[promoted["source"]]] = promoted
        return direct + output_leads

    async def _search_one(self, page, source, host, identifier, timeout_ms, require_text=False):
        query = f'site:{host} "{identifier}"'
        try:
            await page.goto(coccoc_search_url(query),
                            wait_until="domcontentloaded", timeout=timeout_ms)
            page_text = (await page.locator("body").inner_text(timeout=2000)).casefold()
            links = await page.locator("a[href]").evaluate_all(
                "els => els.slice(0, 500).map(a => a.href)"
            )
        except Exception:
            return {"kind": "site", "source": source, "state": "UNKNOWN",
                    "reason": "SEARCH_ENGINE_UNAVAILABLE", "url": None,
                    "search_engine": SEARCH_ENGINE_NAME,
                    "content_sha256": hashlib.sha256(b"").hexdigest()}
        candidate = select_search_candidate(links, host, identifier, require_text)
        valid = candidate is not None
        return {"kind": "search_lead" if valid else "site", "source": source,
                "state": "CANDIDATE" if valid else "UNKNOWN",
                "reason": "COCCOC_SEARCH_RESULT" if valid else "NO_EXACT_SEARCH_RESULT",
                "url": safe_result_url(candidate) if valid else None,
                "account_candidate": False,
                "profile_shaped": bool(valid and candidate_has_username(candidate, identifier)),
                "search_engine": SEARCH_ENGINE_NAME,
                "content_sha256": hashlib.sha256(page_text.encode("utf-8", "replace")).hexdigest()}

    @staticmethod
    def _workflow_steps(rows, lineage, parent_observation_id=None, action_id=None):
        """Trace only SPIDER-owned browser work; no cookies, query string or page text."""
        timestamp = utc_now().isoformat()
        return [{"action_id": (action_id or lineage.configuration_hash)[:128], "parent_observation_id": parent_observation_id,
                "step": "REVALIDATE_PROFILE" if row.get("reason") == "SEARCH_LEAD_REVALIDATED"
                         else "SEARCH_INDEX" if row.get("reason") == "COCCOC_SEARCH_RESULT"
                         else "READ_PROFILE" if row.get("source") in {name for name, _, _ in DIRECT_USERNAME_SOURCES}
                         else "SEARCH_INDEX", "source": row.get("source", "unknown")[:64],
                 "sanitized_url": safe_result_url(row.get("url")) if row.get("url") else None,
                 "observed_at": timestamp,
                 "content_sha256": row.get("content_sha256") or hashlib.sha256(b"").hexdigest(),
                 "state": row.get("state", "UNKNOWN"), "reason": row.get("reason", "NOT_YET_VERIFIED")}
                for row in rows]

    async def execute(self, target, lineage, **kwargs):
        started = time.perf_counter()
        rows, reason = await self._collect(target, kwargs)
        workflow_steps = self._workflow_steps(rows, lineage, kwargs.get("browser_parent_observation_id"),
                                              kwargs.get("browser_action_id"))
        raw = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows).encode("utf-8")
        observations = self.parse(raw, lineage)
        site_rows = [row for row in rows if row.get("kind") != "search_lead"]
        search_only_names = {source for source, _ in SEARCH_SOURCES}
        search_only_leads = [row for row in rows if row.get("kind") == "search_lead"
                             and row.get("source") in search_only_names]
        selected = len(DIRECT_USERNAME_SOURCES) + len(SEARCH_SOURCES)
        candidates = sum(row.get("state") == "CANDIDATE" and row.get("kind") != "search_lead"
                         for row in rows)
        not_found = sum(row.get("state") == "NOT_FOUND" for row in site_rows)
        checked = min(selected, len(site_rows) + len({row.get("source") for row in search_only_leads}))
        unprocessed = sum(row.get("state") == "UNPROCESSED" for row in site_rows) + max(0, selected - checked)
        undecided = len(site_rows) - sum(row.get("state") == "CANDIDATE" for row in site_rows) \
            - not_found - sum(row.get("state") == "UNPROCESSED" for row in site_rows) \
            + len(search_only_leads)
        controls = [row.get("control_state") for row in site_rows if "control_state" in row]
        fallback_outcomes = [row.get("search_fallback_outcome") for row in site_rows
                             if row.get("source") in SEARCH_FALLBACK_SOURCES]
        fallback_outcome = ("SEARCH_LEAD_REVALIDATED" if any(
                                row.get("reason") == "SEARCH_LEAD_REVALIDATED"
                                and row.get("source") in SEARCH_FALLBACK_SOURCES for row in rows)
                            else "COCCOC_SEARCH_RESULT" if any(
                                row.get("reason") == "COCCOC_SEARCH_RESULT"
                                and row.get("source") in SEARCH_FALLBACK_SOURCES for row in rows)
                            else "SEARCH_ENGINE_UNAVAILABLE" if "SEARCH_ENGINE_UNAVAILABLE" in fallback_outcomes
                            else "NO_EXACT_SEARCH_RESULT" if fallback_outcomes else "NOT_RUN")
        coverage = {"selected": selected, "checked": checked, "found": candidates,
                    "not_found": not_found, "unknown": undecided,
                    "unprocessed": unprocessed,
                    "controls_pending": 0,
                    "controls_unknown": sum(state not in {"CANDIDATE", "NOT_FOUND"}
                                            for state in controls),
                    "non_unique_detections": sum(row.get("reason") == "NON_UNIQUE_RESPONSE"
                                                 for row in rows),
                    "parallel_tabs": min(3, max(1, int(kwargs.get("browser_parallel_tabs", 3)))),
                    "source_scope": "VN_COMMON_BROWSER",
                    "search_discovery": {"engine": SEARCH_ENGINE_NAME, "outcome": fallback_outcome,
                                         "candidate_profiles": sum(row.get("reason") == "SEARCH_LEAD_REVALIDATED"
                                                                   for row in rows),
                                         "unverified_leads": sum(row.get("reason") == "COCCOC_SEARCH_RESULT"
                                                                 for row in rows)},
                    "priority_sites": {row.get("source", "unknown"): {
                        "outcome": row.get("state", "UNKNOWN"),
                        "reason": row.get("reason", "NOT_YET_VERIFIED")
                    } for row in site_rows + search_only_leads}}
        fatal_browser_failure = reason in FATAL_BROWSER_REASONS
        complete = reason is None and len(site_rows) == selected and undecided == 0
        if reason is None and not complete:
            reason = "UNRESOLVED_SOURCES"
        errors = {"PROFILE_IN_USE": "Cốc Cốc đang mở với profile này; hãy đóng Cốc Cốc rồi chạy lại để SPIDER mở các tab điều tra.",
                  "MISSING_RUNTIME": "Cốc Cốc runtime unavailable",
                  "BROWSER_CLOSED": "Cốc Cốc đã đóng trước khi hoàn tất kiểm tra.",
                  "BROWSER_START_FAILED": "Không thể khởi động phiên Cốc Cốc cho lượt kiểm tra này.",
                  "BROWSER_NETWORK_UNAVAILABLE": "Phiên Cốc Cốc không truy cập được trang kiểm tra công khai. Không kết luận về username; hãy kiểm tra kết nối của Cốc Cốc rồi chạy lại.",
                  "REQUEST_LIMIT": "Browser request budget exhausted",
                  "UNRESOLVED_SOURCES": "Some browser sources could not be decided automatically"}
        return ProviderExecutionResult(
            raw_content=raw, observations=observations, exit_code=0 if complete else 1,
            outcome="COMPLETED" if complete else "FAILED" if fatal_browser_failure else "PARTIAL",
            error_message=None if complete else errors.get(reason, "Browser discovery incomplete"),
            metadata={"coverage": coverage, "budget_reason": reason,
                      "browser_workflow": {"version": "1", "owned_tabs_max": 3,
                          "owned_tabs_closed": True, "automatic_replay": False,
                          "resume": "NEW_EXPLICIT_ACTION_REQUIRED" if reason else "NOT_REQUIRED",
                          "steps": workflow_steps}},
            mime_type="application/x-ndjson", duration_ms=(time.perf_counter() - started) * 1000,
            raw_items_count=len(rows), accepted_count=len(observations),
        )

    def parse(self, raw_content, lineage):
        results = []
        for line in raw_content.decode("utf-8", errors="replace").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            url = safe_result_url(row.get("url"))
            if row.get("state") != "CANDIDATE" or not isinstance(url, str):
                continue
            if not any(host_matches(url, host) for host in ALLOWED_RESULT_HOSTS):
                continue
            is_search_lead = row.get("reason") == "COCCOC_SEARCH_RESULT"
            is_revalidated = row.get("reason") == "SEARCH_LEAD_REVALIDATED"
            evidence = {"platform": row.get("source"), "profile_url": url,
                        "match_basis": "coccoc_search_lead_revalidated" if is_revalidated
                                       else "coccoc_search_lead" if is_search_lead
                                       else "signed_in_browser_candidate",
                        "identity_verified": False,
                        "verification_state": "PROFILE_ROUTE_REVALIDATED_IDENTITY_UNVERIFIED"
                                              if is_revalidated else "SEARCH_LEAD_ONLY"
                                              if is_search_lead else "CANDIDATE_REVIEW_REQUIRED",
                        "browser": "Cốc Cốc",
                        "search_engine": row.get("search_engine") if is_search_lead or is_revalidated else None}
            item_lineage = lineage.model_copy(update={"upstream_source": "coccoc_browser",
                "upstream_family": "BROWSER_ASSISTED"})
            if (lineage.parent_observable_type == ObservableType.USERNAME
                    and not is_search_lead and row.get("account_candidate") is not False):
                account = f"{lineage.parent_observable_value}@{str(row.get('source', '')).casefold()}"
                account_lineage = item_lineage.model_copy(update={
                    "parent_observable_value": url if is_revalidated else lineage.parent_observable_value,
                    "parent_observable_type": ObservableType.URL if is_revalidated else ObservableType.USERNAME,
                    "parent_namespace": "" if is_revalidated else lineage.parent_namespace})
                results.append(Observation(
                    observable=self.normalize({"type": ObservableType.ACCOUNT, "value": account,
                                               "namespace": str(row.get("source", "")).casefold()}),
                    lineage=account_lineage, confidence=0.70 if is_revalidated else 0.55,
                    raw_data=evidence))
            results.append(Observation(
                observable=self.normalize({"type": ObservableType.URL, "value": url}),
                lineage=item_lineage, confidence=0.55, raw_data=evidence))
        return results

    def normalize(self, raw_item):
        return NormalizedObservable(type=raw_item["type"], value=raw_item["value"],
                                    namespace=raw_item.get("namespace", ""))
