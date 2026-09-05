"""Read public HTML metadata already fetched by Maigret; no additional requests."""
from html.parser import HTMLParser
import json
from urllib.parse import urlsplit, urlunsplit


def _public_link(value):
    if not isinstance(value, str) or len(value) > 2048:
        return ""
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return ""
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc.casefold(), parsed.path or "/", "", ""))


class PublicMetadataParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.fields = {}
        self.in_title = False
        self.title = []
        self.links = []
        self.in_jsonld = False
        self.jsonld = []

    def handle_starttag(self, tag, attrs):
        if tag == "title": self.in_title = True
        pairs = dict(attrs)
        if tag in ("a", "link") and "me" in (pairs.get("rel") or "").lower().split() and pairs.get("href"):
            self.links.append({"url": pairs["href"][:2048], "basis": "rel_me"})
        if tag == "script" and pairs.get("type") == "application/ld+json":
            self.in_jsonld, self.jsonld = True, []
        if tag != "meta": return
        attrs = dict(attrs)
        name = (attrs.get("property") or attrs.get("name") or "").casefold()
        content = " ".join((attrs.get("content") or "").split())
        field = {"og:title": "display_name", "twitter:title": "display_name",
                 "og:description": "bio", "twitter:description": "bio", "description": "bio"}.get(name)
        if field and content and field not in self.fields:
            self.fields[field] = content[:200 if field == "display_name" else 1000]

    def handle_endtag(self, tag):
        if tag == "title": self.in_title = False
        if tag == "script" and self.in_jsonld:
            self.in_jsonld = False
            try:
                data = json.loads("".join(self.jsonld))
                # Only a top-level self description; nested people may be unrelated.
                if isinstance(data, dict) and data.get("@type") in ("Person", "Organization"):
                    links = data.get("sameAs", [])
                    for link in ([links] if isinstance(links, str) else links if isinstance(links, list) else [])[:25]:
                        if isinstance(link, str):
                            self.links.append({"url": link[:2048], "basis": "jsonld_sameAs"})
            except (ValueError, TypeError):
                pass

    def handle_data(self, text):
        if self.in_title: self.title.append(text)
        if self.in_jsonld: self.jsonld.append(text)


def public_metadata(html):
    parser = PublicMetadataParser()
    try:
        if isinstance(html, str): parser.feed(html[:524288])
    except (ValueError, AssertionError):
        return {}
    if "display_name" not in parser.fields and parser.title:
        parser.fields["display_name"] = " ".join(" ".join(parser.title).split())[:200]
    links, seen = [], set()
    for link in parser.links:
        safe = _public_link(link.get("url"))
        item = (safe, link.get("basis"))
        if not safe or item in seen:
            continue
        seen.add(item)
        links.append({"url": safe, "basis": item[1]})
        if len(links) == 50:
            break
    return dict(parser.fields, metadata_basis="public_page_metadata", explicit_links=links)
