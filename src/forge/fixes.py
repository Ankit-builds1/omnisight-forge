"""Pick, for every sample, a fix that the browser verifier confirms (#41).

The original CSS value is often not visible on the broken page, so a model trained to repeat
it learns to guess numbers. A robust value such as `height: auto` repairs the page without
knowing the original. For each sample the candidates are tried in order and the first one the
verifier accepts is kept; the original value is the fallback.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from forge.build import parse_sites
from forge.dataset import Sample, read_samples
from forge.scoring import gold_answer
from forge.verify import verify_fix

CANDIDATES: dict[str, list[str]] = {
    "CLIPPING": ["auto"],
    "OVERFLOW": ["auto", "100%"],
    "OVERLAP": [],
}


def choose_fix(url: str, sample: Sample, out_dir: Path | str) -> dict[str, str]:
    """The first robust value that verifies, else the original value."""
    gold = gold_answer(sample)
    for value in CANDIDATES.get(sample.bug_type, []):
        if verify_fix(url, sample, {**gold, "value": value}, out_dir).fixed:
            return {"sample_id": sample.sample_id, "property": gold["property"],
                    "value": value, "source": "robust"}
    return {"sample_id": sample.sample_id, "property": gold["property"],
            "value": gold["value"], "source": "original"}


def read_fixes(path: Path | str) -> dict[str, dict[str, str]]:
    """{sample_id: fix} from a fixes.jsonl file."""
    with open(path, encoding="utf-8") as f:
        return {row["sample_id"]: row for row in map(json.loads, f)}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Choose a verified fix for every sample.")
    parser.add_argument("--samples", required=True)
    parser.add_argument("--site", action="append", required=True, metavar="NAME=URL")
    parser.add_argument("--out", required=True, help="fixes.jsonl to write")
    args = parser.parse_args(argv)

    sites = parse_sites(args.site)
    samples = [s for s in read_samples(args.samples) if s.site in sites]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, sample in enumerate(samples, start=1):
        fix = choose_fix(sites[sample.site], sample, out.parent / "fix_png")
        rows.append({**fix, "bug_type": sample.bug_type})
        print(f"{index}/{len(samples)} {sample.sample_id:30s} {fix['property']}: "
              f"{fix['value']} ({fix['source']})", flush=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    counts = Counter((r["bug_type"], r["source"]) for r in rows)
    for (bug_type, source), n in sorted(counts.items()):
        print(f"{bug_type:<10} {source:<9} {n}")


if __name__ == "__main__":
    main()