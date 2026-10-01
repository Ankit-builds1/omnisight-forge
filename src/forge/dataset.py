"""Dataset schema: one labeled UI-bug sample, stored as JSON Lines."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from forge.capture import VIEWPORTS
from forge.mutations import MUTATIONS


class SampleError(ValueError):
    """Raised when a sample does not follow the dataset schema."""


@dataclass(frozen=True)
class Sample:
    sample_id: str
    site: str
    viewport: str
    bug_type: str
    target_selector: str
    property: str
    broken_css: str
    gold_fix: str
    clean_screenshot: str
    broken_screenshot: str
    dom_snapshot: str
    visual_diff_score: float

    def __post_init__(self) -> None:
        for field in fields(self):
            if field.name != "visual_diff_score" and not getattr(self, field.name):
                raise SampleError(f"Field '{field.name}' must not be empty.")
        if self.viewport not in VIEWPORTS:
            raise SampleError(f"Unknown viewport: {self.viewport!r}.")
        if self.bug_type not in MUTATIONS:
            raise SampleError(f"Unknown bug type: {self.bug_type!r}.")
        if not 0.0 <= self.visual_diff_score <= 1.0:
            raise SampleError("visual_diff_score must be between 0 and 1.")


def append_sample(sample: Sample, path: Path | str) -> None:
    """Append one sample as a single JSON line (creates the file and folders if needed)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(asdict(sample), ensure_ascii=False) + "\n")


def read_samples(path: Path | str) -> list[Sample]:
    """Read every sample back. Invalid lines raise, so corrupt data fails loudly."""
    samples = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                samples.append(Sample(**json.loads(line)))
    return samples


class SplitError(ValueError):
    """Raised when a train/held-out split cannot be made as requested."""


def split_by_site(
    samples: list[Sample], held_out_sites: set[str] | list[str]
) -> tuple[list[Sample], list[Sample]]:
    """Split samples by site into (train, held_out).

    Every sample of a held-out site goes to held_out, so a held-out site
    never appears in train.
    """
    held = set(held_out_sites)
    if not held:
        raise SplitError("Give at least one held-out site.")
    known = {sample.site for sample in samples}
    unknown = held - known
    if unknown:
        raise SplitError(f"Unknown held-out sites: {sorted(unknown)}")
    if held >= known:
        raise SplitError("Held-out sites cover every site; nothing left to train on.")
    train = [sample for sample in samples if sample.site not in held]
    held_out = [sample for sample in samples if sample.site in held]
    return train, held_out
