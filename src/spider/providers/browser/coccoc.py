import asyncio
import json
import os
import re
import secrets
import time
from pathlib import Path
from urllib.parse import quote_plus, unquote, urlsplit, urlunsplit

from spider.models.budget import RequestBudgetExceeded
from spider.models.enums import NetworkClass, ObservableType, ProviderState
from spider.models.observable import NormalizedObservable
from spider.models.observation import Observation
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


def classify_direct_candidate(expected_host: str, username: str, status: int | None,
                              final_url: str, title: str, body: str) -> str:
    return classify_direct_result(expected_host, username, status, final_url, title, body)[0]


def classify_direct_result(expected_host: str, username: str, status: int | None,
                           final_url: str, title: str, body: str,
                           declared_urls=()) -> tuple[str, str]:
    if status in (404, 410):
        return "NOT_FOUND", "HTTP_NOT_FOUND"
    text = f"{title}\n{body[:100000]}".casefold()
    if any(marker in text for marker in NEGATIVE_MARKERS):
        return "NOT_FOUND", "NEGATIVE_PAGE_MARKER"
    if status == 429 or any(marker in text for marker in RATE_LIMIT_MARKERS):
        return "RATE_LIMITED", "RATE_LIMIT"
    if status in (401, 403) or any(marker in text for marker in CHALLENGE_MARKERS):
        return "BLOCKED", "CHALLENGE_OR_ACCESS_DENIED"
    try:
        path = unquote(urlsplit(final_url).path).casefold()
    except ValueError:
        return "UNKNOWN", "INVALID_FINAL_URL"
    login_surface = f"{title}\n{urlsplit(final_url).path}".casefold()
    if any(marker in login_surface for marker in LOGIN_MARKERS):
        return "LOGIN_REQUIRED", "LOGIN_WALL"
    username_key = username.casefold()
    declared_match = any(
        isinstance(url, str) and host_matches(url, expected_host)
        and username_key in unquote(urlsplit(url).path).casefold()
        for url in declared_urls
    )
    if (status is not None and 200 <= status < 400 and host_matches(final_url, expected_host)
            and username_key in path and (username_key in text or declared_match)):
        return "CANDIDATE", "PROFILE_PAGE_SIGNALS"
    return "UNKNOWN", "INSUFFICIENT_PAGE_SIGNALS"


def apply_negative_control(row, control_state):
    result = {**row, "control_state": control_state}
    if control_state == "NOT_FOUND":
        result.update(state="CANDIDATE", reason="NEGATIVE_CONTROL_DIFFERENTIAL")
    elif control_state == "CANDIDATE":
        result["reason"] = "NON_UNIQUE_RESPONSE"
    return result


