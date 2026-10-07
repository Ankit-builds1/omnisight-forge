"""Self-correcting healer: the model points at the broken area, the browser repairs it.

Run 8 shows that the fine-tuned model often names an element near the bug but the wrong property
(mostly `margin-top: 0px`). The healer keeps the model's element as a starting point, looks at the
elements around it in the live page for a layout symptom, tries the matching fix and keeps it
only if the symptom disappears.

Nothing here uses the clean page or the gold fix: the symptoms are read from the broken page
alone, so the same loop works on a real page with no reference screenshot.
"""

from __future__ import annotations

from dataclasses import dataclass

from playwright.sync_api import Page

from forge.mutations import _JS_HELPERS

# How far from the model's element to look, in steps along the DOM tree (parent or child).
DEFAULT_RADIUS = 3
# Most elements a search may check, so a huge page stays fast.
MAX_ELEMENTS = 400

# Fixes to try for each symptom, in order.
FIXES: dict[str, list[tuple[str, str]]] = {
    "overflow": [("width", "auto"), ("max-width", "100%")],
    "overlap": [("margin-top", "0px")],
    "clipping": [("height", "auto")],
}

# Each symptom is checked on one element of the broken page.
# overflow: the element sticks out of its parent by more than 20px.
# overlap: a negative top margin pulls the element over the sibling above it.
# clipping: the element hides part of its own content.
_SYMPTOMS_JS = """
  const symptoms = {
    overflow: (el) => {
      const parent = el.parentElement;
      if (!parent || parent === document.documentElement) return false;
      const a = el.getBoundingClientRect();
      const b = parent.getBoundingClientRect();
      return a.width > 0 && a.right > b.right + 20;
    },
    overlap: (el) => {
      const prev = el.previousElementSibling;
      if (!prev || parseFloat(getComputedStyle(el).marginTop) >= 0) return false;
      const a = el.getBoundingClientRect();
      const b = prev.getBoundingClientRect();
      const vertical = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      const horizontal = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      return vertical >= 8 && horizontal >= 20;
    },
    clipping: (el) => {
      const overflow = getComputedStyle(el).overflowY;
      if (overflow !== 'hidden' && overflow !== 'clip') return false;
      return el.clientHeight > 0 && el.scrollHeight > el.clientHeight + 1;
    },
  };
"""

_FIND_JS = (
    """
([start, radius, limit]) => {
  //HELPERS//
  //SYMPTOMS//
  const first = document.querySelector(start);
  if (!first) return [];
  const onScreen = (el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < window.innerHeight
      && r.right > 0 && r.left < window.innerWidth;
  };
  const found = [];
  const seen = new Set([first]);
  let queue = [[first, 0]];
  let checked = 0;
  while (queue.length && checked < limit) {
    const [el, distance] = queue.shift();
    checked += 1;
    if (!skip.has(el.tagName) && onScreen(el)) {
      for (const [kind, test] of Object.entries(symptoms)) {
        if (test(el)) found.push({selector: selectorFor(el), kind: kind, distance: distance});
      }
    }
    if (distance === radius) continue;
    const next = [el.parentElement, ...el.children];
    for (const n of next) {
      if (n && n !== document.body && n !== document.documentElement && !seen.has(n)) {
        seen.add(n);
        queue.push([n, distance + 1]);
      }
    }
  }
  return found;
}
"""
    .replace("//HELPERS//", _JS_HELPERS)
    .replace("//SYMPTOMS//", _SYMPTOMS_JS)
)

# Apply one fix, report whether the symptom is gone, then put the element back as it was.
_TRY_JS = (
    """
([sel, kind, prop, val]) => {
  //SYMPTOMS//
  const el = document.querySelector(sel);
  const old = el.style.getPropertyValue(prop);
  const oldPriority = el.style.getPropertyPriority(prop);
  el.style.setProperty(prop, val, 'important');
  const cured = !symptoms[kind](el);
  if (old) el.style.setProperty(prop, old, oldPriority);
  else el.style.removeProperty(prop);
  return cured;
}
"""
    .replace("//SYMPTOMS//", _SYMPTOMS_JS)
)


@dataclass(frozen=True)
class Repair:
    """A fix the browser confirmed: it removes the symptom on that element."""

    selector: str
    property: str
    value: str
    kind: str
    distance: int


# A whole-page scan starts at <body> and may check this many elements.
PAGE_RADIUS = 1000
PAGE_MAX_ELEMENTS = 20000


def find_symptoms(
    page: Page, selector: str, radius: int = DEFAULT_RADIUS, limit: int = MAX_ELEMENTS
) -> list[dict]:
    """Elements within `radius` steps of `selector` that show a layout symptom, nearest first."""
    return page.evaluate(_FIND_JS, [selector, radius, limit])


def heal(
    page: Page, selector: str, radius: int = DEFAULT_RADIUS, limit: int = MAX_ELEMENTS
) -> Repair | None:
    """Find the nearest symptom around `selector` and a fix that removes it."""
    for hit in find_symptoms(page, selector, radius, limit):
        for prop, value in FIXES[hit["kind"]]:
            if page.evaluate(_TRY_JS, [hit["selector"], hit["kind"], prop, value]):
                return Repair(hit["selector"], prop, value, hit["kind"], hit["distance"])
    return None


def scan_page(page: Page) -> Repair | None:
    """Heal without any model: the first symptom found on the whole page, top of the DOM first."""
    return heal(page, "body", PAGE_RADIUS, PAGE_MAX_ELEMENTS)


def _as_answer(repair: Repair) -> dict[str, str]:
    return {"selector": repair.selector, "property": repair.property, "value": repair.value}


def healed_answer(
    page: Page,
    answer: dict[str, str] | None,
    radius: int = DEFAULT_RADIUS,
    whole_page: bool = False,
) -> dict[str, str] | None:
    """The model's answer, replaced by a repair the browser confirmed.

    The browser looks around the model's element first. With `whole_page`, it scans the whole
    page when nothing is found there (or when the model gave no answer).
    """
    if answer is not None:
        repair = heal(page, answer["selector"], radius)
        if repair is not None:
            return _as_answer(repair)
    if whole_page:
        repair = scan_page(page)
        if repair is not None:
            return _as_answer(repair)
    return answer
