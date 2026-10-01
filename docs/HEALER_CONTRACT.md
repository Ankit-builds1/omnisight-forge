# Healer contract

This document fixes what the healer receives, what it must return, and how an answer is scored. Every model (zero-shot baseline, fine-tuned, later versions) is run and scored the same way, so results are comparable.

## Input

For each sample the healer gets exactly three things:

| Field | Source in `samples.jsonl` | Notes |
| --- | --- | --- |
| Broken screenshot | `broken_screenshot` | PNG, viewport-only |
| DOM snapshot | `dom_snapshot` | HTML of the broken page |
| Viewport | `viewport` | `mobile` 375x812, `tablet` 768x1024, `desktop` 1440x900 |

The healer is not given `bug_type`, `target_selector`, `property`, `gold_fix`, `clean_screenshot`, `site` or `visual_diff_score`. Those are labels or metadata, and giving them would leak the answer.

## Output

One JSON object, nothing else:

```json
{"selector": "body > main:nth-of-type(1) > section:nth-of-type(1)", "property": "width", "value": "375px"}
```

- `selector`: CSS selector of the element to fix.
- `property`: the single CSS property to change.
- `value`: the new value, including its unit.

The gold answer is derived from `target_selector`, `property` and the value part of `gold_fix` (for example `width: 375px` gives `375px`). Anything that is not valid JSON with these three string fields counts as an invalid answer.

## Metrics

Per sample:

- `valid_json`: the output parses and has the three fields.
- `selector_match`: the selector equals the gold selector after trimming whitespace.
- `property_match`: the property equals the gold property, case-insensitive.
- `value_match`: if both values are pixel numbers, they differ by at most 2 px; otherwise the strings are equal after trimming and lowercasing.
- `success`: `selector_match`, `property_match` and `value_match` are all true.

Reported over a set of samples: the rate of each metric, plus the success rate broken down by `bug_type`, by `viewport`, and by seen versus held-out sites.

## Split

Samples are split by site, never by sample. Sites in the held-out set never appear in training data. Held-out results measure out-of-distribution behaviour and are the headline number.

## Open decisions

- Which sites are held out (the split function takes the held-out site names as a parameter).
- The 2 px tolerance is a starting value; revisit it after the zero-shot baseline.
- Exact selector match is strict. A different selector that points at the same element is scored wrong for now; an element-level match using the DOM may replace it later.