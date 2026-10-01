# Bug Taxonomy

Version 0.1. Defines the typed UI bugs the Forge bug factory injects, the gold
fix for each, and how the verifier checks each fix. This file is the contract
for the dataset and for UI-HealBench, so change it only through a PR.

## Why this exists

- The bug factory needs an exact spec for every bug it injects.
- Dataset labels (bug type, property, gold fix) must use fixed, consistent values.
- The verifier needs one check per bug type.
- Benchmark results are reported per category, so categories must stay stable.

## Bug types

| ID | What we break (mutation) | Gold fix (inverse) | Verifier check | Tier |
|---|---|---|---|---|
| OVERFLOW | Child wider than its container (fixed oversized `width`, or `white-space: nowrap` on long text) | Restore original `width` / remove `nowrap` | Child bounding box lies inside parent box | 1 |
| OVERLAP | Two siblings overlap (negative `margin` or absolute offset) | Restore original `margin` / `position` | No intersection between sibling bounding boxes | 1 |
| CLIPPING | Text cut off (`overflow: hidden` plus too-small fixed `height`) | Restore original `height` / `overflow` | `scrollHeight <= clientHeight`, text fully visible | 1 |
| Z_INDEX | Element hidden behind another (wrong `z-index` / stacking) | Restore original `z-index` | `elementFromPoint` at the element center returns that element | 2 |
| FLEX_GRID_BREAK | Layout collapses (`flex-direction`, `flex-wrap`, or `grid-template-columns` changed) | Restore original value | Children positions match the clean render (geometry) | 2 |
| LOW_CONTRAST | Text unreadable (`color` set close to background) | Restore original `color` | Contrast ratio >= 4.5:1 (WCAG AA) | 3 |
| FONT_SIZE | Text too small (`font-size` set to 6-8px) | Restore original `font-size` | Computed `font-size` back to original value | 3 |
| MISSING_LABEL | Input label or image alt removed | Restore label / alt | axe-core rule passes | 3 |

## Build order (scope control)

- Tier 1 first: get the full pipeline working end to end on these three types.
- Tier 2 only after tier 1 works end to end.
- Tier 3 only after tiers 1 and 2 work. These overlap with the accessibility extra.

## Sample schema

Every sample stores:

- `sample_id`, `site`, `viewport` (width x height)
- `bug_type` (one ID from the table above)
- `target_selector`, `property`
- `broken_css`, `gold_fix`
- `clean_screenshot`, `broken_screenshot`, `dom_snapshot`
- `visual_diff_score`

## Mutation contract

Each mutation returns: `bug_type`, `target_selector`, `property`, `broken_css`,
`gold_fix`. The gold fix must restore the original value exactly.

## Viewports

375x812 (mobile), 768x1024 (tablet), 1440x900 (desktop).

## Quality filter

Keep a sample only if enough of the screenshot visibly changed. The score is the
share of pixels that differ from the clean render by more than 8/255 in any colour
channel. A sample needs a score of at least 0.0005 (0.05% of the screenshot).
Log how many samples are rejected per bug type.

Why not SSIM: it underweights small or flat-colour changes. On the first real run a
vanished navbar heading scored 0.004 (it looked unchanged) while changing 0.15% of
the pixels, so clearly visible bugs were rejected. The 0.0005 threshold comes from
that evidence. The weakest accepted sample (a form label overlapping another label,
0.057% of pixels) is clearly visible to a person.

Visibility rule: a mutation may only target an element fully inside the initial
viewport (top >= 0, bottom <= viewport height, left < viewport width). Screenshots
cover the viewport only, so a bug below the fold is real in the DOM but invisible in
the image.

Stability: pages whose clean screenshots differ between two identical loads are
excluded for now (the Bootstrap dashboard example has an animated chart). A
stability gate is planned as a separate issue.

## Anti-cheat rules

A proposed fix is rejected if it:

- sets `display: none`, `visibility: hidden`, or `opacity: 0`
- sets width or height to zero
- moves the element off-screen or removes it from the page
- changes the element text content

## Out of scope for v0.1

Cross-browser checks, JavaScript-driven bugs, source-code root-cause tracing,
and design-token-aware fixes.

## Open decisions (settle during v0.1)

- Which real sites form the training set and which are held out for OOD tests.