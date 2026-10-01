"""Bug mutations: break one element in a live page and record how to undo it."""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass

from playwright.sync_api import Page

OVERFLOW = "OVERFLOW"
OVERLAP = "OVERLAP"
CLIPPING = "CLIPPING"


class MutationError(RuntimeError):
    """Raised when no suitable element could be mutated."""


@dataclass(frozen=True)
class Mutation:
    """One injected bug and its gold fix (the contract in docs/BUG_TAXONOMY.md).

    `broken_css` and `gold_fix` may hold several declarations separated by semicolons.
    """

    bug_type: str
    target_selector: str
    property: str
    broken_css: str
    gold_fix: str


# JavaScript shared by every candidate search: skip non-visual tags and build a unique
# CSS selector for an element from its position in the DOM.
_JS_HELPERS = """
  const skip = new Set(
    ['HTML', 'HEAD', 'BODY', 'SCRIPT', 'STYLE', 'LINK', 'META', 'TITLE', 'NOSCRIPT']
  );
  const inView = (r) => (
    r.top >= 0 && r.bottom <= window.innerHeight && r.left < window.innerWidth
  );
  const selectorFor = (el) => {
    const parts = [];
    let node = el;
    while (node && node !== document.body) {
      let index = 1;
      let sib = node.previousElementSibling;
      while (sib) {
        if (sib.tagName === node.tagName) index += 1;
        sib = sib.previousElementSibling;
      }
      parts.unshift(node.tagName.toLowerCase() + ':nth-of-type(' + index + ')');
      node = node.parentElement;
    }
    return 'body > ' + parts.join(' > ');
  };
"""

_OVERFLOW_CANDIDATES_JS = """
() => {
  //HELPERS//
  const out = [];
  for (const el of document.body.querySelectorAll('*')) {
    if (skip.has(el.tagName)) continue;
    const rect = el.getBoundingClientRect();
    const parentRect = el.parentElement.getBoundingClientRect();
    if (rect.width < 20 || rect.height < 10 || parentRect.width <= 0 || !inView(rect)) continue;
    out.push({
      selector: selectorFor(el),
      width: rect.width,
      parentWidth: parentRect.width,
      computedWidth: getComputedStyle(el).width,
    });
  }
  return out;
}
"""

_OVERLAP_CANDIDATES_JS = """
() => {
  //HELPERS//
  const out = [];
  for (const el of document.body.querySelectorAll('*')) {
    if (skip.has(el.tagName)) continue;
    const prev = el.previousElementSibling;
    if (!prev || skip.has(prev.tagName)) continue;
    const rect = el.getBoundingClientRect();
    const prevRect = prev.getBoundingClientRect();
    if (rect.width < 20 || rect.height < 10 || !inView(rect)) continue;
    if (prevRect.width < 20 || prevRect.height < 10) continue;
    out.push({
      selector: selectorFor(el),
      height: rect.height,
      prevHeight: prevRect.height,
      marginTop: getComputedStyle(el).marginTop,
    });
  }
  return out;
}
"""

_CLIPPING_CANDIDATES_JS = """
() => {
  //HELPERS//
  const out = [];
  for (const el of document.body.querySelectorAll('*')) {
    if (skip.has(el.tagName)) continue;
    const style = getComputedStyle(el);
    if (style.display === 'inline') continue;
    const hasText = Array.from(el.childNodes).some(
      (n) => n.nodeType === 3 && n.textContent.trim().length >= 3
    );
    if (!hasText) continue;
    const range = document.createRange();
    range.selectNodeContents(el);
    const contentHeight = range.getBoundingClientRect().height;
    const rect = el.getBoundingClientRect();
    if (rect.width < 20 || contentHeight < 12 || !inView(rect)) continue;
    out.push({
      selector: selectorFor(el),
      contentHeight: contentHeight,
      computedHeight: style.height,
      overflow: style.overflow,
    });
  }
  return out;
}
"""

_OVERFLOW_CHECK_JS = """
(sel) => {
  const el = document.querySelector(sel);
  const right = el.getBoundingClientRect().right;
  const parentRight = el.parentElement.getBoundingClientRect().right;
  return right > parentRight + 1;
}
"""

_OVERLAP_CHECK_JS = """
(sel) => {
  const el = document.querySelector(sel);
  const a = el.getBoundingClientRect();
  const b = el.previousElementSibling.getBoundingClientRect();
  const vertical = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
  const horizontal = Math.min(a.right, b.right) - Math.max(a.left, b.left);
  return vertical >= 8 && horizontal >= 20;
}
"""

