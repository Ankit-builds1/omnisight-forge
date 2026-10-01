"""Zero-shot baseline: ask an Ollama vision model to fix each sample and score it."""

from __future__ import annotations

import argparse
import base64
import json
import urllib.request
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from forge.dataset import Sample, read_samples
from forge.prompt import build_prompt
from forge.scoring import Score, parse_answer, rates, rates_by, score_answer

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
DEFAULT_MODEL = "qwen3-vl:2b-instruct"
NUM_CTX = 8192

Result = tuple[Sample, Score, str]


def build_request(model: str, prompt: str, image: bytes, num_ctx: int = NUM_CTX) -> dict:
    """The JSON body for one Ollama chat call with a screenshot attached."""
    return {
        "model": model,
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [base64.b64encode(image).decode("ascii")],
            }
        ],
        "options": {"num_ctx": num_ctx, "temperature": 0},
    }


def ask_ollama(model: str, prompt: str, image_path: str, timeout: int = 300) -> str:
    """Send one prompt plus screenshot to the local Ollama server; return its text."""
    body = json.dumps(build_request(model, prompt, Path(image_path).read_bytes()))
    request = urllib.request.Request(
        OLLAMA_URL, data=body.encode("utf-8"), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)["message"]["content"]


def sample_asker(model: str) -> Callable[[Sample], str]:
    """A function that asks the model about one sample."""

    def ask(sample: Sample) -> str:
        dom = Path(sample.dom_snapshot).read_text(encoding="utf-8")
        prompt = build_prompt(sample.viewport, dom)
        return ask_ollama(model, prompt, sample.broken_screenshot)

    return ask


def select_samples(
    samples: list[Sample], sites: list[str] | None = None, limit: int | None = None
) -> list[Sample]:
    """Optionally keep only some sites, then take `limit` evenly spaced samples."""
    if sites:
        wanted = set(sites)
        samples = [s for s in samples if s.site in wanted]
    if limit is not None and 0 < limit < len(samples):
        step = len(samples) / limit
        samples = [samples[int(i * step)] for i in range(limit)]
    return samples


def evaluate(
    samples: list[Sample],
    ask: Callable[[Sample], str],
    on_result: Callable[[int, int, Sample, Score, str], None] | None = None,
) -> list[Result]:
    """Ask about every sample and score each answer."""
    results: list[Result] = []
    for index, sample in enumerate(samples, start=1):
        raw = ask(sample)
        score = score_answer(parse_answer(raw), sample)
        results.append((sample, score, raw))
        if on_result is not None:
            on_result(index, len(samples), sample, score, raw)
    return results


def _row(label: str, r: dict[str, float]) -> str:
    return (
        f"{label:<10} n={int(r['n']):<4} json={r['valid_json']:.0%} "
        f"selector={r['selector_match']:.0%} property={r['property_match']:.0%} "
        f"value={r['value_match']:.0%} success={r['success']:.0%}"
    )


def format_report(results: list[Result]) -> str:
    """A plain-text report: overall rates, then by bug type and viewport."""
    pairs = [(sample, score) for sample, score, _ in results]
    lines = ["Overall", _row("all", rates([score for _, score in pairs]))]
    for attribute, title in (("bug_type", "By bug_type"), ("viewport", "By viewport")):
        lines += ["", title]
        lines += [_row(key, r) for key, r in rates_by(pairs, attribute).items()]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Zero-shot healer baseline via Ollama.")
    parser.add_argument("--samples", default="data/samples.jsonl")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--sites", nargs="*", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", default="data/baseline_runs.jsonl")
    args = parser.parse_args(argv)

    samples = select_samples(read_samples(args.samples), args.sites, args.limit)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as handle:

        def record(index: int, total: int, sample: Sample, score: Score, raw: str) -> None:
            row = {"sample_id": sample.sample_id, "raw": raw, **asdict(score)}
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"[{index}/{total}] {sample.sample_id} success={score.success}", flush=True)

        results = evaluate(samples, sample_asker(args.model), record)
    print()
    print(format_report(results))


if __name__ == "__main__":
    main()