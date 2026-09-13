"""Inspect Cốc Cốc result shape without printing the searched phone or page text."""
import argparse
import asyncio
from collections import Counter
import json
from urllib.parse import quote_plus, urlsplit

from playwright.async_api import async_playwright

from spider.models.classifier import TargetClassifier
from spider.models.enums import ObservableType
from spider.providers.browser.coccoc import (
    PHONE_SEARCH_SOURCES, coccoc_installation, coccoc_profile,
    normalize_search_result_url, phone_search_query, phone_search_snippet_fields,
    phone_search_variants,
)


ENGINE_URLS = {
    "coccoc": "https://coccoc.com/search?query={query}",
    "google": "https://www.google.com/search?q={query}",
    "bing": "https://www.bing.com/search?q={query}",
    "duckduckgo": "https://html.duckduckgo.com/html/?q={query}",
}


async def run(phone, requested_host, engine="coccoc"):
    allowed_hosts = {host for _source, host in PHONE_SEARCH_SOURCES}
    if requested_host not in allowed_hosts:
        raise ValueError("Host is not in PHONE_SEARCH_SOURCES")
    classified = TargetClassifier.resolve(phone, ObservableType.PHONE)
    query = quote_plus(f"site:{requested_host} {phone_search_query(classified.canonical_value)}")
    executable, profile = coccoc_installation()
    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            str(profile), executable_path=str(executable), headless=False,
            accept_downloads=False, service_workers="block",
            args=[f"--profile-directory={coccoc_profile(profile)}"])
        try:
            for initial in list(context.pages):
                await initial.close()
            page = await context.new_page()
            response = await page.goto(ENGINE_URLS[engine].format(query=query),
                                       wait_until="domcontentloaded", timeout=10000)
            await page.wait_for_timeout(1500)
            links = await page.locator("a[href]").evaluate_all(
                "els => els.slice(0,1000).map(a=>{const p=[];let n=a;"
                "for(let i=0;i<4&&n;i++,n=n.parentElement){if(n.tagName==='BODY'||n.tagName==='HTML')break;"
                "const v=(n.innerText||n.textContent||'').trim();if(v&&v.length<=1600)p.push(v);}"
                "return {href:a.href,text:p.join('\\n').slice(0,2400)}})")
            body = await page.locator("body").inner_text(timeout=3000)
            hosts = Counter()
            direct = redirect = literal = candidate_labels = 0
            for link in links:
                parsed = urlsplit(link.get("href") or "")
                host = (parsed.hostname or "").casefold()
                if host:
                    hosts[host] += 1
                normalized = normalize_search_result_url(link.get("href"))
                normalized_host = (urlsplit(normalized).hostname or "").casefold() if normalized else ""
                if normalized_host == requested_host or normalized_host.endswith("." + requested_host):
                    direct += 1
                if host.endswith("coccoc.com") and parsed.path not in {"/", "/search"}:
                    redirect += 1
                digits = "".join(char for char in link.get("text", "") if char.isdigit())
                if any("".join(char for char in value if char.isdigit()) in digits
                       for value in phone_search_variants(classified.canonical_value)):
                    literal += 1
                candidate_labels += bool(phone_search_snippet_fields(
                    link.get("text", ""), classified.canonical_value,
                    next(source for source, host in PHONE_SEARCH_SOURCES if host == requested_host)))
            final = urlsplit(page.url)
            return {"status": response.status if response else None,
                    "final_host": final.hostname, "final_path": final.path,
                    "anchors": len(links), "direct_host_links": direct,
                    "coccoc_redirect_links": redirect, "literal_anchor_links": literal,
                    "directory_candidate_labels": candidate_labels,
                    "body_chars": len(body), "top_link_hosts": hosts.most_common(12)}
        finally:
            await context.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--phone", required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--engine", choices=tuple(ENGINE_URLS), default="coccoc")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.phone, args.host, args.engine)), ensure_ascii=False))
