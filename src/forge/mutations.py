"""Bug mutations: break one element in a live page and record how to undo it."""

from __future__ import annotations

import random
from dataclasses import dataclass

from playwright.sync_api import Page

OVERFLOW = "OVERFLOW"


class MutationError(RuntimeError):
    """Raised when no suitable element could be mutated."""


@dataclass(frozen=True)
class Mutation:
    """One injected bug and its gold fix (the contract in docs/BUG_TAXONOMY.md)."""

    bug_type: str
    target_selector: str
    property: str
    broken_css: str
    gold_fix: str


_CANDIDATES_JS = """
() => {
  const skip = new Set(
    ['HTML', 'HEAD', 'BODY', 'SCRIPT', 'STYLE', 'LINK', 'META', 'TITLE', 'NOSCRIPT']
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
  const out = [];
  for (const el of document.body.querySelectorAll('*')) {
    if (skip.has(el.tagName)) continue;
    const rect = el.getBoundingClientRect();
    const parentRect = el.parentElement.getBoundingClientRect();
    if (rect.width < 20 || rect.height < 10 || parentRect.width <= 0) continue;
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

_MEASURE_JS = """
(sel) => {
  const el = document.querySelector(sel);
  const rect = el.getBoundingClientRect();
  const parentRect = el.parentElement.getBoundingClientRect();
  return {right: rect.right, parentRight: parentRect.right};
}
"""

_SET_JS = "([sel, prop, val]) => document.querySelector(sel).style.setProperty(prop, val)"
_CLEAR_JS = "([sel, prop]) => document.querySelector(sel).style.removeProperty(prop)"


def apply_declaration(page: Page, selector: str, declaration: str) -> None:
    """Apply one CSS declaration such as 'width: 300px' to the element as an inline style."""
    prop, _, value = declaration.partition(":")
    page.evaluate(_SET_JS, [selector, prop.strip(), value.strip()])


def mutate_overflow(page: Page, seed: int = 0, max_attempts: int = 10) -> Mutation:
    """Make one element wider than its parent. The page is left in the broken state."""
    rng = random.Random(seed)
    candidates = [
        c for c in page.evaluate(_CANDIDATES_JS) if c["computedWidth"].endswith("px")
    ]
    rng.shuffle(candidates)

    for candidate in candidates[:max_attempts]:
        selector = candidate["selector"]
        factor = rng.uniform(1.5, 2.5)
        new_width = int(max(candidate["parentWidth"] * factor, candidate["width"] + 200))
        broken_css = f"width: {new_width}px"

        apply_declaration(page, selector, broken_css)
        measured = page.evaluate(_MEASURE_JS, selector)
        if measured["right"] > measured["parentRight"] + 1:
            return Mutation(
                bug_type=OVERFLOW,
                target_selector=selector,
                property="width",
                broken_css=broken_css,
                gold_fix=f"width: {candidate['computedWidth']}",
            )
        page.evaluate(_CLEAR_JS, [selector, "width"])

    raise MutationError("No element could be made to overflow its parent.")