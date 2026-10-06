"""Pick, for every sample, a fix that the browser verifier confirms (#41, #43).

The original CSS value is often not visible on the broken page, so a model trained to repeat
it learns to guess numbers. A robust value such as `height: auto` repairs the page without
knowing the original. For each sample the robust candidates and then the original value are
tried in the verifier, and the first one that fixes the page is kept. If none does, the sample
gets source "none" and is left out of training: a CLIPPING bug also sets `overflow: hidden`,
and on some elements no single declaration can undo both.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from forge.build import parse_sites
from forge.dataset import Sample, read_samples
from forge.scoring import gold_answer
from forge.verify import LOAD_FAILED, verify_fix

CANDIDATES: dict[str, list[str]] = {
    "CLIPPING": ["auto"],
    "OVERFLOW": ["auto", "100%"],
    "OVERLAP": [],
}
# The page did not load; the sample is not saved, so the next run tries it again.
UNLOADED = "unloaded"


def choose_fix(
    url: str, sample: Sample, out_dir: Path | str, snapshots: Path | str | None = None
) -> dict[str, str]:
    """The first value that verifies: robust candidates, then the original; else "none"."""
    gold = gold_answer(sample)
    for value in [*CANDIDATES.get(sample.bug_type, []), gold["value"]]:
        verdict = verify_fix(url, sample, {**gold, "value": value}, out_dir, snapshots)
        if verdict.fixed:
            source = "original" if value == gold["value"] else "robust"
            return {"sample_id": sample.sample_id, "property": gold["property"],
                    "value": value, "source": source}
        if verdict.note == LOAD_FAILED:
            return {"sample_id": sample.sample_id, "property": gold["property"],
                    "value": gold["value"], "source": UNLOADED}
    return {"sample_id": sample.sample_id, "property": gold["property"],
            "value": gold["value"], "source": "none"}


def read_fixes(path: Path | str) -> dict[str, dict[str, str]]:
    """{sample_id: fix} from a fixes.jsonl file."""
    with open(path, encoding="utf-8") as f:
        return {row["sample_id"]: row for row in map(json.loads, f)}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Choose a verified fix for every sample.")
    parser.add_argument("--samples", required=True)
    parser.add_argument("--site", action="append", required=True, metavar="NAME=URL")
    parser.add_argument(
        "--out", required=True,
        help="fixes.jsonl; samples already in it are skipped, so a stopped run resumes",
    )
    parser.add_argument("--snapshots", help="folder from forge.snapshot; replay pages offline")
    args = parser.parse_args(argv)

    sites = parse_sites(args.site)
    samples = [s for s in read_samples(args.samples) if s.site in sites]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = read_fixes(out) if out.exists() else {}
    rows = list(done.values())
    todo = [s for s in samples if s.sample_id not in done]
    if done:
        print(f"resuming: {len(done)} already done, {len(todo)} to go", flush=True)
    with out.open("a", encoding="utf-8", newline="\n") as f:
        for index, sample in enumerate(todo, start=1):
            fix = choose_fix(sites[sample.site], sample, out.parent / "fix_png", args.snapshots)
            if fix["source"] == UNLOADED:
                print(f"{index}/{len(todo)} {sample.sample_id:30s} page did not load; "
                      "rerun to retry", flush=True)
                continue
            row = {**fix, "bug_type": sample.bug_type}
            f.write(json.dumps(row) + "\n")
            f.flush()
            rows.append(row)
            print(f"{index}/{len(todo)} {sample.sample_id:30s} {fix['property']}: "
                  f"{fix['value']} ({fix['source']})", flush=True)
    counts = Counter((r["bug_type"], r["source"]) for r in rows)
    for (bug_type, source), n in sorted(counts.items()):
        print(f"{bug_type:<10} {source:<9} {n}")


if __name__ == "__main__":
    main()