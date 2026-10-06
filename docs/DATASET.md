# Dataset v2

Built on 2026-10-01 with the bug factory after the visibility fix (#18): 8 sites, 3 viewports,
3 bug types and 2 seeds, so 144 attempts. The pages are live, so a later rebuild can differ.

## Commands

    python -m forge.build --site album=https://getbootstrap.com/docs/5.3/examples/album/ --site pricing=https://getbootstrap.com/docs/5.3/examples/pricing/ --site blog=https://getbootstrap.com/docs/5.3/examples/blog/ --site sign-in=https://getbootstrap.com/docs/5.3/examples/sign-in/ --site checkout=https://getbootstrap.com/docs/5.3/examples/checkout/ --site product=https://getbootstrap.com/docs/5.3/examples/product/ --site pydocs=https://docs.python.org/3/tutorial/introduction.html --site wiki=https://en.wikipedia.org/wiki/Web_page --seeds 2 --out-dir data/v2/raw --samples data/v2/samples.jsonl
    python -m forge.export --samples data/v2/samples.jsonl --held-out sign-in wiki --out data/v2/export

## Numbers

- Build: 112 kept, 32 rejected (CLIPPING 37/11, OVERFLOW 32/16, OVERLAP 43/5).
- Export: 8 duplicates dropped (two seeds picked the same target with the same fix).
- Train: 84 samples from album, pricing, blog, checkout, product, pydocs.
- Test: 20 samples from the held-out sites sign-in and wiki (OVERLAP 8, CLIPPING 8, OVERFLOW 4).
- Gold values: OVERFLOW 23 distinct widths, CLIPPING 23 distinct heights, OVERLAP 6 distinct
  margins (0px in 33 of 43 kept samples).
## Dataset v3

Same sites, seeds and commands as v2 with `data/v3/...` paths, built on 2026-10-02 after #30. The
saved DOM empties off-screen and invisible elements (their tags stay, so selectors stay valid) and
never touches the bug target; `shorten_dom` also drops link and media attributes.

- Build: 112 kept, 32 rejected (the same counts as v2).
- Export: 9 duplicates dropped; train 84, test 19 (sign-in 6, wiki 13).
- No prompt is cut at 12,000 characters (in v2 all 14 wiki and 13 pydocs prompts were cut).
  Longest prompts: wiki 11,346 characters, pydocs 7,987.
- The bug target is present with its inline style in all 112 saved DOMs.

Local layout (ignored by git): `data/v1` (first 4-site dataset), `data/v2`, `data/v3`, and
`data/runs/run1` to `run3` (answers and adapters of each training run).
## Dataset v4

Same sites, seeds and commands as v3 with `data/v4/...` paths, built on 2026-10-02 after #32.
Every kept element of the saved DOM has a number in its `n` attribute, and training answers use
that number.

- Build: 113 kept, 31 rejected. Export: 8 duplicates dropped; train 84, test 21 (sign-in 6,
  wiki 15). The live Wikipedia page changed between v3 and v4, so the wiki samples differ a little.
- The bug target has a number in all 113 saved DOMs, and every training answer maps back to
  the gold selector.
- No prompt is cut (limit now 20,000 characters). Longest prompts: wiki 13,306 characters,
  pydocs 8,923; up to 258 numbered elements on a page.

## Datasets v5 and v6: verified training answers

Same samples as v4; only the training answers change. `python -m forge.fixes` tries robust values
in the browser verifier (CLIPPING `height: auto`, OVERFLOW `width: auto` or `100%`) and then the
original value, and keeps the first that fixes the page (#41).

- v5: robust answers where they verify, otherwise the original value (unchecked).
- v6: every answer is checked, the original values included; samples that no single declaration
  fixes get source `none` and are left out of training (#43). Train 79, test 21.

    python -m forge.fixes --samples data/v4/samples.jsonl --site ... --out data/v6/fixes.jsonl
    python -m forge.export --samples data/v4/samples.jsonl --held-out sign-in wiki --fixes data/v6/fixes.jsonl --out data/v6/export

## Dataset v7: 17 sites

Built on 2026-10-03: the v4 sites plus cover, dashboard, carousel, features, heroes and jumbotron
(Bootstrap examples), a second Python docs page (pydocs2), a second Wikipedia article (wiki2,
"Web browser") and MDN ("margin"). 235 samples (OVERLAP 87, CLIPPING 80, OVERFLOW 68).

- Fixes on the 13 training sites: CLIPPING robust 57, none 5; OVERFLOW robust 56, none 1;
  OVERLAP original 66 (56 of them `0px`).
- Export with `--held-out sign-in wiki wiki2 mdn`: 17 duplicates dropped; train 166, test 46.
- The 2 longest training prompts (pydocs2 desktop, 4,574 tokens) are skipped in training. Seven
  desktop test prompts (6,381 to 7,192 tokens) do not fit in a 16 GB T4 at inference.