import json
from dataclasses import asdict

import pytest

from forge.dataset import Sample, SampleError, append_sample, read_samples


def make_sample(**overrides):
    values = {
        "sample_id": "example_desktop_overflow_1",
        "site": "example",
        "viewport": "desktop",
        "bug_type": "OVERFLOW",
        "target_selector": "body > div:nth-of-type(1)",
        "property": "width",
        "broken_css": "width: 900px",
        "gold_fix": "width: 400px",
        "clean_screenshot": "data/raw/example_desktop.png",
        "broken_screenshot": "data/raw/example_desktop_broken.png",
        "dom_snapshot": "data/raw/example_desktop.html",
        "visual_diff_score": 0.12,
    }
    values.update(overrides)
    return Sample(**values)


def test_sample_has_all_schema_fields():
    expected = {
        "sample_id", "site", "viewport", "bug_type", "target_selector", "property",
        "broken_css", "gold_fix", "clean_screenshot", "broken_screenshot",
        "dom_snapshot", "visual_diff_score",
    }  # fmt: skip
    assert set(asdict(make_sample())) == expected


def test_round_trip(tmp_path):
    path = tmp_path / "samples.jsonl"
    sample = make_sample()
    append_sample(sample, path)
    assert read_samples(path) == [sample]


def test_append_writes_one_line_per_sample(tmp_path):
    path = tmp_path / "nested" / "samples.jsonl"
    append_sample(make_sample(sample_id="a"), path)
    append_sample(make_sample(sample_id="b"), path)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert [json.loads(line)["sample_id"] for line in lines] == ["a", "b"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"bug_type": "NOT_A_BUG"},
        {"viewport": "watch"},
        {"visual_diff_score": 1.5},
        {"visual_diff_score": -0.1},
        {"gold_fix": ""},
    ],
)
def test_invalid_sample_raises(overrides):
    with pytest.raises(SampleError):
        make_sample(**overrides)


def test_corrupt_line_fails_loudly(tmp_path):
    path = tmp_path / "samples.jsonl"
    bad = asdict(make_sample())
    bad["bug_type"] = "NOT_A_BUG"
    path.write_text(json.dumps(bad) + "\n", encoding="utf-8")
    with pytest.raises(SampleError):
        read_samples(path)