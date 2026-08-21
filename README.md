# Python Base Template

A clean Python base project template with [uv](https://astral.sh/uv/), [pre-commit](https://pre-commit.com/), mypy, flake8, black, and pytest.

## Prerequisites

- Python 3.14
- [uv](https://astral.sh/uv/)
- [pre-commit](https://pre-commit.com/#install) (for development)

## Setup

```bash
uv sync
uv pip install -e .
pre-commit install  # optional, for development
```

## Project structure

```
src/            # Source module
tests/          # pytest test suite
pyproject.toml  # Project metadata, dependencies, and tool config
.pre-commit-config.yaml  # pre-commit hooks (flake8, mypy, black, pytest)
```

## Running tests

```bash
uv run pytest
```
