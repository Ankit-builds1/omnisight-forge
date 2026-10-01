# omnisight-forge

Trainable, measurable UI self-healing: a synthetic UI-bug factory, a fine-tuned
vision-language healer, an anti-cheat verifier, and the UI-HealBench benchmark.

Forge builds on OmniSight (a multimodal UI self-healing and RPA agent). Its goal is
to make the healing model trainable and measurable instead of relying on prompt
engineering alone.

## Status

Early development. Work is tracked in GitHub milestones:

- v0.1 Bug Factory (in progress)
- v0.2 Healer
- v0.3 Verifier
- v0.4 Dashboard / Flywheel

The bug types and their gold fixes are defined in [docs/BUG_TAXONOMY.md](docs/BUG_TAXONOMY.md).

## Setup

Requires Python 3.10 or newer (developed on 3.12).

```powershell
git clone https://github.com/Ankit-builds1/omnisight-forge.git
cd omnisight-forge
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
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