"""Quality filter: measure how much of the screenshot a mutation visibly changed."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

# Minimum share of changed pixels to keep a sample (0.0005 = 0.05% of the screenshot).
# Chosen from the first real run: samples below this changed almost nothing on screen,
# while every sample at or above it showed an obvious bug. SSIM was tried first and
# rejected visible bugs (a vanished heading scored only 0.004), see docs/BUG_TAXONOMY.md.
DEFAULT_THRESHOLD = 0.0005

# A pixel counts as changed only if a colour channel moved by more than this (out of 255).
PIXEL_TOLERANCE = 8


class ImageSizeError(ValueError):
    """Raised when the two screenshots do not have the same dimensions."""


def _load(path: Path | str) -> np.ndarray:
    with Image.open(path) as img:
        return np.asarray(img.convert("RGB"), dtype=np.int16)


def visual_diff(clean_path: Path | str, broken_path: Path | str) -> float:
    """Return the share of pixels (0 to 1) that visibly changed between two screenshots."""
    clean = _load(clean_path)
    broken = _load(broken_path)
    if clean.shape != broken.shape:
        raise ImageSizeError(
            f"Screenshot sizes differ: {clean.shape[1::-1]} vs {broken.shape[1::-1]} (w, h)."
        )
    changed = np.abs(clean - broken).max(axis=2) > PIXEL_TOLERANCE
    return float(changed.mean())


def passes_quality_filter(score: float, threshold: float = DEFAULT_THRESHOLD) -> bool:
    """Keep a sample only if its visual difference reaches the threshold."""
    return score >= threshold