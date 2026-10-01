"""Quality filter: measure how visibly a mutation changed the page."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity

# Provisional threshold. Tune on real data (see "Open decisions" in docs/BUG_TAXONOMY.md).
DEFAULT_THRESHOLD = 0.01


class ImageSizeError(ValueError):
    """Raised when the two screenshots do not have the same dimensions."""


def _load_gray(path: Path | str) -> np.ndarray:
    with Image.open(path) as img:
        return np.asarray(img.convert("L"), dtype=np.uint8)


def visual_diff(clean_path: Path | str, broken_path: Path | str) -> float:
    """Return 0 for identical screenshots, up to 1 for very different ones (1 - SSIM)."""
    clean = _load_gray(clean_path)
    broken = _load_gray(broken_path)
    if clean.shape != broken.shape:
        raise ImageSizeError(
            f"Screenshot sizes differ: {clean.shape[::-1]} vs {broken.shape[::-1]} (w, h)."
        )
    similarity = structural_similarity(clean, broken, data_range=255)
    return float(min(1.0, max(0.0, 1.0 - similarity)))


def passes_quality_filter(score: float, threshold: float = DEFAULT_THRESHOLD) -> bool:
    """Keep a sample only if its visual difference reaches the threshold."""
    return score >= threshold