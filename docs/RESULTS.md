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
## Run 5: training on verified fixes (#41)

Same v4 samples, model and settings as run 4; only the training answers changed. For every
sample `python -m forge.fixes` tried robust values in the browser verifier and kept the first that
fixed the page: CLIPPING `height: auto` (33 of 38), OVERFLOW `width: auto` (31 of 32) or `100%`
(1 of 32); the other 5 CLIPPING samples and all OVERLAP samples keep the original value. Dataset
v5 = v4 samples + these answers (`--fixes data/v5/fixes.jsonl` on export).

Verified in the browser on the same 21 test samples:

| model | all | sign-in | wiki | CLIPPING | OVERFLOW | OVERLAP |
|---|---|---|---|---|---|---|
| 4B zero-shot | 24% | 50% | 13% | 0% | 50% | 38% |
| run 4 fine-tuned | 29% | 50% | 20% | 0% | 0% | 75% |
| run 5 fine-tuned | 57% | 50% | 60% | 22% | 100% | 75% |

Notes:

- The model now answers `width: auto` and `height: auto` on pages it never saw; every OVERFLOW
  test bug is fixed.
- On sign-in it answers `height: 44px` for the clipped button (original 42px). The text is no
  longer cut, but the button stays 2px taller than the clean page, so the verifier rejects it. The
  5 training CLIPPING samples where `auto` failed are buttons and inputs with pixel heights, which
  likely taught this.
- Two wiki CLIPPING answers name the wrong element; one wiki sample is a live-page change.
## Run 6: only verified training answers (#43)

Dataset v6: the v4 training samples with answers from `python -m forge.fixes`, which now checks
every answer in the browser verifier, the original values included. 5 CLIPPING samples where no
single declaration fixes the page (the leftover `overflow: hidden` still cuts blog nav links and
checkout labels) are left out of training. Train 79, test 21 (unchanged). Training took 24.8
minutes with a peak of 14.3 GB.

| model | all | sign-in | wiki | CLIPPING | OVERFLOW | OVERLAP |
|---|---|---|---|---|---|---|
| run 5 fine-tuned | 57% | 50% | 60% | 22% | 100% | 75% |
| run 6 fine-tuned | 76% | 100% | 67% | 67% | 100% | 75% |

Notes:

- The sign-in button now gets `height: auto` on all 3 viewports (run 5: `44px`), so sign-in is
  6 of 6.
- The 3 remaining CLIPPING misses on wiki are pixel heights (`10px`, `16px`); one wiki OVERLAP
  answer names the wrong element; one wiki sample is a live-page change and counts as not fixed.
- Exact-text success is 33% because most fixed answers (`auto`) differ from the original CSS, so
  text matching no longer measures the model; the verifier does.

## Run 7: 17 sites (dataset v7)

Same model and settings as run 6, trained on 164 verified answers from 13 sites (2 long pydocs2
pages skipped). Training: epoch losses 0.0431 and 0.0185, 37.9 minutes, peak 14.1 GB. Test: 46
samples from 4 held-out sites (sign-in, wiki, wiki2, mdn).

Seven desktop test pages (mdn 1, wiki2 6) ran out of memory on one T4. Splitting the model over
two T4s recovered the mdn page; the six wiki2 pages (about 7,000 tokens) still do not fit and
count as no answer.

### How much of the test can be measured

Verifying the gold fixes on the same pages (`forge.verify` without `--preds`) shows the ceiling:
only 58% of the 50 v7 test samples verify. 14 live pages changed since they were captured (the bug
lands elsewhere or cannot be rebuilt), and on MDN desktop and some tablet pages the screenshots
never match even with the gold fix. A model score on all samples therefore mixes model errors with
measurement errors, so runs are compared on the 26 samples where the gold fix verifies.

### Run 6 and run 7 on the same test

Run 6's adapter answered the same 46 v7 test samples (no retraining), then both were verified.

| on the 26 measurable samples | run 6 (79 train) | run 7 (164 train) |
|---|---|---|
| all | **18/26 = 69%** | 17/26 = 65% |
| sign-in | 6/6 | 6/6 |
| wiki | 6/7 | 5/7 |
| mdn | 3/4 | 3/4 |
| wiki2 | 3/9 | 3/9 |
| CLIPPING | 8/12 | 8/12 |
| OVERFLOW | 3/6 | 4/6 |
| OVERLAP | 7/8 | 5/8 |

Notes:

- The two runs are within one sample of each other; doubling the training data from mostly
  Bootstrap pages did not help. The limit is the variety of the data and the measurement, not
  the amount.
- Run 7 answers `margin-top: 14px` on six wiki and wiki2 OVERLAP samples, a value it took from
  the pydocs training pages; that costs it two OVERLAP fixes.
