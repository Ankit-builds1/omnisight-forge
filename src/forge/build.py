"""Batch builder: generate many samples, save them, and report how many were rejected."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError

from forge.capture import VIEWPORTS
from forge.dataset import append_sample, read_samples
from forge.mutations import MUTATIONS
from forge.pipeline import Rejection, generate_sample, make_sample_id
from forge.quality import DEFAULT_THRESHOLD, ImageSizeError


@dataclass
class BuildReport:
    accepted: int = 0
    skipped: int = 0
    accepted_by_type: dict[str, int] = field(default_factory=dict)
    rejections: list[Rejection] = field(default_factory=list)

    def reject_counts(self) -> dict[str, int]:
        return dict(Counter(item.bug_type for item in self.rejections))

    def summary(self) -> str:
        rejected = self.reject_counts()
        lines = [
            f"accepted={self.accepted} skipped={self.skipped} rejected={len(self.rejections)}"
        ]
        for bug_type in sorted(set(self.accepted_by_type) | set(rejected)):
            ok = self.accepted_by_type.get(bug_type, 0)
            bad = rejected.get(bug_type, 0)
            rate = bad / (ok + bad)
            lines.append(f"  {bug_type}: {ok} accepted, {bad} rejected ({rate:.0%} reject rate)")
        return "\n".join(lines)


def build_dataset(
    sites: dict[str, str],
    out_dir: str = "data/raw",
    samples_path: str = "data/samples.jsonl",
    viewports: Sequence[str] | None = None,
    bug_types: Sequence[str] | None = None,
    seeds: Sequence[int] = range(3),
    threshold: float = DEFAULT_THRESHOLD,
) -> BuildReport:
    """Generate samples for every site x viewport x bug type x seed combination."""
    viewports = list(viewports or VIEWPORTS)
    bug_types = list(bug_types or MUTATIONS)
    path = Path(samples_path)
    done = {sample.sample_id for sample in read_samples(path)} if path.exists() else set()
    report = BuildReport()

    for site, url in sites.items():
        for viewport in viewports:
            for bug_type in bug_types:
                for seed in seeds:
                    sample_id = make_sample_id(site, viewport, bug_type, seed)
                    if sample_id in done:
                        report.skipped += 1
                        continue
                    try:
                        result = generate_sample(
                            url, site, viewport, bug_type, seed, out_dir, threshold
                        )
                    except (PlaywrightError, ImageSizeError) as error:
                        reason = f"error: {type(error).__name__}: {error}"
                        result = Rejection(sample_id, bug_type, reason)
                    if isinstance(result, Rejection):
                        report.rejections.append(result)
                    else:
                        append_sample(result, path)
                        report.accepted += 1
                        counts = report.accepted_by_type
                        counts[bug_type] = counts.get(bug_type, 0) + 1
    return report