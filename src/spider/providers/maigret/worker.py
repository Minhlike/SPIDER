"""Isolated Maigret bridge. stdout carries permits, never page/report content."""
import asyncio
import hashlib
import importlib.metadata
import json
import logging
import sys
import secrets
import hmac
from pathlib import Path
from spider.providers.maigret.profile_metadata import public_metadata
from spider.discovery.vn_sources import DIRECT_MAIGRET_SITES, SEARCH_ONLY_SITES

PRIORITY_SOCIAL_SITES = ("Instagram", "Threads", "TikTok")
SOCIAL_RESPONSE_RULE_VERSION = "2026-09-04.1"

SOCIAL_RESPONSE_RULES = {
    "instagram": {
        "presence": ('"biography"',),
        "absence": ("sorry, this page isn&#39;t available.", "dialog-404"),
        "login": ("accounts/login", "login • instagram", "login | instagram", "login - instagram",
                  '"routepath":"\\/"'),
        "blocked": ("challenge_required", "checkpoint_required", "captcha"),
    },
    "threads": {
        "presence": ('og:type" content="profile',),
        "absence": (),
        "login": ("threads • log in", "threads | log in", "threads - log in",
                  'content="https://www.threads.com/login', "/login"),
        "blocked": ("challenge", "captcha"),
    },
    "tiktok": {
        "presence": ('"nickname":',),
        "absence": ('servercode":404',),
        "login": ("login to tiktok", "log in to tiktok"),
        "blocked": ("tiktok-verify-page", "verify to continue", "captcha"),
    },
}


def classify_priority_social_response(site_name, response):
    """Downgrade ambiguous platform pages; never promotes a profile result."""
    rules = SOCIAL_RESPONSE_RULES.get(str(site_name).casefold())
    if not rules or not response:
        return None
    html, status_code, check_error = response
    if check_error:
        return None
    text = (html or "").casefold()
    if status_code == 429 or any(marker in text for marker in
                                 ("too many requests", "please wait a few minutes before you try again")):
        return "RATE_LIMITED"
    if status_code == 401:
        return "LOGIN_REQUIRED"
    if status_code in (403, 451) or any(marker in text for marker in rules["blocked"]):
        return "BLOCKED"
    if any(marker in text for marker in rules["login"]):
        return "LOGIN_REQUIRED"
    if status_code in (404, 410):
        return None
    if any(marker in text for marker in (*rules["presence"], *rules["absence"])):
        return None
    if isinstance(status_code, int) and 200 <= status_code < 300:
        return "PARSER_DRIFT"
    return None


def select_prioritized_sites(sites, site_limit, requested_sites=None):
    """Keep high-value social sites inside a bounded Maigret run."""
    if requested_sites is not None:
        by_name = {name.casefold(): name for name in sites}
        names = [by_name[name.casefold()] for name in requested_sites
                 if name.casefold() in by_name]
        return {name: sites[name] for name in names}
    if not site_limit or site_limit >= len(sites):
        return dict(sites)
    by_name = {name.casefold(): name for name in sites}
    names = []
    for preferred in PRIORITY_SOCIAL_SITES:
        actual = by_name.get(preferred.casefold())
        if actual and actual not in names:
            names.append(actual)
    for name in sites:
        if len(names) >= site_limit:
            break
        if name not in names:
            names.append(name)
    return {name: sites[name] for name in names[:site_limit]}


def priority_site_manifest(catalog, eligible, selected, preferred_sites=PRIORITY_SOCIAL_SITES):
    catalog_names = {name.casefold(): name for name in catalog}
    eligible_names = {name.casefold(): name for name in eligible}
    selected_names = {name.casefold(): name for name in selected}
    result = {}
    for preferred in preferred_sites:
        key = preferred.casefold()
        if key in selected_names:
            result[preferred] = {"state": "SCHEDULED", "site_name": selected_names[key]}
        elif key in eligible_names:
            result[preferred] = {"state": "SKIPPED_SITE_BUDGET", "site_name": eligible_names[key]}
        elif key in catalog_names:
            result[preferred] = {"state": "INELIGIBLE", "site_name": catalog_names[key]}
        else:
            result[preferred] = {"state": "NOT_IN_CATALOG"}
    return result


