"""Check any web page for layout bugs and write an HTML report with suggested fixes.

    python -m forge.report --url https://example.com --out reports/example

For every viewport the page is opened in Chromium and scanned for the three layout symptoms of
forge.heal (an element sticking out of its parent, an element pulled over the one above it, an
element hiding part of its own content). Each symptom gets the first fix that removes it, with a
before and after picture of that area. Nothing is changed on the real site: the report only
suggests CSS for a developer to review, because some symptoms are intended (a slider, text cut
with an ellipsis).

`--demo-bug` first breaks the page with the bug factory (forge.mutations), to show a repair on a
page that has no bug of its own.
"""

from __future__ import annotations

import argparse
import html
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from forge.capture import SCREENSHOT, VIEWPORTS, close_browser, close_page, open_page, settle
from forge.heal import _SYMPTOMS_JS, FIXES, PAGE_MAX_ELEMENTS, PAGE_RADIUS, find_symptoms
from forge.mutations import MUTATIONS, MutationError

# Most findings reported per viewport, so a page full of intended symptoms stays readable.
MAX_FINDINGS = 10
# Space around the element in the before and after pictures, in CSS pixels.
MARGIN = 40

PROBLEMS = {
    "overflow": "sticks out of its parent",
    "overlap": "is pulled over the element above it",
    "clipping": "hides part of its own content",
}

_RECT_JS = """
(sel) => {
  const r = document.querySelector(sel).getBoundingClientRect();
  return {x: r.left, y: r.top, width: r.width, height: r.height};
}
"""

# Apply a fix and return what to put back; then a second call restores it.
_SET_JS = """
([sel, prop, val]) => {
  const el = document.querySelector(sel);
  const old = [el.style.getPropertyValue(prop), el.style.getPropertyPriority(prop)];
  el.style.setProperty(prop, val, 'important');
  return old;
}
"""
_RESTORE_JS = """
([sel, prop, old]) => {
  const el = document.querySelector(sel);
  if (old[0]) el.style.setProperty(prop, old[0], old[1]);
  else el.style.removeProperty(prop);
}
"""

_STILL_SICK_JS = """
([sel, kind]) => {
  //SYMPTOMS//
  return symptoms[kind](document.querySelector(sel));
}
""".replace("//SYMPTOMS//", _SYMPTOMS_JS)


@dataclass(frozen=True)
class Finding:
    """One symptom on the page and a CSS fix that removes it."""

    viewport: str
    selector: str
    kind: str
    property: str
    value: str
    before: str
    after: str


def _clip(page: Page, selector: str, viewport: str) -> dict:
    """The element's area plus a margin, kept inside the viewport."""
    rect = page.evaluate(_RECT_JS, selector)
    width, height = VIEWPORTS[viewport]
    x = max(0, rect["x"] - MARGIN)
    y = max(0, rect["y"] - MARGIN)
    right = min(width, rect["x"] + rect["width"] + MARGIN)
    bottom = min(height, rect["y"] + rect["height"] + MARGIN)
    return {"x": x, "y": y, "width": max(1, right - x), "height": max(1, bottom - y)}


def _still_sick(page: Page, selector: str, kind: str) -> bool:
    return page.evaluate(_STILL_SICK_JS, [selector, kind])


