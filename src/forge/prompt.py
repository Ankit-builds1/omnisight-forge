"""Build the healer prompt for one sample (see docs/HEALER_CONTRACT.md)."""

from __future__ import annotations

import re

from forge.capture import VIEWPORTS

MAX_DOM_CHARS = 20000
TRUNCATION_MARKER = " [truncated]"
RESPONSE_FORMAT = (
    '{"element": <the n number of the broken element>, '
    '"property": "<one CSS property name, e.g. margin-left>", '
    '"value": "<the corrected value, e.g. 16px>"}'
)

# Long text runs fill the prompt on article pages but say little about the layout; each one is
# cut to its first words (#58).
MAX_TEXT_CHARS = 60
_LONG_TEXT = re.compile(r">([^<]{%d,})<" % (MAX_TEXT_CHARS + 1))

_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_HEAVY = re.compile(r"<(style|script|svg)\b[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_NOISY_ATTR = re.compile(
    r'\s(?:class|id|role|aria-[\w-]+|data-[\w-]+|href|title|accesskey|rel|src|srcset|alt|lang'
    r'|dir|tabindex)="[^"]*"',
    re.IGNORECASE,
)
# The healer answers with an element number, and forge.elements maps it back on the full saved
# page, so elements without a number can never be an answer. Empty ones (emptied off-screen
# parts, style and script tags, head metadata) are dropped from the prompt (#58).
_EMPTY_UNNUMBERED = re.compile(r'<(\w+)(?![^>]*\sn=")[^>]*>\s*</\1>')
_VOID_UNNUMBERED = re.compile(
    r'<(?:meta|link|input|br|hr|img|source|base|wbr)(?![^>]*\sn=")[^>]*>', re.IGNORECASE
)
_GAP = re.compile(r">\s+<")


def shorten_dom(html: str) -> str:
    """Make a page's HTML small enough for the model.

    Keeps every numbered element (attribute `n`), its text and its own inline style. Drops
    comments, the content of style, script and svg blocks, noisy attributes (class, id, links,
    ARIA), empty elements without a number, whitespace between tags, and the end of long text
    runs. The injected bug itself is never in the HTML (#54).
    """
    html = _COMMENT.sub("", html)
    html = _HEAVY.sub(lambda m: f"<{m.group(1).lower()}></{m.group(1).lower()}>", html)
    html = _NOISY_ATTR.sub("", html)
    html = re.sub(r"\s+", " ", html).strip()
    html = _GAP.sub("><", html)
    html = _VOID_UNNUMBERED.sub("", html)
    previous = None
    while previous != html:  # removing an empty element can empty its parent
        previous = html
        html = _EMPTY_UNNUMBERED.sub("", html)
    return _LONG_TEXT.sub(_cut_text, html)


def _cut_text(match: re.Match) -> str:
    """Keep the first words of a long text run, up to MAX_TEXT_CHARS characters."""
    words = match.group(1)[:MAX_TEXT_CHARS].rsplit(" ", 1)[0]
    return f">{words}…<"


def build_prompt(viewport: str, dom_html: str) -> str:
    """The text prompt sent with the broken screenshot."""
    width, height = VIEWPORTS[viewport]
    dom = shorten_dom(dom_html)
    if len(dom) > MAX_DOM_CHARS:
        dom = dom[:MAX_DOM_CHARS] + TRUNCATION_MARKER
    return "\n".join(
        [
            "A web page has a layout bug. One element has a wrong CSS value.",
            f"Viewport: {viewport} ({width}x{height} pixels).",
            "You get a screenshot of the broken page and its HTML (styles and scripts removed).",
            "Every visible element in the HTML has a number in its n attribute.",
            "Reply with ONLY a JSON object in this form:",
            RESPONSE_FORMAT,
            "Use the n number of the element whose CSS value is wrong.",
            "",
            "HTML:",
            dom,
        ]
    )