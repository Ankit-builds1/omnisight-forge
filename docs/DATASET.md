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