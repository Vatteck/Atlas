import re
from html import escape

HTML_RE = re.compile(r'<[^>]+>')


def strip_html(string: str):
    return HTML_RE.sub('', string)


def bold(text: str) -> str:
    return '<span style="font-weight: bold">{}</span>'.format(escape(str(text), quote=True))


def link(url: str) -> str:
    safe_url = escape(str(url), quote=True)
    return '<a href="{}">{}</a>'.format(safe_url, safe_url)
