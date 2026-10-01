"""Build the healer prompt for one sample (see docs/HEALER_CONTRACT.md)."""

from __future__ import annotations

import re

from forge.capture import VIEWPORTS

MAX_DOM_CHARS = 12000
TRUNCATION_MARKER = " [truncated]"
RESPONSE_FORMAT = (
    '{"selector": "<CSS selector of the broken element>", '
    '"property": "<one CSS property name, e.g. margin-left>", '
    '"value": "<the corrected value, e.g. 16px>"}'
)

_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_HEAVY = re.compile(r"<(style|script|svg)\b[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_NOISY_ATTR = re.compile(r'\s(?:class|role|aria-[\w-]+|data-[\w-]+)="[^"]*"', re.IGNORECASE)


def shorten_dom(html: str) -> str:
    """Make a page's HTML small enough for the model without losing the bug.

    Style, script and svg blocks are emptied but their tags are kept, so
    :nth-of-type counts stay correct. Inline style and id attributes are kept
    because the bug lives in the inline style.
    """
    html = _COMMENT.sub("", html)
    html = _HEAVY.sub(lambda m: f"<{m.group(1).lower()}></{m.group(1).lower()}>", html)
    html = _NOISY_ATTR.sub("", html)
    return re.sub(r"\s+", " ", html).strip()


def build_prompt(viewport: str, dom_html: str) -> str:
    """The text prompt sent with the broken screenshot."""
    width, height = VIEWPORTS[viewport]
    dom = shorten_dom(dom_html)
    if len(dom) > MAX_DOM_CHARS:
        dom = dom[:MAX_DOM_CHARS] + TRUNCATION_MARKER
    return "\n".join(
        [
            "A web page has a layout bug. One element has a wrong inline CSS value.",
            f"Viewport: {viewport} ({width}x{height} pixels).",
            "You get a screenshot of the broken page and its HTML (styles and scripts removed).",
            "Reply with ONLY a JSON object in this form:",
            RESPONSE_FORMAT,
            "Write the selector as a chain from body using :nth-of-type, for example",
            "body > div:nth-of-type(2) > p:nth-of-type(1).",
            "",
            "HTML:",
            dom,
        ]
    )