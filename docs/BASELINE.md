# Zero-shot baseline (v0.2)

Model: `qwen3-vl:2b-instruct` through Ollama, temperature 0, `num_ctx` 8192, `num_predict` 128.
Prompt frozen at commit `821c2df` (`src/forge/prompt.py`). Gold value fix in `f59552d`.
Data: 83 samples from 4 sites (pricing 26, album 22, blog 20, sign-in 15).
Runtime: 51 min on an RTX 2050 (about 37 s per sample).

## All sites (n=83)

| group | n | json | selector | property | value | success |
|---|---|---|---|---|---|---|
| all | 83 | 96% | 0% | 76% | 17% | 0% |
| CLIPPING | 25 | 96% | 0% | 60% | 0% | 0% |
| OVERFLOW | 25 | 92% | 0% | 64% | 0% | 0% |
| OVERLAP | 33 | 100% | 0% | 97% | 42% | 0% |
| desktop | 24 | 92% | 0% | 79% | 21% | 0% |
| mobile | 30 | 97% | 0% | 73% | 17% | 0% |
| tablet | 29 | 100% | 0% | 76% | 14% | 0% |

## Held-out site: sign-in (n=15)

The first fine-tuning run trains on pricing, album and blog (68 samples) and is tested on sign-in.
The fine-tuned model is compared against this table.

| group | n | json | selector | property | value | success |
|---|---|---|---|---|---|---|
| all | 15 | 100% | 0% | 73% | 47% | 0% |
| CLIPPING | 3 | 100% | 0% | 33% | 0% | 0% |
| OVERFLOW | 3 | 100% | 0% | 67% | 0% | 0% |
| OVERLAP | 9 | 100% | 0% | 89% | 78% | 0% |

## Constant reference

Answering `margin-top: 0px` for every sample, without looking at the input, scores 40% property
and 40% value on all sites, and 60% on both for sign-in. The 2B model beats this on property but
not on value. A fine-tuned model has to beat both rows.

## Observations

- The model gave the same selector (`body > div:nth-of-type(2) > p:nth-of-type(1)`) for every
  inspected sample, so selector 0% means a wrong element, not a formatting mismatch.
  Exact selector matching stays for now.
- In the current factory each bug type maps to one property (CLIPPING height, OVERFLOW width,
  OVERLAP margin-top) and every OVERLAP fix is `margin-top: 0px`. Property accuracy is mostly
  bug-type recognition.
- CLIPPING values were far from gold (for example 9px against 38px, 73px against 150px).
- Some samples share the same target and fix (for example `album_mobile_clipping_1` and `_2`).