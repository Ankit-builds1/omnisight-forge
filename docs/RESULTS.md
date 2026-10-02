# Healer run 1 (v0.2 dry run)

Model: `Qwen/Qwen3-VL-4B-Instruct`, loaded in 4-bit (NF4), trained with LoRA (r 16, alpha 32,
dropout 0.05) on the attention and MLP projections of the language model.
Data: 68 training samples (pricing, album, blog). Tested on the held-out site sign-in (15 samples).
Training: 2 epochs, batch 1, gradient accumulation 4, AdamW at 2e-4, screenshots capped at
640x640 pixels. Kaggle T4 (16 GB), 42 minutes, peak 13.7 GB.
Training loss: 0.160 after epoch 1, 0.069 after epoch 2.
Code: `notebooks/train_healer.py`. Answers were graded locally with `forge.scoring`.

## Held-out site: sign-in (n=15)

| model | json | selector | property | value | success |
|---|---|---|---|---|---|
| 2B zero-shot (baseline) | 100% | 0% | 73% | 47% | 0% |
| 4B zero-shot | 100% | 0% | 100% | 13% | 0% |
| 4B fine-tuned | 100% | 100% | 100% | 73% | 73% |

## Fine-tuned 4B by bug type

| bug type | n | selector | property | value | success |
|---|---|---|---|---|---|
| CLIPPING | 3 | 100% | 100% | 67% | 67% |
| OVERFLOW | 3 | 100% | 100% | 0% | 0% |
| OVERLAP | 9 | 100% | 100% | 100% | 100% |

## Notes

- 9 of the 11 successes are OVERLAP, whose fix is always `margin-top: 0px` in the current data.
  On CLIPPING and OVERFLOW together the fine-tuned model fixes 2 of 6.
- Selector accuracy went from 0% to 100%. The model picks different elements for different
  samples, so it locates the broken element instead of repeating one answer.
- OVERFLOW widths are still wrong.
- One held-out site with 15 samples is a small test. Issue #18 and more sites come next.
- Both 4B rows used the same 640x640 image cap. The 2B baseline used full-size screenshots
  through Ollama.
## Run 2: dataset v2 (8 sites)

Same model and settings as run 1. Data: dataset v2 (docs/DATASET.md), 84 training samples from
6 sites, tested on the held-out sites sign-in and wiki (20 samples). The 13 Python docs samples
were skipped in training because they were longer than 4,000 tokens.

| model | all (20) | sign-in (6) | wiki (14) |
|---|---|---|---|
| 4B zero-shot | 0% | 0% | 0% |
| 4B fine-tuned | 15% | 50% | 0% |

Every Wikipedia answer was invalid JSON: the prompt cut the HTML at 12,000 characters (the target
was often in the cut part) and the answer was cut at 128 tokens. On sign-in, CLIPPING was 3 of 3
and OVERLAP 0 of 3 (wrong element, 16px instead of 0px).

## Run 3: dataset v3 (on-screen HTML)

Dataset v3 saves only the on-screen, visible HTML and always keeps the bug target (#30), so no
prompt is cut. The answer limit is 256 tokens. All 84 training samples fit (longest 2,837 tokens).
Training took 22.6 minutes with a peak of 10.3 GB. Test: 19 samples (sign-in 6, wiki 13).

| model | all (19) | sign-in (6) | wiki (13) |
|---|---|---|---|
| 4B zero-shot | 0% | 0% | 0% |
| 4B fine-tuned | 32% | 100% | 0% |

Fine-tuned 4B by bug type: CLIPPING 3 of 8, OVERLAP 3 of 7, OVERFLOW 0 of 4.

Notes:

- Sign-in is 6 of 6 on every viewport; the OVERLAP mistake from run 2 is gone.
- 12 of 13 Wikipedia answers still hit the 256-token limit. The gold selectors are about 130 to
  300 characters, but the model keeps repeating `div:nth-of-type(1)` segments (answers of about
  680 characters) and never closes the JSON. The input is complete now, so the limit is writing
  long selectors; issue #32 replaces them with numbered elements.
- The test sets of runs 1, 2 and 3 differ, so rows are not directly comparable across runs; each
  run has its own zero-shot row.
## Run 4: numbered elements (dataset v4)

Every kept on-screen element in the saved DOM gets a number (`n` attribute) and the healer
answers `{"element": N, "property": ..., "value": ...}`; the scorer turns N back into the
selector (#32). Same model and training settings as run 3. Train 84, test 21 (sign-in 6,
wiki 15). Training took 22.3 minutes with a peak of 14.3 GB, close to the 14.6 GB limit.

| model | all (21) | sign-in (6) | wiki (15) |
|---|---|---|---|
| 4B zero-shot | 14% | 50% | 0% |
| 4B fine-tuned | 43% | 100% | 20% |

Fine-tuned 4B on wiki: valid JSON 100% (run 3: 8%), right element 93% (run 3: 0%), right
property 100%, right value 27%. By bug type on all sites: CLIPPING 44%, OVERFLOW 0%, OVERLAP 62%.

Notes:

- Answers are about 60 characters, so the looping seen in run 3 is gone.
- The model now finds the broken element on Wikipedia 14 of 15 times; the remaining errors
  are values. The gold value is the original CSS value, which the broken page no longer shows
  (for example `height: 79.1875px`), and a different value can still fix the page. Text matching
  counts those as wrong; the browser verifier (#35) will check whether a fix works.
## Browser verification of run 4 (#35)

`python -m forge.verify` rebuilds each bug from its seed on the live page, applies the proposed
fix and counts it as fixed when it removes at least 90% of the bug's pixel change. Self-check with
the gold fixes on the v4 sign-in and wiki samples: 26 of 27 fixed (96%); the one miss is a live
Wikipedia change where the bug now lands on another element.

| model | exact-text success | verified fixed |
|---|---|---|
| 4B zero-shot | 14% | 24% |
| 4B fine-tuned | 43% | 29% |

Fine-tuned 4B, verified: sign-in 50%, wiki 20%; CLIPPING 0%, OVERFLOW 0%, OVERLAP 75%.

Notes:

- Text matching overstated the fine-tuned model. Its CLIPPING heights within the 2 px tolerance
  (40px against 42px on sign-in) still cut the text, so none of them fix the page.
- Some answers that text matching calls wrong do fix the page, e.g. `margin-top: 0px` where the
  original was 8px.
- The zero-shot model fixes 2 of 4 OVERFLOW bugs with `width: 100%`; the fine-tuned model learned
  to guess the original pixel width and fixes none. Training on the original value teaches the
  model to imitate a number the broken page does not show. The next step is to train on fixes
  that the verifier has confirmed.