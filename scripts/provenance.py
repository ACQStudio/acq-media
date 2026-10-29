"""Read the explicitly credited original publication from an aggregator page."""

from html.parser import HTMLParser
from ipaddress import ip_address
from urllib.parse import urljoin, urlsplit, urlunsplit


_VOID_TAGS = frozenset("area base br col embed hr img input link meta param source track wbr".split())


class _Node:
    def __init__(self, tag="", attrs=(), parent=None):
        self.tag = tag
        self.attrs = dict(attrs)
        self.parent = parent
        self.contents = []

    def text(self):
        return "".join(value if isinstance(value, str) else value.text() for value in self.contents)

    def descendants(self):
        for value in self.contents:
            if isinstance(value, _Node):
                yield value
                yield from value.descendants()


class _SourceHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node()
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, attrs, self.stack[-1])
        self.stack[-1].contents.append(node)
        if tag not in _VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].contents.append(_Node(tag, attrs, self.stack[-1]))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].contents.append(data)


def _original_url(href, page_url):
    try:
        url = urlsplit(urljoin(page_url, href))
        host = (url.hostname or "").lower().rstrip(".")
        if url.scheme.lower() not in ("http", "https") or not host or url.username or url.password:
            return None
        page_host = (urlsplit(page_url).hostname or "").lower().rstrip(".")
        if host == page_host or host == "soldoutmedia.ro" or host.endswith(".soldoutmedia.ro"):
            return None
        if "." not in host or host.endswith((".local", ".localhost", ".internal")):
            return None
        try:
            if not ip_address(host).is_global:
                return None
        except ValueError:
            pass
        return urlunsplit((url.scheme.lower(), url.netloc, url.path, url.query, ""))
    except (TypeError, ValueError):
        return None


def resolve_original_source(page_html, page_url):
    """Return the source credit beside the exact ``span.kicker`` label ``Sursa:``.

    A photo credit, a link in the article body, or an uncredited external link is
    insufficient. Missing or invalid original-source credits return ``None``.
    """
    if not isinstance(page_html, str) or not isinstance(page_url, str):
        return None
    parser = _SourceHTML()
    try:
        parser.feed(page_html)
    except (TypeError, ValueError):
        return None
    for label in parser.root.descendants():
        if label.tag != "span" or "kicker" not in (label.attrs.get("class") or "").split():
            continue
        if " ".join(label.text().split()).casefold() != "sursa:" or label.parent is None:
            continue
        for anchor in label.parent.descendants():
            if anchor.tag != "a":
                continue
            link = _original_url(anchor.attrs.get("href"), page_url)
            if not link:
                continue
            source = " ".join(anchor.text().split())
            if not source:
                source = (urlsplit(link).hostname or "").removeprefix("www.")
            return {"source": source[:100], "link": link}
    return None
