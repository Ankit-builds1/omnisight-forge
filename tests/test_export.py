import json
from pathlib import Path

from forge.dataset import Sample
from forge.export import export, to_example
from forge.prompt import build_prompt
from forge.scoring import gold_answer, parse_answer


def make_sample(tmp_path: Path, sample_id: str, site: str) -> Sample:
    dom = tmp_path / f"{sample_id}.html"
    dom.write_text("<body><p>hi</p></body>", encoding="utf-8")
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
        dom_snapshot=str(dom),
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
    assert user["content"][1] == {
        "type": "text",
        "text": build_prompt("mobile", "<body><p>hi</p></body>"),
    }
    assert assistant["role"] == "assistant"


def test_answer_round_trips_through_the_scorer(tmp_path):
    sample = make_sample(tmp_path, "a_mobile_clipping_0", "a")
    answer = to_example(sample)["messages"][1]["content"][0]["text"]
    assert parse_answer(answer) == gold_answer(sample)
    assert gold_answer(sample)["value"] == "24px"


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
