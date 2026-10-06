# omnisight-forge

Trainable, measurable UI self-healing: a synthetic UI-bug factory, a fine-tuned
vision-language healer, an anti-cheat verifier, and the UI-HealBench benchmark.

Forge builds on OmniSight (a multimodal UI self-healing and RPA agent). Its goal is
to make the healing model trainable and measurable instead of relying on prompt
engineering alone.

## Status

Early development. Work is tracked in GitHub milestones:

- v0.1 Bug Factory (done)
- v0.2 Healer (done)
- v0.3 Verifier
- v0.4 Dashboard / Flywheel

The bug types and their gold fixes are defined in [docs/BUG_TAXONOMY.md](docs/BUG_TAXONOMY.md).

## What the bug factory produces

The factory loads a real page, breaks one element with a verified CSS mutation
(overflow, overlap or clipping), and stores the clean screenshot, the broken
screenshot, the broken DOM and the exact CSS fix that reverses the bug. Every bug is
checked with geometry, lands only on elements visible in the screenshot, and can be
reproduced from a seed.

Example: a form label pushed up by 33px so it overlaps the label above it.

| Clean | Broken |
| --- | --- |
| ![clean page](docs/images/example_clean.png) | ![broken page](docs/images/example_broken.png) |

Build a dataset from the Bootstrap example pages (MIT licensed):

```powershell
.\.venv\Scripts\python.exe -m forge.build `
  --site album=https://getbootstrap.com/docs/5.3/examples/album/ `
  --site pricing=https://getbootstrap.com/docs/5.3/examples/pricing/ `
  --site sign-in=https://getbootstrap.com/docs/5.3/examples/sign-in/ `
  --site blog=https://getbootstrap.com/docs/5.3/examples/blog/ `
  --seeds 3
```

Output goes to `data/samples.jsonl` and `data/raw/`, both ignored by git. The first
full run kept 83 of 108 attempts after the quality filter.

## Results

Qwen3-VL-4B fine-tuned with LoRA, tested on held-out sites it never saw in training. Full
tables and notes are in [docs/RESULTS.md](docs/RESULTS.md).

**Finding in v0.3: the v0.2 healer was reading a leak, not the screenshot.** The bug factory
wrote each broken value as an inline style, visible in the HTML given to the model. With the bug
hidden in a stylesheet instead, the same model drops from 70% to 0% verified fixes and from 97%
to 0% right elements on the same pages. The v0.2 numbers below measure that shortcut; v0.3
trains and tests on hidden bugs only.

v0.2 result (with the leak): on 4 websites never seen in training, the healer repaired 69% of the
measurable injected layout bugs, checked in a real browser (sign-in 100%, Wikipedia 86%).

Every fix is applied to the live page and compared with the clean screenshot by
`python -m forge.verify`, because exact text matching proved misleading: it scored run 4 at 43%
while only 29% of its fixes actually repaired the page.

| run | what changed | verified fixed |
| --- | --- | --- |
| 4 | numbered elements instead of selectors | 29% (sign-in + wiki, 21) |
| 5 | trained on browser-verified fixes such as `height: auto` | 57% (sign-in + wiki, 21) |
| 6 | only verified answers, unfixable samples dropped | 76% (sign-in + wiki, 21) |
| 6 | same model on the harder v7 test (4 sites) | **69%** of 26 measurable samples |
| 7 | twice the training data (13 sites) | 65% of the same 26 samples |

Runs 1 to 3 used exact text matching only; see [docs/RESULTS.md](docs/RESULTS.md). A gold-fix
check showed that only 58% of the v7 test could be measured on live pages; with saved page
snapshots (v0.3) the verifier accepts 96% of gold fixes, with bugs inline or hidden.

## Setup

Requires Python 3.10 or newer (developed on 3.12).

```powershell
git clone https://github.com/Ankit-builds1/omnisight-forge.git
cd omnisight-forge
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

## Run tests and lint

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
```

## Workflow

`main` is protected. All changes go through `feat/<name>` branches and pull
requests, with conventional commit messages.

## License

Copyright (c) 2026 Ankit Dash. All Rights Reserved. See [LICENSE](LICENSE).