async def run(spec):
    import aiohttp
    import inspect
    import maigret
    import maigret.checking as checking
    from maigret.result import MaigretCheckStatus

    if importlib.metadata.version("maigret") != "0.6.5":
        raise RuntimeError("Unsupported Maigret version")
    db_path = Path(spec.get("database") or Path(maigret.__file__).parent / "resources/data.json")
    database = maigret.MaigretDatabase().load_from_file(str(db_path))
    catalog = database.ranked_sites_dict(disabled=False, id_type="username")
    sites = {name: site for name, site in catalog.items()
             if not site.activation and not site.similar_search and site.protocol in ("", "http", "https")}
    requested_sites = spec.get("requested_sites")
    selected = select_prioritized_sites(sites, spec["site_limit"], requested_sites)
    with Path(spec["report"]).open("w", encoding="utf-8", buffering=1) as report:
        def write(row):
            report.write(json.dumps(row, ensure_ascii=False) + "\n")
            report.flush()

        preferred_sites = requested_sites or PRIORITY_SOCIAL_SITES
        selected_names = {name.casefold() for name in selected}
        write({"kind": "manifest", "selected": len(selected), "supported": len(sites),
               "excluded_ineligible": len(catalog)-len(sites),
               "source_scope": spec.get("source_scope", "GLOBAL_LIMIT"),
               "requested_sites": list(requested_sites or []),
               "requested_missing": [name for name in requested_sites or []
                                     if name.casefold() not in selected_names],
               "search_only_sites": list(SEARCH_ONLY_SITES) if requested_sites == list(DIRECT_MAIGRET_SITES) else [],
               "priority_sites": priority_site_manifest(catalog, sites, selected, preferred_sites),
               "database_sha256": hashlib.sha256(db_path.read_bytes()).hexdigest()})

        metadata_by_site = {}
        site_rows = {}
        request_count = 0
        permit_count = 0
        permit_lock = asyncio.Lock()
        request_limit = spec.get("max_requests")
        request_kind = "lookup"
        request_identifier = spec["username"]
        fingerprint_salt = bytes.fromhex(spec.get("fingerprint_salt", ""))
        original_session_init = aiohttp.ClientSession.__init__
        if "middlewares" not in inspect.signature(original_session_init).parameters:
            raise RuntimeError("Maigret HTTP request accounting unavailable")

        async def meter(request, handler):
            nonlocal request_count, permit_count
            if request_limit is not None and request_count >= request_limit:
                raise aiohttp.ClientError("Network request budget exhausted")
            host = request.url.host or "unknown"
            if request_identifier.casefold() in host.casefold():
                host = "<identifier-host>"
            frame = {"kind": "request_permit", "purpose": request_kind,
                   "destination": host, "identifier_fingerprint": hmac.new(fingerprint_salt,
                       json.dumps(("USERNAME", "", request_identifier)).encode(), hashlib.sha256).hexdigest()}
            async with permit_lock:
                # Serialise only the handshake, not the network response.
                if request_limit is not None and request_count >= request_limit:
                    raise aiohttp.ClientError("Network request budget exhausted")
                permit_count += 1
                sequence = permit_count
                frame["sequence"] = sequence
                if spec.get("parent_permits"):
                    print(json.dumps(frame), flush=True)
                    approved = await asyncio.to_thread(sys.stdin.readline)
                    if approved.strip() != "1":
                        raise aiohttp.ClientError("Parent request budget denied")
                request_count += 1
            # Every retry, redirect and negative control needs its own permit.
            write({**frame, "kind": "request"})
            try:
                response = await handler(request)
            except BaseException:
                write({"kind": "request_outcome", "sequence": sequence, "outcome": "UNKNOWN_AFTER_DISPATCH"})
                raise
            write({"kind": "request_outcome", "sequence": sequence, "outcome": "HTTP_" + str(response.status)})
            return response

        def metered_session(session, *args, **kwargs):
            kwargs["middlewares"] = (meter, *kwargs.get("middlewares", ()))
            original_session_init(session, *args, **kwargs)
        original_process = checking.process_site_result
        def process_with_metadata(response, query_notify, logger, results_info, site):
            result = original_process(response, query_notify, logger, results_info, site)
            status = result.get("status")
            response_class = classify_priority_social_response(site.name, response)
            if status and response_class:
                status.status = MaigretCheckStatus.UNKNOWN
                status.error = response_class
                status.context = response_class
                status.spider_response_class = response_class
            if status and status.is_found() and not status.error:
                metadata_by_site[site.name] = public_metadata(response[0] if response else None)
            return result

        class Notify:
            def start(self, *args, **kwargs): pass
            def finish(self, *args, **kwargs): pass
            def warning(self, *args, **kwargs): pass
            def success(self, *args, **kwargs): pass
            def info(self, *args, **kwargs): pass
            def enrich(self, *args, **kwargs): pass
            def update(self, result, *args, **kwargs):
                site = selected[result.site_name]
                needs_control = site.check_type == "status_code" or (site.check_type == "message" and not site.presense_strs)
                response_class = getattr(result, "spider_response_class", None)
                row = {"kind": "site", "sitename": result.site_name,
                       "url_user": result.site_url_user,
                       "status": {"status": result.status.value},
                       "error": bool(result.error), **metadata_by_site.get(result.site_name, {}),
                       "negative_control": "pending" if result.is_found() and needs_control else "not_required"}
                if response_class:
                    row.update(response_class=response_class,
                               verification_reason=response_class,
                               detection_rule_version=SOCIAL_RESPONSE_RULE_VERSION)
                site_rows[result.site_name] = row
                write(row)

        # 0.6.5 discards response_text before notifying. This version-pinned hook
        # runs only in this worker, preserves upstream decisions, and extracts
        # bounded public metadata before the response is discarded. No package
        # files are modified; a real HTTP contract test guards the hook.
        checking.process_site_result = process_with_metadata
        aiohttp.ClientSession.__init__ = metered_session
        try:
            await maigret.search(
                spec["username"], selected, logging.getLogger("maigret.worker"),
                query_notify=Notify(), timeout=spec.get("site_timeout", 4),
                max_connections=20, no_progressbar=True, retries=0,
                is_parsing_enabled=False, is_enrich_enabled=False, check_domains=False,
                dns_resolver="threaded")
            # Upstream may return without notifying a failed site. Preserve uncertainty
            # instead of silently losing it from coverage or retrying it unmetered.
            for name in selected.keys() - site_rows.keys():
                row = {"kind": "site", "sitename": name, "status": {"status": "Unknown"},
                       "error": True, "negative_control": "not_required",
                       "verification_reason": "no_result_event"}
                site_rows[name] = row
                write(row)
            control_sites = {name: selected[name] for name, row in site_rows.items()
                             if row["negative_control"] == "pending"}
            if control_sites:
                request_kind = "negative_control"
                request_identifier = "sp" + secrets.token_hex(5)
                class ControlNotify(Notify):
                    def update(self, result, *args, **kwargs):
                        row = dict(site_rows[result.site_name])
                        row["negative_control"] = result.status.value.casefold()
                        if result.is_found():
                            # The site also claims an unpredictable control handle.
                            # This cannot establish existence of the requested profile.
                            row["status"] = {"status": "Unknown"}
                            row["error"] = True
                            row["verification_reason"] = "non_unique_detection"
                        write(row)
                await maigret.search(
                    request_identifier, control_sites, logging.getLogger("maigret.control"),
                    query_notify=ControlNotify(), timeout=spec.get("site_timeout", 4),
                    max_connections=20, no_progressbar=True, retries=0,
                    is_parsing_enabled=False, is_enrich_enabled=False, check_domains=False,
                    dns_resolver="threaded")
        finally:
            checking.process_site_result = original_process
            aiohttp.ClientSession.__init__ = original_session_init
        write({"kind": "complete"})


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    try:
        asyncio.run(run(json.loads(sys.stdin.readline())))
    except Exception:
        # Exceptions may contain URLs, request headers or user data.
        sys.exit(1)