_CLIPPING_CHECK_JS = """
(sel) => {
  const el = document.querySelector(sel);
  return el.scrollHeight > el.clientHeight + 1;
}
"""

_SET_JS = "([sel, prop, val]) => document.querySelector(sel).style.setProperty(prop, val)"
_CLEAR_JS = "([sel, prop]) => document.querySelector(sel).style.removeProperty(prop)"


def apply_declaration(page: Page, selector: str, declaration: str) -> None:
    """Apply CSS declarations such as 'width: 300px; overflow: hidden' as inline styles."""
    for part in declaration.split(";"):
        if not part.strip():
            continue
        prop, _, value = part.partition(":")
        page.evaluate(_SET_JS, [selector, prop.strip(), value.strip()])


def _candidates(page: Page, script: str) -> list[dict]:
    return page.evaluate(script.replace("//HELPERS//", _JS_HELPERS))


def _try_mutation(
    page: Page, selector: str, broken_css: str, properties: list[str], check_js: str
) -> bool:
    """Apply the broken CSS; keep it if the bug is real, otherwise undo it."""
    apply_declaration(page, selector, broken_css)
    if page.evaluate(check_js, selector):
        return True
    for prop in properties:
        page.evaluate(_CLEAR_JS, [selector, prop])
    return False


def mutate_overflow(page: Page, seed: int = 0, max_attempts: int = 10) -> Mutation:
    """Make one element wider than its parent. The page is left in the broken state."""
    rng = random.Random(seed)
    candidates = [
        c for c in _candidates(page, _OVERFLOW_CANDIDATES_JS) if c["computedWidth"].endswith("px")
    ]
    rng.shuffle(candidates)

    for candidate in candidates[:max_attempts]:
        factor = rng.uniform(1.5, 2.5)
        new_width = int(max(candidate["parentWidth"] * factor, candidate["width"] + 200))
        broken_css = f"width: {new_width}px"
        if _try_mutation(page, candidate["selector"], broken_css, ["width"], _OVERFLOW_CHECK_JS):
            return Mutation(
                bug_type=OVERFLOW,
                target_selector=candidate["selector"],
                property="width",
                broken_css=broken_css,
                gold_fix=f"width: {candidate['computedWidth']}",
            )

    raise MutationError("No element could be made to overflow its parent.")


def mutate_overlap(page: Page, seed: int = 0, max_attempts: int = 10) -> Mutation:
    """Pull an element up over the sibling above it. The page is left in the broken state."""
    rng = random.Random(seed)
    candidates = _candidates(page, _OVERLAP_CANDIDATES_JS)
    rng.shuffle(candidates)

    for candidate in candidates[:max_attempts]:
        smaller = min(candidate["prevHeight"], candidate["height"])
        amount = max(16, int(smaller * rng.uniform(0.4, 0.9)))
        broken_css = f"margin-top: -{amount}px"
        if _try_mutation(
            page, candidate["selector"], broken_css, ["margin-top"], _OVERLAP_CHECK_JS
        ):
            return Mutation(
                bug_type=OVERLAP,
                target_selector=candidate["selector"],
                property="margin-top",
                broken_css=broken_css,
                gold_fix=f"margin-top: {candidate['marginTop']}",
            )

    raise MutationError("No element could be made to overlap its sibling.")


def mutate_clipping(page: Page, seed: int = 0, max_attempts: int = 10) -> Mutation:
    """Cut off an element's text with a too-small height. The page is left broken."""
    rng = random.Random(seed)
    candidates = [
        c for c in _candidates(page, _CLIPPING_CANDIDATES_JS) if c["computedHeight"].endswith("px")
    ]
    rng.shuffle(candidates)

    for candidate in candidates[:max_attempts]:
        new_height = max(6, int(candidate["contentHeight"] * rng.uniform(0.3, 0.7)))
        broken_css = f"height: {new_height}px; overflow: hidden"
        if _try_mutation(
            page, candidate["selector"], broken_css, ["height", "overflow"], _CLIPPING_CHECK_JS
        ):
            return Mutation(
                bug_type=CLIPPING,
                target_selector=candidate["selector"],
                property="height",
                broken_css=broken_css,
                gold_fix=(
                    f"height: {candidate['computedHeight']}; "
                    f"overflow: {candidate['overflow']}"
                ),
            )

    raise MutationError("No element could be clipped.")


# Maps each bug type to its mutation function, so a dataset builder can loop over all types.
MUTATIONS: dict[str, Callable[..., Mutation]] = {
    OVERFLOW: mutate_overflow,
    OVERLAP: mutate_overlap,
    CLIPPING: mutate_clipping,
}