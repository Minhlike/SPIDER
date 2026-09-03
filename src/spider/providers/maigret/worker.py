"""Isolated Maigret 0.6.5 bridge. stdout is never the report transport."""
import asyncio
import hashlib
import importlib.metadata
import json
import logging
import sys
import secrets
from pathlib import Path
from spider.providers.maigret.profile_metadata import public_metadata


async def run(spec):
    import maigret
    import maigret.checking as checking

    if importlib.metadata.version("maigret") != "0.6.5":
        raise RuntimeError("Unsupported Maigret version")
    db_path = Path(spec.get("database") or Path(maigret.__file__).parent / "resources/data.json")
    database = maigret.MaigretDatabase().load_from_file(str(db_path))
    catalog = database.ranked_sites_dict(disabled=False, id_type="username")
    sites = {name: site for name, site in catalog.items()
             if not site.activation and not site.similar_search and site.protocol in ("", "http", "https")}
    selected = dict(list(sites.items())[:spec["site_limit"] or len(sites)])
    with Path(spec["report"]).open("w", encoding="utf-8", buffering=1) as report:
        def write(row):
            report.write(json.dumps(row, ensure_ascii=False) + "\n")
            report.flush()

        write({"kind": "manifest", "selected": len(selected), "supported": len(sites),
               "excluded_ineligible": len(catalog)-len(sites),
               "database_sha256": hashlib.sha256(db_path.read_bytes()).hexdigest()})

        metadata_by_site = {}
        site_rows = {}
        original_process = checking.process_site_result
        def process_with_metadata(response, query_notify, logger, results_info, site):
            result = original_process(response, query_notify, logger, results_info, site)
            status = result.get("status")
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
                row = {"kind": "site", "sitename": result.site_name,
                       "url_user": result.site_url_user,
                       "status": {"status": result.status.value},
                       "error": bool(result.error), **metadata_by_site.get(result.site_name, {}),
                       "negative_control": "pending" if result.is_found() and needs_control else "not_required"}
                site_rows[result.site_name] = row
                write(row)

        # 0.6.5 discards response_text before notifying. This version-pinned hook
        # runs only in this worker, preserves upstream decisions, and extracts
        # bounded public metadata before the response is discarded. No package
        # files are modified; a real HTTP contract test guards the hook.
        checking.process_site_result = process_with_metadata
        try:
            await maigret.search(
                spec["username"], selected, logging.getLogger("maigret.worker"),
                query_notify=Notify(), timeout=spec.get("site_timeout", 4),
                max_connections=20, no_progressbar=True, retries=0,
                is_parsing_enabled=False, is_enrich_enabled=False, check_domains=False,
                dns_resolver="threaded")
            control_sites = {name: selected[name] for name, row in site_rows.items()
                             if row["negative_control"] == "pending"}
            if control_sites:
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
                    "sp" + secrets.token_hex(5), control_sites, logging.getLogger("maigret.control"),
                    query_notify=ControlNotify(), timeout=spec.get("site_timeout", 4),
                    max_connections=20, no_progressbar=True, retries=0,
                    is_parsing_enabled=False, is_enrich_enabled=False, check_domains=False,
                    dns_resolver="threaded")
        finally:
            checking.process_site_result = original_process
        write({"kind": "complete"})


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    try:
        asyncio.run(run(json.load(sys.stdin)))
    except Exception:
        # Exceptions may contain URLs, request headers or user data.
        sys.exit(1)