- Run 7 names the right element in 30 of the 34 answered samples that could be rebuilt (88%).
- Run 6 is kept as the v0.2 model.

### Limits found in this release

- Live pages: tests on live sites drift; v0.3 moves the benchmark to saved page snapshots.
- Shortcut: the bug factory writes the broken value as an inline style, which is visible in the
  HTML the model reads. v0.3 injects bugs through a stylesheet so only the screenshot shows them.
- Variety: 11 of the 13 training sites are Bootstrap examples.
- Memory: test pages above about 6,400 tokens do not fit on a 16 GB T4.

# v0.3: a measurement that can be trusted

## Offline snapshots (#52)

`python -m forge.snapshot` records each site and viewport once into a HAR file; build, fixes and
verify replay it offline with `--snapshots`. Pages open with reduced motion, screenshots stop
animations, and the verifier rebuilds each bug on a fully loaded page, as the build does.

Gold self-check (how many correct answers the verifier accepts) on the 4 test sites:

| pages | gold fixes accepted |
|---|---|
| live (v7 test) | 58% |
| snapshots, bug rebuilt before the page settled | 76% (39/51) |
| snapshots, bug rebuilt after the page settled | **96% (49/51)** |

The two remaining misses are MDN clipped links that no single declaration can undo.

## Hidden bugs (#54)

The bug factory used to write the broken value as an inline style, so the HTML the model reads
showed it. Bugs now go into a constructed style sheet (`document.adoptedStyleSheets`) that is not
part of the HTML; fixes are applied as `!important` inline styles.

| test set (4 sites, snapshots, 2 seeds) | HTML shows the broken CSS | gold fixes accepted |
|---|---|---|
| inline bugs | 51 of 51 samples | 96% |
| hidden bugs | 0 of 54 samples | 96% (52/54) |

## The v0.2 model relied on the inline-style clue

Run 6's adapter answered both test sets above, with the same prompt and the same pages; the only
difference is whether the broken value is visible in the HTML. Counted on samples whose gold fix
verifies; 6 wiki2 desktop pages in each set ran out of memory and have no answer.

| run 6 | clue visible | clue hidden |
|---|---|---|
| right element (of answered) | 38/39 = 97% | 0/42 = 0% |
| right property (of answered) | 97% | 21% |
| verified fixed | 30/43 = 70% | **0/46 = 0%** |

Without the clue the model guesses: a wrong element on every page, often with an unrelated
property (`margin` on 15 pages, `display: none` on 2). Run 6 had learned to find the element
with an unusual inline style in the HTML, not to read the screenshot, so the v0.2 numbers measure
that shortcut. Training must use hidden bugs, so that the screenshot is the only evidence.

## Run 8: hidden bugs on 36 sites (dataset v8)

Dataset v8: hidden bugs (#54), offline snapshots (#52) and the compact prompt (#58), built on 26
training sites and 9 held-out test sites (careers pages, shops, docs, wikis, landing pages and
forms). Training answers are verified fixes from `forge.fixes`. Train 296 (17 pages above 4,000
tokens skipped, 279 used), test 110. Screenshots capped at 896x896 pixels. Same model and LoRA
settings as run 6. Training: epoch losses 0.2752 and 0.1711, 83.5 minutes, peak 14.2 GB.

The 11 Flipkart test pages (about 8,000 to 8,700 tokens) ran out of memory on the T4 and count as
no answer. The gold fixes of the v8 test samples verify at 96%.

Verified in the browser on the 110 test samples:

| model | all | wiki | amazonjobs | svelte | books | google, mdn, wiki2, sign-in | flipkart |
|---|---|---|---|---|---|---|---|
| 4B zero-shot | 0% | 0% | 0% | 0% | 0% | 0% | no answer |
| 4B fine-tuned | **13% (14/110)** | 50% | 31% | 8% | 7% | 0% | no answer |

Fine-tuned 4B by bug type: OVERFLOW 21% (7/34), OVERLAP 11% (4/37), CLIPPING 8% (3/39).

Notes:

- This is the first run where the screenshot is the only evidence of the bug. Without fine-tuning
  the model fixes nothing; after fine-tuning it fixes 13% on sites it never saw.
- It works best on OVERFLOW on text pages (wiki, amazonjobs), where `width: auto` on the right
  element fixes the page.
- About 70 of the 99 answers are `margin-top: 0px`, the most common training answer (the OVERLAP
  fix), whatever the bug type. When the model cannot see the bug it falls back to that answer.
- Finding small visual bugs in a screenshot is the limit of a 4-bit 4B model trained on about 280
  examples. The next step does not retrain: the browser tries several candidate fixes and keeps the
  one that works.