"""Render a page with Playwright and save a clean screenshot and DOM snapshot.

Every page in Forge is opened with `open_page`. Motion is reduced and screenshots are taken with
animations stopped, so two screenshots of the same page match. When a recorded snapshot (a HAR
file made by `python -m forge.snapshot`) is given, the page is replayed from it offline, so a
live site that changes later cannot change the page (#52).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import Browser, Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

# Viewports defined in docs/BUG_TAXONOMY.md (width, height).
VIEWPORTS: dict[str, tuple[int, int]] = {
    "mobile": (375, 812),
    "tablet": (768, 1024),
    "desktop": (1440, 900),
}

# Screenshot options: finish CSS animations and transitions, hide the text cursor.
SCREENSHOT = {"animations": "disabled", "caret": "hide"}

_IMAGES_READY_JS = """
() => Array.from(document.images)
  .filter((img) => img.getBoundingClientRect().top < window.innerHeight)
  .every((img) => img.complete)
"""


@dataclass(frozen=True)
class Capture:
    """Result of rendering one page at one viewport."""

    screenshot_path: Path
    dom_path: Path
    dom_html: str
    viewport: str
    width: int
    height: int


def snapshot_path(snapshots: Path | str | None, site: str, viewport: str) -> Path | None:
    """The recorded snapshot of one site at one viewport, or None when snapshots are not used."""
    if snapshots is None:
        return None
    return Path(snapshots) / f"{site}_{viewport}.zip"


def open_page(browser: Browser, viewport: str, har: Path | str | None = None) -> Page:
    """A new page at the viewport with reduced motion; replays `har` offline when given."""
    if viewport not in VIEWPORTS:
        raise ValueError(f"Unknown viewport '{viewport}'. Choose from {sorted(VIEWPORTS)}.")
    width, height = VIEWPORTS[viewport]
    context = browser.new_context(
        viewport={"width": width, "height": height}, reduced_motion="reduce"
    )
    if har is not None:
        if not Path(har).exists():
            raise FileNotFoundError(f"No snapshot {har}; record it with python -m forge.snapshot.")
        # Requests missing from the recording fail the same way every time, so pages stay equal.
        context.route_from_har(str(har), not_found="abort")
    return context.new_page()


def settle(page: Page) -> None:
    """Wait until late content (lazy images, icons) has loaded, so screenshots compare."""
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
        page.wait_for_function(_IMAGES_READY_JS, timeout=10000)
    except PlaywrightTimeoutError:
        pass
    page.wait_for_timeout(500)


def capture_page(
    url: str,
    viewport: str = "desktop",
    out_dir: Path | str = "data/raw",
    name: str = "page",
    har: Path | str | None = None,
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
            page = open_page(browser, viewport, har)
            page.goto(url, wait_until="load")
            settle(page)
            page.screenshot(path=str(screenshot_path), **SCREENSHOT)
            dom_html = page.content()
        finally:
            browser.close()

    dom_path.write_text(dom_html, encoding="utf-8")
    return Capture(screenshot_path, dom_path, dom_html, viewport, width, height)
