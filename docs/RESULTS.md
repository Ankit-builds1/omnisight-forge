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