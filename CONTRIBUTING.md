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

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting,
enforced at two levels:

- **Pre-commit hook** — lightweight slop-catcher that blocks glaring issues
  (dead code, unused imports, commented-out code, whitespace junk, syntax errors)
- **CI** — comprehensive lint + format check on every push and PR to `main`

### One-time setup

```bash
pip install -r requirements-dev.txt
pre-commit install
```

After this, every `git commit` will automatically catch:
- Unused imports and variables (dead code)
- Undefined names
- Commented-out code left behind
- Trailing whitespace and missing newlines
- Syntax errors (`compileall`)

The full rule set (import ordering, code style, format) is enforced by CI.

### Manual checks

```bash
# Quick lint (same rules as pre-commit)
ruff check --select "F,W,ERA,PIE790" .

# Full lint (same rules as CI)
ruff check .

# Format
ruff format .
```

Configuration lives in `pyproject.toml` under `[tool.ruff]`.

### Guidelines

- Keep changes focused and consistent with nearby code.
- Prefer explicit, typed data structures (`TypedDict` / Pydantic models) where the pipeline crosses boundaries.
- Avoid introducing new runtime dependencies unless necessary.

## Branching

- Create feature branches off `main`: `feature/<short-description>` or `fix/<short-description>`
- Keep PRs small and focused.

## Pull Request Checklist

- [ ] The change is scoped and explained (what + why)
- [ ] `pre-commit run --all-files` passes (or `ruff check . && ruff format --check .`)
- [ ] Any new env vars are documented in `README.md` and/or `docs/OPERATIONS.md`
- [ ] Any behavior changes to the pipeline are reflected in `docs/ARCHITECTURE.md`
