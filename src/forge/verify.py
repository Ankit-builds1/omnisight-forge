"""Browser verifier: apply a proposed fix to the broken page and check that it looks fixed.

Text matching marks a fix wrong whenever its value differs from the original, even if the
page looks right again. The verifier rebuilds the bug from its seed on the live page, applies
the proposed declaration and compares the screenshot with the clean one (#35).

A fix counts when it removes at least 90% of the bug's visible change. The rule is relative
because an absolute pixel threshold fails on small bugs: a few clipped letters change only
about 0.03% of a desktop screenshot.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from forge.build import parse_sites
from forge.capture import VIEWPORTS
from forge.dataset import Sample, read_samples
from forge.mutations import MUTATIONS, MutationError, apply_declaration
from forge.quality import visual_diff
from forge.scoring import gold_answer, parse_answer, score_answer

# A fix may leave at most this share of the bug's pixel change on screen.
RESIDUAL_SHARE = 0.1

_EXISTS_JS = """
(sel) => {
  try { return document.querySelector(sel) !== null; } catch (e) { return false; }
}
"""


_IMAGES_READY_JS = """
() => Array.from(document.images)
  .filter((img) => img.getBoundingClientRect().top < window.innerHeight)
  .every((img) => img.complete)
"""


def _settle(page) -> None:
    """Wait until late content (lazy images, icons) has loaded, so screenshots compare."""
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
        page.wait_for_function(_IMAGES_READY_JS, timeout=10000)
    except PlaywrightTimeoutError:
        pass
    page.wait_for_timeout(500)


@dataclass(frozen=True)
class Verdict:
    """Whether a proposed fix makes the page look like the clean page again."""

    fixed: bool
    broken_diff: float
    fixed_diff: float
    note: str = ""


def seed_of(sample: Sample) -> int:
    """The seed is the last part of the sample id, e.g. wiki_mobile_overflow_1 -> 1."""
    return int(sample.sample_id.rsplit("_", 1)[1])


def verify_fix(
    url: str,
    sample: Sample,
    answer: dict[str, str] | None,
    out_dir: Path | str,
) -> Verdict:
    """Rebuild the sample's bug on `url`, apply `answer` and compare with the clean page."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    clean_png = out / f"{sample.sample_id}_clean.png"
    broken_png = out / f"{sample.sample_id}_broken.png"
    fixed_png = out / f"{sample.sample_id}_fixed.png"
    width, height = VIEWPORTS[sample.viewport]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            viewport = {"width": width, "height": height}
            clean_page = browser.new_page(viewport=viewport)
            clean_page.goto(url)
            _settle(clean_page)
            clean_page.screenshot(path=str(clean_png))
            clean_page.close()
            page = browser.new_page(viewport=viewport)
            page.goto(url)
            try:
                mutation = MUTATIONS[sample.bug_type](page, seed=seed_of(sample))
            except MutationError:
                return Verdict(False, 0.0, 0.0, "page changed: the bug could not be rebuilt")
            if mutation.target_selector != sample.target_selector:
                return Verdict(False, 0.0, 0.0, "page changed: the bug landed elsewhere")
            _settle(page)
            page.screenshot(path=str(broken_png))
            if answer is None:
                note = "no answer"
            elif ";" in answer["value"]:
                note = "value has several declarations"
            elif not page.evaluate(_EXISTS_JS, answer["selector"]):
                note = "selector not found"
            else:
                declaration = f"{answer['property']}: {answer['value']}"
                apply_declaration(page, answer["selector"], declaration)
                note = ""
            page.screenshot(path=str(fixed_png))
        finally:
            browser.close()

    broken_diff = visual_diff(clean_png, broken_png)
    fixed_diff = visual_diff(clean_png, fixed_png)
    if broken_diff == 0:
        return Verdict(False, broken_diff, fixed_diff, note or "bug not visible")
    fixed = fixed_diff <= RESIDUAL_SHARE * broken_diff
    return Verdict(fixed, broken_diff, fixed_diff, note)

def summary(rows: list[dict]) -> str:
    """Verified fix rate next to the exact-text success rate, overall, by site and bug type."""
    lines = []
    for key in ("all", "site", "bug_type"):
        groups: dict[str, list[dict]] = {}
        for row in rows:
            groups.setdefault("all" if key == "all" else row[key], []).append(row)
        for name, group in sorted(groups.items()):
            fixed = sum(r["fixed"] for r in group) / len(group)
            text = sum(r["text_success"] for r in group) / len(group)
            lines.append(
                f"{name:<10} n={len(group):<3} verified_fixed={fixed:.0%} text_success={text:.0%}"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Check proposed fixes in a real browser.")
    parser.add_argument("--samples", required=True)
    parser.add_argument("--preds", help="answers file with sample_id and raw; omit for gold")
    parser.add_argument("--site", action="append", required=True, metavar="NAME=URL")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    sites = parse_sites(args.site)
    samples = [s for s in read_samples(args.samples) if s.site in sites]
    raw = None
    if args.preds:
        with open(args.preds, encoding="utf-8") as f:
            raw = {row["sample_id"]: row["raw"] for row in map(json.loads, f)}
        samples = [s for s in samples if s.sample_id in raw]
    out = Path(args.out)

    rows = []
    for index, sample in enumerate(samples, start=1):
        if raw is None:
            answer = gold_answer(sample)
        else:
            html = Path(sample.dom_snapshot).read_text(encoding="utf-8")
            answer = parse_answer(raw[sample.sample_id], html)
        verdict = verify_fix(sites[sample.site], sample, answer, out / "png")
        text_ok = score_answer(answer, sample).success
        rows.append(
            {"sample_id": sample.sample_id, "site": sample.site, "bug_type": sample.bug_type,
             "text_success": text_ok, **asdict(verdict)}
        )
        print(f"{index}/{len(samples)} {sample.sample_id:30s} fixed={verdict.fixed} "
              f"text={text_ok} {verdict.note}", flush=True)

    out.mkdir(parents=True, exist_ok=True)
    with (out / "verdicts.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    print(summary(rows))


if __name__ == "__main__":
    main()