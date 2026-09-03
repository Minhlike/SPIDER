"""Read public HTML metadata already fetched by Maigret; no additional requests."""
from html.parser import HTMLParser


class PublicMetadataParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.fields = {}
        self.in_title = False
        self.title = []

    def handle_starttag(self, tag, attrs):
        if tag == "title": self.in_title = True
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

    def handle_data(self, text):
        if self.in_title: self.title.append(text)


def public_metadata(html):
    parser = PublicMetadataParser()
    try:
        if isinstance(html, str): parser.feed(html[:524288])
    except (ValueError, AssertionError):
        return {}
    if "display_name" not in parser.fields and parser.title:
        parser.fields["display_name"] = " ".join(" ".join(parser.title).split())[:200]
    return dict(parser.fields, metadata_basis="public_page_metadata")
