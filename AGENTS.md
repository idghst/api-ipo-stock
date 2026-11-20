# AGENTS.md

## Cursor Cloud specific instructions

This repo is a single read-only FastAPI service (`fastapi-ipo-stock`) that reads the
`ipostock` Postgres DB directly with psycopg and is deployed to Vercel. There is no frontend. Standard commands are already documented in
`README.md` (Local development, Database setup, CI, Vercel sections) — prefer those and only
the non-obvious cloud notes below.

### Toolchain / dependencies

- The package manager is [uv](https://docs.astral.sh/uv/). The startup update script
  ensures `uv` is present (installed to `/usr/local/bin`, so it is on `PATH` for every
  shell) and runs `uv sync --locked --dev`. You normally do not need to install anything
  by hand.
- Python is pinned to 3.12 (`.python-version`); the system `python3` is already 3.12.

### Lint / type / test / run

- Quality gates (same as `.github/workflows/ci.yml`), run from the repo root:
  - `uv run ruff format --check app tests`
  - `uv run ruff check app tests`
  - `uv run mypy app`
  - `uv run pytest -m "not integration" --cov=app --cov-report=term-missing`
- The non-integration suite is fully self-contained: `tests/conftest.py` injects
  a placeholder `DATABASE_URL`, so it needs **no** external services. Coverage must stay >= 90%.
- `uv run pip-audit` currently reports pre-existing transitive advisories
  (`cryptography`, `h2`) and exits non-zero. This is inherited from `uv.lock`, not from
  environment setup; do not "fix" it unless the task is a dependency bump.
- Integration tests (`uv run pytest -m integration`) are skipped unless
  `DATABASE_TEST_URL` is set. Point it at a throwaway Postgres loaded with the `ipostock`
  schema and `sql/ipostock_app.sql`, never at the production DB.

### Running the app

- Run with `uv run uvicorn app.main:app --reload` (README documents this).
- Non-obvious gotcha: settings are validated at import time via `get_settings()`, so the
  process **will not start** unless `DATABASE_URL` (a `postgresql://` URL) is set. Provide
  it through a gitignored `.env.local` (loaded automatically). `IPO_STOCK_API_KEY` is
  additionally required for IPO list/detail GET (localhost/`dev`/`test` hosts 503 those
  routes when it is missing; other hosts also 503 unless `/health/live`). Env is not
  `APP_ENV`: Host/URL hostname containing `test` → test, `dev` or localhost/127.0.0.1 →
  development, else production. Log level is always INFO. Docs are only on
  development/test hosts.
- IPO list/detail GET requires the `X-Admin-Key: <IPO_STOCK_API_KEY>` header.
  Request/response bodies are camelCase JSON.
- `/health/live` needs nothing; `/health/ready` and the IPO GET routes connect to
  `DATABASE_URL`. `/api/v1/auth/me` returns 401 without a bearer token and 503 with one
  (Supabase Auth was removed; no replacement auth is decided yet).
