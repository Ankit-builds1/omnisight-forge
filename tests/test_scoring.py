import pytest

from forge.dataset import Sample
from forge.scoring import (
    Score,
    gold_answer,
    parse_answer,
    rates,
    rates_by,
    score_answer,
    values_match,
)


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


def good_answer(**overrides):
    answer = {"selector": "body > div:nth-of-type(1)", "property": "width", "value": "400px"}
    answer.update(overrides)
    return answer


def test_parse_plain_json():
    text = '{"selector": "a", "property": "width", "value": "10px"}'
    assert parse_answer(text) == {"selector": "a", "property": "width", "value": "10px"}


def test_parse_json_inside_code_fence_and_text():
    text = 'Sure:\n```json\n{"selector": "a", "property": "width", "value": "10px"}\n```\nDone.'
    assert parse_answer(text)["value"] == "10px"


@pytest.mark.parametrize(
    "text",
    [
        "no json here",
        '{"selector": "a"}',
        '{"selector": "a", "property": "width", "value": 5}',
        "[1, 2]",
        "{not json}",
    ],
)
def test_parse_rejects_invalid_answers(text):
    assert parse_answer(text) is None


def test_gold_answer_comes_from_sample_labels():
    assert gold_answer(make_sample()) == good_answer()


def test_gold_value_ignores_trailing_semicolon():
    assert gold_answer(make_sample(gold_fix="width: 400px;"))["value"] == "400px"


def test_perfect_answer_succeeds():
    score = score_answer(good_answer(), make_sample())
    assert score == Score(True, True, True, True)
    assert score.success


def test_value_within_pixel_tolerance_matches():
    assert values_match("401px", "400px")
    assert values_match("398px", "400px")
    assert not values_match("403px", "400px")


def test_non_pixel_values_compare_as_text():
    assert values_match("AUTO", "auto")
    assert not values_match("50%", "100%")


def test_wrong_selector_is_not_a_success():
    score = score_answer(good_answer(selector="body > p"), make_sample())
    assert score.valid_json
    assert not score.selector_match
    assert not score.success


def test_invalid_answer_scores_all_false():
    assert score_answer(None, make_sample()) == Score(False, False, False, False)


def test_rates_and_rates_by():
    ok = Score(True, True, True, True)
    bad = Score(True, False, True, False)
    result = rates([ok, bad])
    assert result["n"] == 2
    assert result["success"] == 0.5
    assert result["property_match"] == 1.0
    pairs = [
        (make_sample(viewport="desktop"), ok),
        (make_sample(viewport="mobile"), bad),
    ]
    by = rates_by(pairs, "viewport")
    assert by["desktop"]["success"] == 1.0
    assert by["mobile"]["success"] == 0.0


def test_rates_rejects_empty_input():
    with pytest.raises(ValueError):
        rates([])

def test_gold_answer_keeps_only_first_declaration():
    from forge.dataset import Sample
    from forge.scoring import gold_answer

    sample = Sample(
        sample_id="x_desktop_clipping_0",
        site="x",
        viewport="desktop",
        bug_type="CLIPPING",
        target_selector="body > p",
        property="height",
        broken_css="height: 4px; overflow: hidden",
        gold_fix="height: 24px; overflow: visible",
        clean_screenshot="data/raw/x.png",
        broken_screenshot="data/raw/x_broken.png",
        dom_snapshot="data/raw/x.html",
        visual_diff_score=0.1,
    )
    assert gold_answer(sample) == {
        "selector": "body > p",
        "property": "height",
        "value": "24px",
    }


def test_answer_with_element_number_is_turned_into_the_selector():
    html = '<html><body><div n="1">x</div><p n="2">y</p></body></html>'
    text = '{"element": 1, "property": "width", "value": "1px"}'
    answer = parse_answer(text, html)
    assert answer["selector"] == "body > div:nth-of-type(1)"
    assert score_answer(answer, make_sample()).selector_match


def test_unknown_element_number_is_a_wrong_selector():
    html = '<html><body><div n="1">x</div></body></html>'
    answer = parse_answer('{"element": 9, "property": "width", "value": "1px"}', html)
    assert answer is not None
    assert not score_answer(answer, make_sample()).selector_match