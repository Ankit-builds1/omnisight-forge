"""Pipeline: capture a page, break it, filter the result, return a labeled sample."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import sync_playwright

from forge.capture import capture_page
from forge.dataset import Sample
from forge.mutations import MUTATIONS, MutationError
from forge.quality import DEFAULT_THRESHOLD, passes_quality_filter, visual_diff


@dataclass(frozen=True)
class Rejection:
    """A sample attempt that was dropped, with the reason (kept so we can count rejects)."""

    sample_id: str
    bug_type: str
    reason: str
    visual_diff_score: float | None = None


def generate_sample(
    url: str,
    site: str,
    viewport: str,
    bug_type: str,
    seed: int,
    out_dir: str = "data/raw",
    threshold: float = DEFAULT_THRESHOLD,
) -> Sample | Rejection:
    """Create one labeled sample, or a Rejection if no valid, visible bug could be made."""
    if bug_type not in MUTATIONS:
        raise ValueError(f"Unknown bug type: {bug_type!r}.")

    sample_id = f"{site}_{viewport}_{bug_type.lower()}_{seed}"
    out = Path(out_dir)
    clean = capture_page(url, viewport=viewport, out_dir=out_dir, name=site)
    broken_png = out / f"{sample_id}_broken.png"
    broken_html = out / f"{sample_id}_broken.html"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": clean.width, "height": clean.height})
            page.goto(url)
            try:
                mutation = MUTATIONS[bug_type](page, seed=seed)
            except MutationError as error:
                return Rejection(sample_id, bug_type, f"no valid mutation: {error}")
            page.screenshot(path=str(broken_png))
            broken_dom = page.content()
        finally:
            browser.close()

    broken_html.write_text(broken_dom, encoding="utf-8")
    score = visual_diff(clean.screenshot_path, broken_png)
    if not passes_quality_filter(score, threshold):
        return Rejection(sample_id, bug_type, "below visual-diff threshold", score)

    return Sample(
        sample_id=sample_id,
        site=site,
        viewport=viewport,
        bug_type=bug_type,
        target_selector=mutation.target_selector,
        property=mutation.property,
        broken_css=mutation.broken_css,
        gold_fix=mutation.gold_fix,
        clean_screenshot=Path(clean.screenshot_path).as_posix(),
        broken_screenshot=broken_png.as_posix(),
        dom_snapshot=broken_html.as_posix(),
        visual_diff_score=score,
    )