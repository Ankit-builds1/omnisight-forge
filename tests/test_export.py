import json
from pathlib import Path

import pytest

from forge.dataset import Sample
from forge.export import drop_duplicates, export, to_example
from forge.prompt import build_prompt
from forge.scoring import gold_answer, parse_answer

DOM = '<body><p n="1">hi</p></body>'


def make_sample(tmp_path: Path, sample_id: str, site: str, dom: str = DOM) -> Sample:
    dom_path = tmp_path / f"{sample_id}.html"
    dom_path.write_text(dom, encoding="utf-8")
    shot = tmp_path / f"{sample_id}_broken.png"
    shot.write_bytes(b"png-" + sample_id.encode())
    return Sample(
        sample_id=sample_id,
        site=site,
        viewport="mobile",
        bug_type="CLIPPING",
        target_selector="body > p:nth-of-type(1)",
        property="height",
        broken_css="height: 4px; overflow: hidden",
        gold_fix="height: 24px; overflow: visible",
        clean_screenshot=str(tmp_path / f"{sample_id}.png"),
        broken_screenshot=str(shot),
        dom_snapshot=str(dom_path),
        visual_diff_score=0.1,
    )


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_to_example_uses_the_baseline_prompt(tmp_path):
    sample = make_sample(tmp_path, "a_mobile_clipping_0", "a")
    example = to_example(sample)
    user, assistant = example["messages"]
    assert example["sample_id"] == "a_mobile_clipping_0"
    assert example["image"] == "images/a_mobile_clipping_0.png"
    assert user["role"] == "user"
    assert user["content"][0] == {"type": "image"}
    assert user["content"][1] == {"type": "text", "text": build_prompt("mobile", DOM)}
    assert assistant["role"] == "assistant"


def test_answer_uses_the_element_number_and_round_trips(tmp_path):
    sample = make_sample(tmp_path, "a_mobile_clipping_0", "a")
    answer = to_example(sample)["messages"][1]["content"][0]["text"]
    assert json.loads(answer) == {"element": 1, "property": "height", "value": "24px"}
    assert parse_answer(answer, DOM) == gold_answer(sample)


def test_to_example_rejects_a_target_without_a_number(tmp_path):
    sample = make_sample(tmp_path, "a_mobile_clipping_0", "a", dom="<body><p>hi</p></body>")
    with pytest.raises(ValueError):
        to_example(sample)


def test_export_splits_by_site_and_copies_images(tmp_path):
    samples = [
        make_sample(tmp_path, "a_mobile_clipping_0", "a"),
        make_sample(tmp_path, "a_mobile_clipping_1", "a"),
        make_sample(tmp_path, "b_mobile_clipping_0", "b"),
    ]
    out = tmp_path / "export"
    assert export(samples, ["b"], out) == (2, 1)
    train = read_jsonl(out / "train.jsonl")
    test = read_jsonl(out / "test.jsonl")
    assert [e["sample_id"] for e in train] == ["a_mobile_clipping_0", "a_mobile_clipping_1"]
    assert [e["sample_id"] for e in test] == ["b_mobile_clipping_0"]
    assert (out / "images" / "b_mobile_clipping_0.png").read_bytes() == b"png-b_mobile_clipping_0"


def test_drop_duplicates_keeps_first_of_same_target_and_fix(tmp_path):
    first = make_sample(tmp_path, "a_mobile_clipping_0", "a")
    copy = make_sample(tmp_path, "a_mobile_clipping_1", "a")
    other = make_sample(tmp_path, "b_mobile_clipping_0", "b")
    assert drop_duplicates([first, copy, other]) == [first, other]

def test_to_example_uses_a_verified_fix_when_given(tmp_path):
    sample = make_sample(tmp_path, "a_mobile_clipping_0", "a")
    fix = {"sample_id": sample.sample_id, "property": "height", "value": "auto", "source": "robust"}
    answer = to_example(sample, fix)["messages"][1]["content"][0]["text"]
    assert json.loads(answer) == {"element": 1, "property": "height", "value": "auto"}

def test_export_skips_unfixable_training_samples_but_keeps_test_samples(tmp_path):
    samples = [
        make_sample(tmp_path, "a_mobile_clipping_0", "a"),
        make_sample(tmp_path, "a_mobile_clipping_1", "a"),
        make_sample(tmp_path, "b_mobile_clipping_0", "b"),
    ]
    none = {"property": "height", "value": "24px", "source": "none"}
    fixes = {"a_mobile_clipping_1": none, "b_mobile_clipping_0": none}
    assert export(samples, ["b"], tmp_path / "export", fixes) == (1, 1)