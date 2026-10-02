import pytest

from forge.fixes import choose_fix
from forge.pipeline import generate_sample
from forge.scoring import gold_answer

PAGE = """<!doctype html><html><body style="margin:0">
<div style="width:400px">
<div style="height:120px;background:#c0392b"></div>
<div style="height:120px;background:#2980b9"></div>
<p>Some text</p>
</div></body></html>"""


def make(tmp_path, bug_type):
    path = tmp_path / "page.html"
    path.write_text(PAGE, encoding="utf-8")
    url = path.as_uri()
    sample = generate_sample(
        url, "demo", "desktop", bug_type, seed=1, out_dir=str(tmp_path / "out"), threshold=0.0
    )
    return url, sample


@pytest.mark.parametrize("bug_type, robust", [("CLIPPING", "auto"), ("OVERFLOW", "auto")])
def test_robust_value_is_chosen_when_it_verifies(tmp_path, bug_type, robust):
    url, sample = make(tmp_path, bug_type)
    fix = choose_fix(url, sample, tmp_path / "v")
    assert fix["value"] == robust
    assert fix["source"] == "robust"
    assert fix["property"] == sample.property


def test_overlap_keeps_the_original_value(tmp_path):
    url, sample = make(tmp_path, "OVERLAP")
    fix = choose_fix(url, sample, tmp_path / "v")
    assert fix["value"] == gold_answer(sample)["value"]
    assert fix["source"] == "original"