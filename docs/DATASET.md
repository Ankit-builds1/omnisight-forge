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