"""Score healer answers against the gold fix (see docs/HEALER_CONTRACT.md)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from forge.dataset import Sample
from forge.elements import element_paths

PX_TOLERANCE = 2.0
_PX = re.compile(r"^\s*(-?\d+(?:\.\d+)?)px\s*$")
_FIELDS = ("selector", "property", "value")


@dataclass(frozen=True)
class Score:
    valid_json: bool
    selector_match: bool
    property_match: bool
    value_match: bool

    @property
    def success(self) -> bool:
        return self.selector_match and self.property_match and self.value_match


def _element_selector(number: object, html: str) -> str | None:
    """Selector of a numbered element; "" for an unknown number, None if not a number."""
    if isinstance(number, str) and number.strip().isdigit():
        number = int(number)
    if isinstance(number, bool) or not isinstance(number, int):
        return None
    return element_paths(html).get(number, "")


def parse_answer(text: str, html: str | None = None) -> dict[str, str] | None:
    """Pull the JSON answer out of model text; None if it is not a valid answer.

    An answer may name the element by its `n` number instead of a selector; with the
    sample's HTML the number is turned into the selector.
    """
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match is None:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if "element" in data and html is not None:
        data = {**data, "selector": _element_selector(data["element"], html)}
    if not all(isinstance(data.get(field), str) for field in _FIELDS):
        return None
    return {field: data[field] for field in _FIELDS}


def gold_answer(sample: Sample) -> dict[str, str]:
    """The answer the healer should give, derived from the sample's labels."""
    first_declaration = sample.gold_fix.split(";")[0]
    value = first_declaration.split(":", 1)[1].strip()
    return {"selector": sample.target_selector, "property": sample.property, "value": value}


def values_match(answer: str, gold: str) -> bool:
    """Pixel values match within PX_TOLERANCE; anything else must match as text."""
    a, g = _PX.match(answer), _PX.match(gold)
    if a and g:
        return abs(float(a.group(1)) - float(g.group(1))) <= PX_TOLERANCE
    return answer.strip().lower() == gold.strip().lower()


def score_answer(answer: dict[str, str] | None, sample: Sample) -> Score:
    """Score one parsed answer (or None for an invalid one) against the sample."""
    if answer is None:
        return Score(False, False, False, False)
    gold = gold_answer(sample)
    return Score(
        valid_json=True,
        selector_match=answer["selector"].strip() == gold["selector"],
        property_match=answer["property"].strip().lower() == gold["property"].lower(),
        value_match=values_match(answer["value"], gold["value"]),
    )


def rates(scores: list[Score]) -> dict[str, float]:
    """Share of samples passing each metric."""
    if not scores:
        raise ValueError("No scores to summarise.")
    n = len(scores)
    return {
        "n": n,
        "valid_json": sum(s.valid_json for s in scores) / n,
        "selector_match": sum(s.selector_match for s in scores) / n,
        "property_match": sum(s.property_match for s in scores) / n,
        "value_match": sum(s.value_match for s in scores) / n,
        "success": sum(s.success for s in scores) / n,
    }


def rates_by(pairs: list[tuple[Sample, Score]], attribute: str) -> dict[str, dict[str, float]]:
    """Rates grouped by a sample attribute such as bug_type or viewport."""
    groups: dict[str, list[Score]] = {}
    for sample, score in pairs:
        groups.setdefault(getattr(sample, attribute), []).append(score)
    return {key: rates(group) for key, group in sorted(groups.items())}