def check_page(page: Page, viewport: str, out: Path) -> list[Finding]:
    """Find symptoms on the loaded page, try fixes and save before/after pictures."""
    findings = []
    hits = find_symptoms(page, "body", PAGE_RADIUS, PAGE_MAX_ELEMENTS)
    for hit in hits:
        if len(findings) == MAX_FINDINGS:
            break
        selector, kind = hit["selector"], hit["kind"]
        clip = _clip(page, selector, viewport)
        name = f"{viewport}_{len(findings) + 1}"
        before = out / f"{name}_before.png"
        # A red outline marks the element in both pictures; outlines do not change the layout.
        mark = page.evaluate(_SET_JS, [selector, "outline", "3px solid red"])
        page.screenshot(path=str(before), clip=clip, **SCREENSHOT)
        for prop, value in FIXES[kind]:
            old = page.evaluate(_SET_JS, [selector, prop, value])
            cured = not _still_sick(page, selector, kind)
            if cured:
                after = out / f"{name}_after.png"
                page.screenshot(path=str(after), clip=clip, **SCREENSHOT)
            page.evaluate(_RESTORE_JS, [selector, prop, old])
            if cured:
                findings.append(
                    Finding(viewport, selector, kind, prop, value, before.name, after.name)
                )
                break
        else:
            before.unlink(missing_ok=True)
        page.evaluate(_RESTORE_JS, [selector, "outline", mark])
    return findings


def write_report(url: str, findings: list[Finding], viewports: list[str], out: Path) -> Path:
    """A self-contained HTML page (pictures next to it) listing every finding."""
    rows = []
    for f in findings:
        rows.append(
            "<tr>"
            f"<td>{f.viewport}</td>"
            f"<td><code>{html.escape(f.selector)}</code><br>{PROBLEMS[f.kind]}</td>"
            f"<td><code>{f.property}: {f.value};</code></td>"
            f'<td><img src="{f.before}" alt="before"></td>'
            f'<td><img src="{f.after}" alt="after"></td>'
            "</tr>"
        )
    body = "\n".join(rows) or '<tr><td colspan="5">No layout symptom found.</td></tr>'
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OmniSight Forge report</title>
<style>
  body {{ font: 15px/1.5 system-ui, sans-serif; margin: 24px; color: #1d1d1f; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border-bottom: 1px solid #ddd; padding: 8px; text-align: left; vertical-align: top; }}
  img {{ max-width: 320px; border: 1px solid #ccc; }}
  code {{ font-size: 13px; word-break: break-all; }}
  .note {{ color: #555; }}
</style></head><body>
<h1>Layout check</h1>
<p><a href="{html.escape(url)}">{html.escape(url)}</a>, viewports: {", ".join(viewports)}.
{len(findings)} finding(s).</p>
<p class="note">Each fix was tried in Chromium and removed the symptom. Review before applying:
some symptoms are intended (sliders, text cut with an ellipsis).</p>
<table>
<tr><th>viewport</th><th>element and problem</th><th>suggested CSS</th><th>before</th>
<th>after</th></tr>
{body}
</table>
</body></html>
"""
    path = out / "report.html"
    path.write_text(page, encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Check a web page for layout bugs.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--out", required=True, help="folder for report.html and pictures")
    parser.add_argument(
        "--viewport", action="append", choices=sorted(VIEWPORTS),
        help="repeat for several; default: all three",
    )
    parser.add_argument(
        "--demo-bug", choices=sorted(MUTATIONS),
        help="first inject this bug from the bug factory, to demonstrate a repair",
    )
    parser.add_argument("--seed", type=int, default=0, help="seed for --demo-bug")
    args = parser.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    viewports = args.viewport or list(VIEWPORTS)
    findings: list[Finding] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for viewport in viewports:
                page = open_page(browser, viewport)
                page.goto(args.url, timeout=60000)
                settle(page)
                if args.demo_bug:
                    try:
                        bug = MUTATIONS[args.demo_bug](page, seed=args.seed)
                        print(f"{viewport}: injected {bug.broken_css} on {bug.target_selector}")
                    except MutationError as error:
                        print(f"{viewport}: {error}")
                page.screenshot(path=str(out / f"{viewport}_page.png"), **SCREENSHOT)
                found = check_page(page, viewport, out)
                print(f"{viewport}: {len(found)} finding(s)")
                findings.extend(found)
                close_page(page)
        finally:
            close_browser(browser)
    print(write_report(args.url, findings, viewports, out))


if __name__ == "__main__":
    main()
