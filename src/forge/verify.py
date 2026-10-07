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
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from forge.build import parse_sites
from forge.capture import (
    SCREENSHOT,
    close_browser,
    close_page,
    open_page,
    settle,
    snapshot_path,
)
from forge.dataset import Sample, read_samples
from forge.heal import healed_answer
from forge.mutations import MUTATIONS, MutationError, apply_declaration
from forge.quality import visual_diff
from forge.scoring import gold_answer, parse_answer, score_answer

# A fix may leave at most this share of the bug's pixel change on screen.
RESIDUAL_SHARE = 0.1
# A page gets this long to load, twice, before the sample is reported instead of crashing.
LOAD_TIMEOUT_MS = 60000
RETRY_DELAY_S = 5
LOAD_FAILED = "page load failed"

_EXISTS_JS = """
(sel) => {
  try { return document.querySelector(sel) !== null; } catch (e) { return false; }
}
"""


def _open(page, url: str) -> bool:
    """Load the page, retrying once after a timeout or network error; False if it never loads."""
    for attempt in range(2):
        if attempt:
            time.sleep(RETRY_DELAY_S)
        try:
            page.goto(url, timeout=LOAD_TIMEOUT_MS)
            return True
        except PlaywrightError:  # also covers timeouts
            pass
    return False


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
    snapshots: Path | str | None = None,
    heal_radius: int | None = None,
    whole_page: bool = False,
) -> Verdict:
    """Rebuild the sample's bug on `url`, apply `answer` and compare with the clean page.

    With `snapshots`, both pages are replayed offline from the recorded snapshot (#52).
    With `heal_radius`, the healer (forge.heal) may replace the answer with a repair it confirmed
    on the broken page alone, before the clean page is compared. With `whole_page`, it also scans
    the whole page when nothing is found near the answer.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    clean_png = out / f"{sample.sample_id}_clean.png"
    broken_png = out / f"{sample.sample_id}_broken.png"
    fixed_png = out / f"{sample.sample_id}_fixed.png"
    har = snapshot_path(snapshots, sample.site, sample.viewport)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            clean_page = open_page(browser, sample.viewport, har)
            if not _open(clean_page, url):
                return Verdict(False, 0.0, 0.0, LOAD_FAILED)
            settle(clean_page)
            clean_page.screenshot(path=str(clean_png), **SCREENSHOT)
            close_page(clean_page)
            page = open_page(browser, sample.viewport, har)
            if not _open(page, url):
                return Verdict(False, 0.0, 0.0, LOAD_FAILED)
            # Rebuild the bug on a fully loaded page, exactly as the build did, so it lands
            # on the same element.
            settle(page)
            try:
                mutation = MUTATIONS[sample.bug_type](page, seed=seed_of(sample))
            except (MutationError, PlaywrightError):
                # A live page that changed can lose the element the bug was built on.
                return Verdict(False, 0.0, 0.0, "page changed: the bug could not be rebuilt")
            if mutation.target_selector != sample.target_selector:
                return Verdict(False, 0.0, 0.0, "page changed: the bug landed elsewhere")
            settle(page)
            page.screenshot(path=str(broken_png), **SCREENSHOT)
            healing = heal_radius is not None or whole_page
            if answer is not None and not page.evaluate(_EXISTS_JS, answer["selector"]):
                # The healer cannot start from an element that is not there.
                answer, note = (None, "") if healing else (answer, "selector not found")
            else:
                note = ""
            if healing:
                healed = healed_answer(page, answer, heal_radius or 0, whole_page)
                if healed is not None and healed != answer:
                    note = f"healed: {healed['property']}: {healed['value']}"
                answer = healed
            if answer is None:
                note = note or "no answer"
            elif ";" in answer["value"]:
                note = "value has several declarations"
            elif note == "selector not found":
                pass
            else:
                declaration = f"{answer['property']}: {answer['value']}"
                apply_declaration(page, answer["selector"], declaration)
            page.screenshot(path=str(fixed_png), **SCREENSHOT)
        finally:
            close_browser(browser)

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
    parser.add_argument("--snapshots", help="folder from forge.snapshot; replay pages offline")
    parser.add_argument(
        "--heal", type=int, metavar="RADIUS",
        help="let forge.heal repair around the answer's element, up to RADIUS DOM steps away",
    )
    parser.add_argument(
        "--whole-page", action="store_true",
        help="let forge.heal scan the whole page when nothing is found near the answer",
    )
    parser.add_argument(
        "--no-model", action="store_true",
        help="ignore the answers: the browser scans the whole page on its own (a baseline)",
    )
    args = parser.parse_args(argv)
    if args.no_model:
        args.whole_page = True
        args.heal = None

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
        if args.no_model:
            answer = None
        verdict = verify_fix(
            sites[sample.site], sample, answer, out / "png", args.snapshots, args.heal,
            args.whole_page,
        )
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