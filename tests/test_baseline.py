import base64
import json

from forge.baseline import build_request, evaluate, format_report, select_samples
from forge.dataset import Sample
from forge.scoring import Score


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


def test_build_request_shape():
    request = build_request("m", "hello", b"abc", num_ctx=4096)
    assert request["model"] == "m"
    assert request["stream"] is False
    assert request["options"] == {"num_ctx": 4096, "temperature": 0}
    message = request["messages"][0]
    assert message["role"] == "user"
    assert message["content"] == "hello"
    assert message["images"] == [base64.b64encode(b"abc").decode("ascii")]


def test_evaluate_scores_each_sample():
    correct = json.dumps(
        {"selector": "body > div:nth-of-type(1)", "property": "width", "value": "400px"}
    )
    answers = {"a": correct, "b": "I do not know"}
    seen = []
    results = evaluate(
        [make_sample(sample_id="a"), make_sample(sample_id="b")],
        lambda sample: answers[sample.sample_id],
        lambda index, total, sample, score, raw: seen.append((index, total)),
    )
    assert results[0][1].success
    assert not results[1][1].valid_json
    assert results[1][2] == "I do not know"
    assert seen == [(1, 2), (2, 2)]


def test_format_report_has_sections_and_numbers():
    results = [
        (make_sample(), Score(True, True, True, True), "x"),
        (make_sample(bug_type="OVERLAP", viewport="mobile"), Score(True, False, True, False), "y"),
    ]
    report = format_report(results)
    assert "Overall" in report
    assert "By bug_type" in report
    assert "By viewport" in report
    assert "OVERFLOW" in report
    assert "OVERLAP" in report
    assert "success=50%" in report


def test_select_samples_filters_by_site_and_spreads_the_limit():
    samples = [make_sample(sample_id=f"s{i}", site="a" if i % 2 else "b") for i in range(10)]
    assert select_samples(samples) == samples
    assert [s.site for s in select_samples(samples, ["a"])] == ["a"] * 5
    assert [s.sample_id for s in select_samples(samples, None, 5)] == [
        "s0",
        "s2",
        "s4",
        "s6",
        "s8",
    ]
    assert select_samples(samples, None, 50) == samples