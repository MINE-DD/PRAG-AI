# Contributing to PRAG-AI

Thank you for considering contributing! This document covers how to get started.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) for dependency management
- Docker Desktop (for running Qdrant locally)
- Git

## Development Setup

```bash
git clone https://github.com/MINE-DD/PRAG-AI.git
cd PRAG-AI
uv sync --extra dev
pre-commit install   # runs ruff on every commit automatically
```

## Running Tests

```bash
pytest                          # all tests
pytest tests/unit/              # unit tests only
pytest tests/integration/       # integration tests only
pytest --cov=backend            # with coverage report
```

## Linting

```bash
uv run ruff check .             # check for issues
uv run ruff check . --fix       # auto-fix safe issues
uv run ruff format .            # auto-format
```

## Submitting a Pull Request

1. Fork the repository and create a branch from `main`:
   ```bash
   git checkout -b feat/my-feature
   ```
2. Make your changes and add tests if applicable.
3. Run `pytest && uv run ruff check .` — both must pass.
4. Commit using a conventional prefix:
   - `feat:` new feature
   - `fix:` bug fix
   - `docs:` documentation only
   - `test:` tests only
   - `chore:` tooling, dependencies
5. Open a pull request against `main`.

## Reporting Bugs

Open a GitHub issue with:
- Steps to reproduce
- Expected vs actual behaviour
- Output of `docker compose logs backend` if relevant

## Proposing Features

Open a GitHub issue labelled `enhancement` describing the feature and the use case.