class CocCocBrowserAdapter(BaseProviderAdapter):
    request_budget_supported = True

    def provider_id(self): return "coccoc_browser"
    def version(self): return "local-coccoc"
    def adapter_version(self): return "1.0.0"
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
                page = context.pages[0] if context.pages else await context.new_page()
                rows = []
                timeout_ms = int(min(15, max(3, options.get("timeout_seconds", 180) / 12)) * 1000)

                if target.type == ObservableType.USERNAME:
                    username = target.canonical_value.lstrip("@")
                    parallel_tabs = min(3, max(1, int(options.get("browser_parallel_tabs", 3))))
                    rows.extend(await self._collect_direct_sources(
                        context, username, timeout_ms, lambda: exhausted, parallel_tabs
                    ))
                    rows.extend(await self._search_sources(page, username, lambda: exhausted, timeout_ms))
                else:
                    sources = tuple((source, host) for source, host, _ in DIRECT_USERNAME_SOURCES) + SEARCH_SOURCES
                    for source, host in sources:
                        if exhausted:
                            break
                        rows.append(await self._search_one(
                            page, source, host, target.canonical_value, timeout_ms, require_text=True
                        ))
                return rows, "REQUEST_LIMIT" if exhausted else None
            except Exception:
                return [], "PROFILE_UNAVAILABLE"
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
                "http_status": status}

    async def _search_sources(self, page, identifier, is_exhausted, timeout_ms):
        rows = []
        for source, host in SEARCH_SOURCES:
            if is_exhausted():
                break
            rows.append(await self._search_one(page, source, host, identifier, timeout_ms))
        return rows

    async def _search_one(self, page, source, host, identifier, timeout_ms, require_text=False):
        query = quote_plus(f'site:{host} "{identifier}"')
        try:
            await page.goto(f"https://www.bing.com/search?q={query}",
                            wait_until="domcontentloaded", timeout=timeout_ms)
            page_text = (await page.locator("body").inner_text(timeout=2000)).casefold()
            links = await page.locator("a[href]").evaluate_all(
                "els => els.slice(0, 500).map(a => a.href)"
            )
        except Exception:
            page_text, links = "", []
        candidate = next((url for url in links if host_matches(url, host)), None)
        valid = bool(candidate and (not require_text or identifier.casefold() in page_text))
        return {"kind": "site", "source": source,
                "state": "CANDIDATE" if valid else "UNKNOWN",
                "reason": "EXACT_SEARCH_RESULT" if valid else "NO_EXACT_SEARCH_RESULT",
                "url": safe_result_url(candidate) if valid else None}

    async def execute(self, target, lineage, **kwargs):
        started = time.perf_counter()
        rows, reason = await self._collect(target, kwargs)
        raw = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows).encode("utf-8")
        observations = self.parse(raw, lineage)
        selected = len(DIRECT_USERNAME_SOURCES) + len(SEARCH_SOURCES)
        candidates = sum(row.get("state") == "CANDIDATE" for row in rows)
        not_found = sum(row.get("state") == "NOT_FOUND" for row in rows)
        unprocessed = sum(row.get("state") == "UNPROCESSED" for row in rows) + max(0, selected - len(rows))
        undecided = len(rows) - candidates - not_found - sum(
            row.get("state") == "UNPROCESSED" for row in rows)
        controls = [row.get("control_state") for row in rows if "control_state" in row]
        coverage = {"selected": selected, "checked": len(rows), "found": candidates,
                    "not_found": not_found, "unknown": undecided,
                    "unprocessed": unprocessed,
                    "controls_pending": 0,
                    "controls_unknown": sum(state not in {"CANDIDATE", "NOT_FOUND"}
                                            for state in controls),
                    "non_unique_detections": sum(row.get("reason") == "NON_UNIQUE_RESPONSE"
                                                 for row in rows),
                    "parallel_tabs": min(3, max(1, int(kwargs.get("browser_parallel_tabs", 3)))),
                    "source_scope": "VN_COMMON_BROWSER",
                    "priority_sites": {row.get("source", "unknown"): {
                        "outcome": row.get("state", "UNKNOWN"),
                        "reason": row.get("reason", "NOT_YET_VERIFIED")
                    } for row in rows}}
        complete = reason is None and len(rows) == selected and undecided == 0
        if reason is None and not complete:
            reason = "UNRESOLVED_SOURCES"
        errors = {"PROFILE_UNAVAILABLE": "Cốc Cốc profile is unavailable or already open",
                  "MISSING_RUNTIME": "Cốc Cốc runtime unavailable",
                  "REQUEST_LIMIT": "Browser request budget exhausted",
                  "UNRESOLVED_SOURCES": "Some browser sources could not be decided automatically"}
        return ProviderExecutionResult(
            raw_content=raw, observations=observations, exit_code=0 if complete else 1,
            outcome="COMPLETED" if complete else "PARTIAL",
            error_message=None if complete else errors.get(reason, "Browser discovery incomplete"),
            metadata={"coverage": coverage, "budget_reason": reason},
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
            evidence = {"platform": row.get("source"), "profile_url": url,
                        "match_basis": "signed_in_browser_candidate", "identity_verified": False,
                        "verification_state": "CANDIDATE_REVIEW_REQUIRED",
                        "browser": "Cốc Cốc"}
            item_lineage = lineage.model_copy(update={"upstream_source": "coccoc_browser",
                "upstream_family": "BROWSER_ASSISTED"})
            if lineage.parent_observable_type == ObservableType.USERNAME:
                account = f"{lineage.parent_observable_value}@{str(row.get('source', '')).casefold()}"
                results.append(Observation(
                    observable=self.normalize({"type": ObservableType.ACCOUNT, "value": account,
                                               "namespace": str(row.get("source", "")).casefold()}),
                    lineage=item_lineage, confidence=0.55, raw_data=evidence))
            results.append(Observation(
                observable=self.normalize({"type": ObservableType.URL, "value": url}),
                lineage=item_lineage, confidence=0.55, raw_data=evidence))
        return results

    def normalize(self, raw_item):
        return NormalizedObservable(type=raw_item["type"], value=raw_item["value"],
                                    namespace=raw_item.get("namespace", ""))
