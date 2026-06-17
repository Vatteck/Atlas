"""Parse the comments section of an AUR package web page into structured, plain-text entries.

The AUR RPC exposes no comments endpoint, so the package page HTML must be scraped. This module is
the **pure, network-free** parser (fetching + caching live in the webview API), which keeps it
unit-testable and keeps the fragile scraping logic in one place.

Comment bodies are reduced to **plain text** on purpose: we never re-inject scraped third-party HTML
into the WebKitGTK UI (XSS surface). The frontend escapes the text and linkifies bare URLs itself.
"""
from html.parser import HTMLParser
from typing import List, Dict
import re

MAX_COMMENTS = 20

# AUR account links look like /account/<user>; the comment date sits in a <time> element.
_ACCOUNT_HREF = re.compile(r'^/account/')
_WS = re.compile(r'[ \t ]+')


def _classes(attrs) -> set:
    for k, v in attrs:
        if k == 'class' and v:
            return set(v.split())
    return set()


def _attr(attrs, name):
    for k, v in attrs:
        if k == name:
            return v
    return None


class _CommentParser(HTMLParser):
    """Walks the AUR package page, pairing each `<h4 class="comment-header">` (author + date) with the
    `article-content` block that follows it (the rendered body). Tolerant of attribute order and
    nested divs; ignores everything outside that structure."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.comments: List[Dict] = []
        self._div_depth = 0
        # header capture
        self._in_header = False
        self._capture_author = False
        self._in_time = False
        self._pending_author = None
        self._pending_date = None
        # body capture
        self._in_body = False
        self._body_div_depth = 0
        self._body_parts: List[str] = []

    def handle_starttag(self, tag, attrs):
        classes = _classes(attrs)
        if tag == 'h4' and 'comment-header' in classes:
            self._in_header = True
            self._pending_author = None
            self._pending_date = None
            return
        if self._in_header:
            if tag == 'a' and self._pending_author is None:
                href = _attr(attrs, 'href') or ''
                if _ACCOUNT_HREF.match(href):
                    self._capture_author = True
                    self._pending_author = ''
            elif tag == 'time':
                self._in_time = True
                if not self._pending_date:
                    self._pending_date = (_attr(attrs, 'datetime') or '').strip()
        if tag == 'div':
            self._div_depth += 1
            if not self._in_body and ('article-content' in classes or 'comment-rendered' in classes):
                self._in_body = True
                self._body_div_depth = self._div_depth
                self._body_parts = []
            return
        # keep paragraph/line breaks readable in the flattened text
        if self._in_body and tag in ('p', 'br', 'li', 'pre', 'blockquote'):
            self._body_parts.append('\n')

    def handle_endtag(self, tag):
        if tag == 'a' and self._capture_author:
            self._capture_author = False
        elif tag == 'time' and self._in_time:
            self._in_time = False
        elif tag == 'h4' and self._in_header:
            self._in_header = False
        elif tag == 'div':
            if self._in_body and self._div_depth == self._body_div_depth:
                self._finalize_body()
            self._div_depth = max(0, self._div_depth - 1)

    def handle_data(self, data):
        if self._capture_author:
            self._pending_author += data
        elif self._in_time and not self._pending_date:
            self._pending_date = data.strip()
        elif self._in_body:
            self._body_parts.append(data)

    def _finalize_body(self):
        self._in_body = False
        body = _clean_text(''.join(self._body_parts))
        author = _WS.sub(' ', (self._pending_author or '')).strip()
        date = _WS.sub(' ', (self._pending_date or '')).strip()
        self._pending_author = None
        self._pending_date = None
        self._body_parts = []
        if body:
            self.comments.append({'author': author, 'date': date, 'body': body})


def _clean_text(text: str) -> str:
    """Collapse intra-line whitespace, trim blank lines, and drop runs of >2 newlines."""
    lines = [_WS.sub(' ', ln).strip() for ln in text.split('\n')]
    out = []
    blanks = 0
    for ln in lines:
        if ln:
            blanks = 0
            out.append(ln)
        else:
            blanks += 1
            if blanks == 1 and out:
                out.append('')
    return '\n'.join(out).strip()


def parse_comments(html_text: str, limit: int = MAX_COMMENTS) -> List[Dict]:
    """Parse AUR package-page HTML into ``[{author, date, body}]`` (plain text), in document order
    (AUR shows newest first), capped at ``limit``. Returns ``[]`` on any parse failure."""
    if not html_text:
        return []
    parser = _CommentParser()
    try:
        parser.feed(html_text)
    except Exception:
        return parser.comments[:limit]
    return parser.comments[:limit]
