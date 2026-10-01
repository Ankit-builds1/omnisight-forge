import pytest
from PIL import Image

from forge.dataset import Sample
from forge.mutations import MUTATIONS
from forge.pipeline import Rejection, generate_sample

PAGE = """<!doctype html><html><body style="margin:0">
<div style="width:400px">
<div style="height:120px;background:#c0392b"></div>
<div style="height:120px;background:#2980b9"></div>
<p>Some text</p>
</div></body></html>"""

EMPTY = "<!doctype html><html><body></body></html>"


def page_url(tmp_path, html):
    path = tmp_path / "page.html"
    path.write_text(html, encoding="utf-8")
    return path.as_uri()


@pytest.mark.parametrize("bug_type", sorted(MUTATIONS))
def test_generates_valid_sample(tmp_path, bug_type):
    url = page_url(tmp_path, PAGE)
    result = generate_sample(
        url, "demo", "mobile", bug_type, seed=1, out_dir=str(tmp_path / "out"), threshold=0.0
    )
    assert isinstance(result, Sample)
    assert result.sample_id == f"demo_mobile_{bug_type.lower()}_1"
    assert 0.0 <= result.visual_diff_score <= 1.0
    clean = Image.open(result.clean_screenshot)
    broken = Image.open(result.broken_screenshot)
    assert clean.size == broken.size
    with open(result.dom_snapshot, encoding="utf-8") as handle:
        assert "<html" in handle.read()


def test_low_visual_diff_is_rejected(tmp_path):
    url = page_url(tmp_path, PAGE)
    result = generate_sample(
        url, "demo", "mobile", "OVERFLOW", seed=1, out_dir=str(tmp_path / "out"), threshold=1.01
    )
    assert isinstance(result, Rejection)
    assert "threshold" in result.reason
    assert result.visual_diff_score is not None


def test_same_seed_gives_same_sample(tmp_path):
    url = page_url(tmp_path, PAGE)
    out = str(tmp_path / "out")
    first = generate_sample(url, "demo", "mobile", "OVERFLOW", seed=7, out_dir=out, threshold=0.0)
    second = generate_sample(url, "demo", "mobile", "OVERFLOW", seed=7, out_dir=out, threshold=0.0)
    assert (first.target_selector, first.broken_css, first.gold_fix) == (
        second.target_selector,
        second.broken_css,
        second.gold_fix,
    )


def test_empty_page_is_rejected_not_crashed(tmp_path):
    url = page_url(tmp_path, EMPTY)
    result = generate_sample(
        url, "empty", "mobile", "OVERFLOW", seed=1, out_dir=str(tmp_path / "out")
    )
    assert isinstance(result, Rejection)
    assert "no valid mutation" in result.reason


def test_unknown_bug_type_raises(tmp_path):
    url = page_url(tmp_path, PAGE)
    with pytest.raises(ValueError):
        generate_sample(url, "demo", "mobile", "NOT_A_BUG", seed=1, out_dir=str(tmp_path))