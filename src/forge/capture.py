"""Render a page with Playwright and save a clean screenshot and DOM snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import sync_playwright

# Viewports defined in docs/BUG_TAXONOMY.md (width, height).
VIEWPORTS: dict[str, tuple[int, int]] = {
    "mobile": (375, 812),
    "tablet": (768, 1024),
    "desktop": (1440, 900),
}


@dataclass(frozen=True)
class Capture:
    """Result of rendering one page at one viewport."""

    screenshot_path: Path
    dom_path: Path
    dom_html: str
    viewport: str
    width: int
    height: int


def capture_page(
    url: str,
    viewport: str = "desktop",
    out_dir: Path | str = "data/raw",
    name: str = "page",
) -> Capture:
    """Open `url` at the named viewport; save a screenshot and the DOM HTML."""
    if viewport not in VIEWPORTS:
        raise ValueError(f"Unknown viewport '{viewport}'. Choose from {sorted(VIEWPORTS)}.")

    width, height = VIEWPORTS[viewport]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = out_dir / f"{name}_{viewport}.png"
    dom_path = out_dir / f"{name}_{viewport}.html"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(url, wait_until="load")
            page.screenshot(path=str(screenshot_path))
            dom_html = page.content()
        finally:
            browser.close()

    dom_path.write_text(dom_html, encoding="utf-8")
    return Capture(screenshot_path, dom_path, dom_html, viewport, width, height)