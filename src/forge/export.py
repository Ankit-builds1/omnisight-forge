"""Turn samples into chat-style training examples for fine-tuning."""

import argparse
import json
import shutil
from pathlib import Path

from forge.dataset import Sample, read_samples, split_by_site
from forge.prompt import build_prompt
from forge.scoring import gold_answer

DEFAULT_HELD_OUT = ["sign-in"]


def image_name(sample: Sample) -> str:
    """File name of the sample's broken screenshot inside the export."""
    return sample.sample_id + Path(sample.broken_screenshot).suffix


def to_example(sample: Sample) -> dict:
    """One training example: screenshot + baseline prompt in, gold JSON out."""
    dom = Path(sample.dom_snapshot).read_text(encoding="utf-8")
    prompt = build_prompt(sample.viewport, dom)
    answer = json.dumps(gold_answer(sample))
    return {
        "sample_id": sample.sample_id,
        "image": f"images/{image_name(sample)}",
        "messages": [
            {
                "role": "user",
                "content": [{"type": "image"}, {"type": "text", "text": prompt}],
            },
            {
                "role": "assistant",
                "content": [{"type": "text", "text": answer}],
            },
        ],
    }


def drop_duplicates(samples: list[Sample]) -> list[Sample]:
    """Keep the first sample per site, viewport, bug type, target and gold fix.

    Two seeds can pick the same element with the same fix. The copy repeats a question
    the model already has, and in the test set it would be counted twice.
    """
    seen = set()
    unique = []
    for sample in samples:
        key = (
            sample.site,
            sample.viewport,
            sample.bug_type,
            sample.target_selector,
            sample.gold_fix,
        )
        if key not in seen:
            seen.add(key)
            unique.append(sample)
    return unique


def export(
    samples: list[Sample], held_out_sites: list[str], out_dir: Path | str
) -> tuple[int, int]:
    """Write train.jsonl, test.jsonl and images/; return (train, test) counts."""
    train, test = split_by_site(samples, held_out_sites)
    out = Path(out_dir)
    images = out / "images"
    images.mkdir(parents=True, exist_ok=True)
    for file_name, part in (("train.jsonl", train), ("test.jsonl", test)):
        with (out / file_name).open("w", encoding="utf-8", newline="\n") as handle:
            for sample in part:
                shutil.copyfile(sample.broken_screenshot, images / image_name(sample))
                handle.write(json.dumps(to_example(sample), ensure_ascii=False) + "\n")
    return len(train), len(test)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Export samples as chat training data.")
    parser.add_argument("--samples", required=True)
    parser.add_argument("--held-out", nargs="+", default=DEFAULT_HELD_OUT)
    parser.add_argument("--out", default="data/export")
    args = parser.parse_args(argv)

    samples = read_samples(args.samples)
    unique = drop_duplicates(samples)
    print(f"dropped {len(samples) - len(unique)} duplicate samples")
    n_train, n_test = export(unique, args.held_out, args.out)
    print(f"train={n_train} test={n_test} -> {args.out}")


if __name__ == "__main__":
    main()