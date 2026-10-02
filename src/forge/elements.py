"""Map the numbered elements of a saved DOM to their CSS selectors.

The factory gives every kept on-screen element an `n` attribute (see forge.pipeline). The
healer answers with that number, and these helpers turn it back into the same
`body > tag:nth-of-type(i) > ...` selector that the mutations use.
"""

from __future__ import annotations

from html.parser import HTMLParser

_VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}


class _Frame:
    def __init__(self, tag: str | None, parts: list[str] | None) -> None:
        self.tag = tag
        self.parts = parts
        self.counts: dict[str, int] = {}


class _Walker(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack = [_Frame(None, None)]
        self.paths: dict[int, str] = {}

    def handle_starttag(self, tag, attrs):
        self._enter(tag, attrs, void=tag in _VOID)

    def handle_startendtag(self, tag, attrs):
        self._enter(tag, attrs, void=True)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def _enter(self, tag, attrs, void):
        parent = self.stack[-1]
        index = parent.counts.get(tag, 0) + 1
        parent.counts[tag] = index
        if tag == "body":
            parts = []
        elif parent.parts is None:
            parts = None
        else:
            parts = parent.parts + [f"{tag}:nth-of-type({index})"]
        number = dict(attrs).get("n")
        if parts and number is not None and number.isdigit():
            self.paths[int(number)] = "body > " + " > ".join(parts)
        if not void:
            self.stack.append(_Frame(tag, parts))


def element_paths(html: str) -> dict[int, str]:
    """Every numbered element in the HTML, as {number: selector}."""
    walker = _Walker()
    walker.feed(html)
    walker.close()
    return walker.paths


def element_number(html: str, selector: str) -> int | None:
    """The number of the element with this selector, or None if it has none."""
    for number, path in element_paths(html).items():
        if path == selector:
            return number
    return None