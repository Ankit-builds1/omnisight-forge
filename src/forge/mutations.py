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


# JavaScript shared by every candidate search: skip non-visual tags, keep only elements
# that are fully on screen and not hidden, and build a unique CSS selector for an element
# from its position in the DOM.
_JS_HELPERS = """
  const skip = new Set(
    ['HTML', 'HEAD', 'BODY', 'SCRIPT', 'STYLE', 'LINK', 'META', 'TITLE', 'NOSCRIPT']
  );
  const inView = (r) => (
    r.top >= 0 && r.bottom <= window.innerHeight
    && r.left >= 0 && r.left < window.innerWidth
  );
  const shown = (el) => {
    if (getComputedStyle(el).visibility === 'hidden') return false;
    for (let a = el; a; a = a.parentElement) {
      if (parseFloat(getComputedStyle(a).opacity) === 0) return false;
    }
    return true;
  };
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

# Widening only shows on screen if the element paints something itself (own text,
# background or border) and no ancestor cuts off what sticks out.
_OVERFLOW_CANDIDATES_JS = """
() => {
  //HELPERS//
  const ownText = (el) => Array.from(el.childNodes).some(
    (n) => n.nodeType === 3 && n.textContent.trim().length > 0
  );
  const painted = (el) => {
    const s = getComputedStyle(el);
    return s.backgroundColor !== 'rgba(0, 0, 0, 0)' || parseFloat(s.borderTopWidth) > 0;
  };
  const clipped = (el) => {
    for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
      if (getComputedStyle(a).overflowX !== 'visible') return true;
    }
    return false;
  };
  const out = [];
  for (const el of document.body.querySelectorAll('*')) {
    if (skip.has(el.tagName)) continue;
    const rect = el.getBoundingClientRect();
    const parentRect = el.parentElement.getBoundingClientRect();
    if (rect.width < 20 || rect.height < 10 || parentRect.width <= 0 || !inView(rect)) continue;
    if (!shown(el) || clipped(el) || !(ownText(el) || painted(el))) continue;
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
    if (!shown(el) || !shown(prev)) continue;
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
    if (!shown(el)) continue;
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

# Bugs go into a constructed style sheet attached with document.adoptedStyleSheets. It is not
# part of the HTML, so page.content() and the DOM the healer reads carry no trace of the bug:
# the model has to find it from the screenshot, as with a real bug that comes from a CSS file
# (#54). Rules are !important so they beat the page's own styles.
_INJECT_JS = """
([sel, prop, val]) => {
  if (!window.__forgeBugSheet) {
    window.__forgeBugSheet = new CSSStyleSheet();
    document.adoptedStyleSheets = [...document.adoptedStyleSheets, window.__forgeBugSheet];
  }
  const sheet = window.__forgeBugSheet;
  sheet.insertRule(sel + ' { ' + prop + ': ' + val + ' !important; }', sheet.cssRules.length);
}
"""
_CLEAR_BUG_JS = "() => { if (window.__forgeBugSheet) window.__forgeBugSheet.replaceSync(''); }"
# A fix is an !important inline style, which wins over the !important bug rule.
_SET_JS = (
    "([sel, prop, val]) => "
    "document.querySelector(sel).style.setProperty(prop, val, 'important')"
)


def _declarations(declaration: str) -> list[tuple[str, str]]:
    """'width: 300px; overflow: hidden' -> [('width', '300px'), ('overflow', 'hidden')]."""
    pairs = []
    for part in declaration.split(";"):
        if part.strip():
            prop, _, value = part.partition(":")
            pairs.append((prop.strip(), value.strip()))
    return pairs


def inject_bug(page: Page, selector: str, declaration: str) -> None:
    """Break an element with CSS that the page's HTML does not show."""
    for prop, value in _declarations(declaration):
        page.evaluate(_INJECT_JS, [selector, prop, value])


def apply_declaration(page: Page, selector: str, declaration: str) -> None:
    """Apply a fix such as 'height: auto' as !important inline styles on the element."""
    for prop, value in _declarations(declaration):
        page.evaluate(_SET_JS, [selector, prop, value])


def _candidates(page: Page, script: str) -> list[dict]:
    return page.evaluate(script.replace("//HELPERS//", _JS_HELPERS))


def _try_mutation(page: Page, selector: str, broken_css: str, check_js: str) -> bool:
    """Inject the broken CSS; keep it if the bug is real, otherwise undo it."""
    inject_bug(page, selector, broken_css)
    if page.evaluate(check_js, selector):
        return True
    page.evaluate(_CLEAR_BUG_JS)
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
        if _try_mutation(page, candidate["selector"], broken_css, _OVERFLOW_CHECK_JS):
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
        if _try_mutation(page, candidate["selector"], broken_css, _OVERLAP_CHECK_JS):
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
        if _try_mutation(page, candidate["selector"], broken_css, _CLIPPING_CHECK_JS):
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


# Held-out bug types. They break a page the same three ways (an element sticks out, covers
# its neighbour, or its text no longer fits) but with CSS the healer's checks were not written for:
# no width change, no negative margin, no fixed height. They test whether forge.heal generalises
# beyond the bugs it was designed against; neither the healer nor the model saw them.
SHIFT = "SHIFT"
LIFT = "LIFT"
NOWRAP = "NOWRAP"

_SHIFT_CANDIDATES_JS = """
() => {
  //HELPERS//
  const out = [];
  for (const el of document.body.querySelectorAll('*')) {
    if (skip.has(el.tagName)) continue;
    const s = getComputedStyle(el);
    if (s.position !== 'static' || s.display === 'inline') continue;
    const rect = el.getBoundingClientRect();
    const parentRect = el.parentElement.getBoundingClientRect();
    if (rect.width < 20 || rect.height < 10 || parentRect.width <= 0 || !inView(rect)) continue;
    if (!shown(el)) continue;
    out.push({selector: selectorFor(el), parentWidth: parentRect.width});
  }
  return out;
}
"""

_LIFT_CANDIDATES_JS = """
() => {
  //HELPERS//
  const out = [];
  for (const el of document.body.querySelectorAll('*')) {
    if (skip.has(el.tagName)) continue;
    const prev = el.previousElementSibling;
    if (!prev || skip.has(prev.tagName)) continue;
    if (getComputedStyle(el).transform !== 'none') continue;
    const rect = el.getBoundingClientRect();
    const prevRect = prev.getBoundingClientRect();
    if (rect.width < 20 || rect.height < 10 || !inView(rect)) continue;
    if (prevRect.width < 20 || prevRect.height < 10) continue;
    if (!shown(el) || !shown(prev)) continue;
    out.push({selector: selectorFor(el), height: rect.height, prevHeight: prevRect.height});
  }
  return out;
}
"""

# Text that wraps onto several lines today; forcing one line makes it run out of its box.
_NOWRAP_CANDIDATES_JS = """
() => {
  //HELPERS//
  const out = [];
  for (const el of document.body.querySelectorAll('*')) {
    if (skip.has(el.tagName)) continue;
    const s = getComputedStyle(el);
    if (s.whiteSpace !== 'normal' || s.display === 'inline') continue;
    const text = Array.from(el.childNodes)
      .filter((n) => n.nodeType === 3).map((n) => n.textContent).join(' ').trim();
    if (text.length < 40) continue;
    const rect = el.getBoundingClientRect();
    const lineHeight = parseFloat(s.lineHeight) || parseFloat(s.fontSize) * 1.2;
    if (rect.height < 1.8 * lineHeight || !inView(rect) || !shown(el)) continue;
    out.push({selector: selectorFor(el)});
  }
  return out;
}
"""

_SHIFT_CHECK_JS = """
(sel) => {
  const el = document.querySelector(sel);
  const r = el.getBoundingClientRect();
  return r.right > el.parentElement.getBoundingClientRect().right + 1
    || r.right > window.innerWidth;
}
"""

_NOWRAP_CHECK_JS = """
(sel) => {
  const el = document.querySelector(sel);
  return el.scrollWidth > el.clientWidth + 20;
}
"""


def mutate_shift(page: Page, seed: int = 0, max_attempts: int = 10) -> Mutation:
    """Push an element sideways out of its parent with relative positioning."""
    rng = random.Random(seed)
    candidates = _candidates(page, _SHIFT_CANDIDATES_JS)
    rng.shuffle(candidates)
    for candidate in candidates[:max_attempts]:
        offset = int(max(80, candidate["parentWidth"] * rng.uniform(0.4, 0.8)))
        broken_css = f"position: relative; left: {offset}px"
        if _try_mutation(page, candidate["selector"], broken_css, _SHIFT_CHECK_JS):
            return Mutation(SHIFT, candidate["selector"], "left", broken_css, "left: auto")
    raise MutationError("No element could be shifted out of its parent.")


def mutate_lift(page: Page, seed: int = 0, max_attempts: int = 10) -> Mutation:
    """Move an element up over its sibling with a transform instead of a margin."""
    rng = random.Random(seed)
    candidates = _candidates(page, _LIFT_CANDIDATES_JS)
    rng.shuffle(candidates)
    for candidate in candidates[:max_attempts]:
        smaller = min(candidate["prevHeight"], candidate["height"])
        amount = max(16, int(smaller * rng.uniform(0.4, 0.9)))
        broken_css = f"transform: translateY(-{amount}px)"
        if _try_mutation(page, candidate["selector"], broken_css, _OVERLAP_CHECK_JS):
            return Mutation(LIFT, candidate["selector"], "transform", broken_css, "transform: none")
    raise MutationError("No element could be lifted over its sibling.")


def mutate_nowrap(page: Page, seed: int = 0, max_attempts: int = 10) -> Mutation:
    """Force wrapped text onto one line so that it runs out of its box."""
    rng = random.Random(seed)
    candidates = _candidates(page, _NOWRAP_CANDIDATES_JS)
    rng.shuffle(candidates)
    for candidate in candidates[:max_attempts]:
        broken_css = "white-space: nowrap"
        if _try_mutation(page, candidate["selector"], broken_css, _NOWRAP_CHECK_JS):
            return Mutation(
                NOWRAP, candidate["selector"], "white-space", broken_css, "white-space: normal"
            )
    raise MutationError("No text could be forced out of its box.")


# Maps each bug type to its mutation function, so a dataset builder can loop over all types.
MUTATIONS: dict[str, Callable[..., Mutation]] = {
    OVERFLOW: mutate_overflow,
    OVERLAP: mutate_overlap,
    CLIPPING: mutate_clipping,
    SHIFT: mutate_shift,
    LIFT: mutate_lift,
    NOWRAP: mutate_nowrap,
}
# The healer and the model were built against these; the others are held out.
TRAIN_BUG_TYPES = [OVERFLOW, OVERLAP, CLIPPING]
HELD_OUT_BUG_TYPES = [SHIFT, LIFT, NOWRAP]