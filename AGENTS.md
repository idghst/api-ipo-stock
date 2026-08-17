# AGENTS.md

## Cursor Cloud specific instructions

This repo is a single FastAPI service (`fastapi-ipo-stock`) backed by Supabase and
deployed to Vercel. There is no frontend. Standard commands are already documented in
`README.md` (Local development, CI, Supabase, Vercel sections) — prefer those and only
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
  placeholder `SUPABASE_URL` / `SUPABASE_PUBLISHABLE_KEY`, so it needs **no** external
  services. Coverage must stay >= 90%.
- `uv run pip-audit` currently reports pre-existing transitive advisories
  (`cryptography`, `h2`) and exits non-zero. This is inherited from `uv.lock`, not from
  environment setup; do not "fix" it unless the task is a dependency bump.
- Integration tests (`uv run pytest -m integration`) are skipped unless
  `SUPABASE_TEST_URL`, `SUPABASE_TEST_PUBLISHABLE_KEY`, and
  `SUPABASE_TEST_ACCESS_TOKEN` are all set (they hit a real Supabase project).

### Running the app

- Run with `uv run uvicorn app.main:app --reload` (README documents this).
- Non-obvious gotcha: settings are validated at import time via `get_settings()`, so the
  process **will not start** unless `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` are set.
  Provide them through a gitignored `.env.local` (loaded automatically). A minimal boot
  needs only those two; `SUPABASE_SECRET_KEY` + `IPO_STOCK_API_KEY` are additionally
  required for IPO list/detail GET (in development, missing admin creds only make the
  `/api/v1/ipo-stocks` routes return `503`; production refuses to start).
- IPO list/detail GET requires the `X-Admin-Key: <IPO_STOCK_API_KEY>` header.
  Request/response bodies are camelCase JSON.
- `/health/live` needs nothing; `/health/ready` and the GET/auth routes make live calls
  to the configured Supabase, so they need a reachable Supabase (see below).

### Optional: local Supabase for full end-to-end (health/ready + real GET)

Only needed when you want the Supabase-backed endpoints to actually work locally. This is
a per-session step (heavy), intentionally kept out of the startup update script.

1. Docker is not preinstalled and there is no systemd. Install Docker CE, then start the
   daemon manually in the background: `sudo dockerd`. The daemon config
   (`/etc/docker/daemon.json`) must use `"storage-driver": "fuse-overlayfs"` and, because
   this is Docker 29, `"features": { "containerd-snapshotter": false }` (fuse-overlayfs is
   otherwise ignored). Set `iptables`/`ip6tables` alternatives to the `-legacy` variants.
   For non-root access run `sudo chmod 666 /var/run/docker.sock`.
2. Install the Supabase CLI, then from the repo root run `supabase start` (it pulls
   several images the first time and applies `supabase/migrations/`). Grab the local
   `PUBLISHABLE_KEY` / `SECRET_KEY` from `supabase status`.
3. Point `.env.local` at it: `SUPABASE_URL=http://127.0.0.1:54321`,
   `SUPABASE_PUBLISHABLE_KEY=<PUBLISHABLE_KEY>`, `SUPABASE_SECRET_KEY=<SECRET_KEY>`,
   `ADMIN_API_KEY=<random>`. The Data API default schema for this service is `ipo_stock`
   (already exposed in `supabase/config.toml`); never call it from a browser with the
   anon key — only the server uses the secret key.
