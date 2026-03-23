# Contributing

This project is a small Python codebase with a CLI-oriented workflow.

## Development Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Environment variables:

- Copy `.env.example` to `.env` and set required keys.
- `run_cli_main.py` loads `.env`; `main.py` expects env vars to already be present.

## Running Locally

```bash
python main.py
```

Rich console wrapper:

```bash
python run_cli_main.py
```

## Testing

There is no dedicated test suite in this repository at the moment.

Quick non-destructive checks you can run:

```bash
python -m compileall -q .
```

If you add tests, include how to run them in your PR description and consider updating this file.

## Linting / Formatting

There is no pinned linter/formatter configuration in-repo (no `pyproject.toml`).

Guidelines:

- Keep changes focused and consistent with nearby code.
- Prefer explicit, typed data structures (`TypedDict` / Pydantic models) where the pipeline crosses boundaries.
- Avoid introducing new runtime dependencies unless necessary.

## Branching

- Create feature branches off `main`: `feature/<short-description>` or `fix/<short-description>`
- Keep PRs small and focused.

## Pull Request Checklist

- [ ] The change is scoped and explained (what + why)
- [ ] `python -m compileall -q .` succeeds
- [ ] Any new env vars are documented in `README.md` and/or `docs/OPERATIONS.md`
- [ ] Any behavior changes to the pipeline are reflected in `docs/ARCHITECTURE.md`
