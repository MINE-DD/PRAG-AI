# AGENTS.md

## Tech Stack
- Use docker compose 
- Use Docling to process PDFs
- Use Qdrant for storing embeddings
- Use Ollama for running local LLMs

## Setup commands
- Run tests: `uv run --extra dev python -m pytest`
- Type check: `uv run mypy backend/`
- Lint: `uv run ruff check`
- Format: `uv run ruff format`

## Pre-commit hooks
ruff and mypy run automatically on every `git commit` via pre-commit.
To install the hooks after a fresh clone: `uv run pre-commit install`
To run all checks manually without committing: `uv run pre-commit run --all-files`

## Code style
- Python 3.12
- Use `uv` to manage environments and dependencies
- Before committing, ensure `uv run mypy backend/`, `uv run ruff check`, and `uv run ruff format --check` all pass


