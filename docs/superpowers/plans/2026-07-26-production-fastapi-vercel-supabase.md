# IPO Stock Production FastAPI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `fastapi-ipo-stock` into a production-ready Vercel FastAPI foundation backed by its isolated Supabase project, Supabase Auth, and the `ipo_stock` custom schema.

**Architecture:** Vercel loads `app/main.py` as one ASGI Function. FastAPI validates configuration, emits structured request logs, exposes versioned routes, validates bearer tokens through Supabase Auth, and creates a request-scoped asynchronous Supabase client whose Data API queries target `ipo_stock` and retain the caller JWT for RLS.

**Tech Stack:** Python 3.12, FastAPI, Pydantic Settings, supabase-py async client, httpx, uv, pytest, Ruff, mypy, pip-audit, Vercel Functions, Supabase Auth/Data API/RLS.

## Global Constraints

- The Vercel runtime is Python 3.12 with Fluid Compute and a 30-second function timeout.
- `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` are required outside tests.
- `SUPABASE_SECRET_KEY` is optional and must only be used by an explicit administrator dependency.
- The database schema is the fixed string `ipo_stock`; it is not environment-overridable.
- User requests use request-scoped async clients; no shared mutable JWT state.
- Production docs are disabled by default.
- CORS is deny-by-default and accepts only configured origins.
- Error responses contain only `code`, `message`, and `request_id`.
- Do not add business tables, domain endpoints, Docker, in-memory sessions, or in-memory rate limiting.

## File Map

- Modify `pyproject.toml`: runtime/dev dependencies and tool configuration.
- Modify `uv.lock`: reproducible dependency graph.
- Modify `app/main.py`: application factory and Vercel ASGI export.
- Modify `README.md`: local, Supabase, Vercel, and verification runbook.
- Create `.python-version`, `.env.example`, `vercel.json`.
- Create `app/api/router.py`, `app/api/routes/health.py`, `app/api/routes/auth.py`.
- Create `app/core/config.py`, `app/core/errors.py`, `app/core/logging.py`.
- Create `app/integrations/supabase.py`.
- Create `app/middleware/request_context.py`.
- Create package `__init__.py` files for every new package.
- Replace `tests/test_main.py` with focused configuration, middleware, health, error, and auth tests.
- Create `tests/integration/test_supabase.py`.
- Create `.github/workflows/ci.yml`.
- Create `supabase/config.toml` and a CLI-generated initial migration.

---

### Task 1: Runtime, dependencies, and typed configuration

**Files:**
- Create: `.python-version`
- Create: `.env.example`
- Create: `app/core/__init__.py`
- Create: `app/core/config.py`
- Create: `tests/conftest.py`
- Create: `tests/test_config.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`

**Interfaces:**
- Produces: `Settings`, `get_settings() -> Settings`, and `clear_settings_cache() -> None`.
- Produces fixed values `app_name="IPO Stock API"` and `supabase_schema="ipo_stock"`.

- [ ] **Step 1: Write failing configuration tests**

```python
def test_schema_cannot_be_overridden(monkeypatch):
    monkeypatch.setenv("SUPABASE_SCHEMA", "public")
    settings = Settings(
        SUPABASE_URL="https://test.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="sb_publishable_test",
    )
    assert settings.supabase_schema == "ipo_stock"

def test_production_disables_docs_by_default():
    settings = Settings(
        APP_ENV="production",
        SUPABASE_URL="https://test.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="sb_publishable_test",
    )
    assert settings.docs_enabled is False
```

- [ ] **Step 2: Verify the tests fail**

Run: `uv run pytest tests/test_config.py -v`

Expected: FAIL because `app.core.config` does not exist.

- [ ] **Step 3: Add and lock exact dependency ranges**

Run:

```bash
uv add "pydantic-settings>=2,<3" "supabase>=2.31,<3" "httpx>=0.28,<1"
uv add --dev "ruff>=0.12,<1" "mypy>=1.17,<2" "pytest-asyncio>=1,<2" "pytest-cov>=6,<8" "pip-audit>=2.9,<3"
```

Set `.python-version` to `3.12`. Configure Ruff for `py312`, mypy `strict = true`,
pytest `testpaths = ["tests"]`, the `integration` marker, and coverage branch
measurement with `fail_under = 90`.

- [ ] **Step 4: Implement typed settings**

Implement `Settings(BaseSettings)` with `APP_ENV`, `LOG_LEVEL`, `ENABLE_DOCS`,
`CORS_ORIGINS`, `SUPABASE_URL`, publishable/secret keys, and a positive
`SUPABASE_TIMEOUT_SECONDS` defaulting to `5.0`. Use `SecretStr` for keys,
`SettingsConfigDict(env_file=".env", extra="ignore")`, a `ClassVar` for
`supabase_schema`, and an `lru_cache` around `get_settings`.

- [ ] **Step 5: Run the focused tests**

Run: `uv run pytest tests/test_config.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add .python-version .env.example pyproject.toml uv.lock app/core tests/conftest.py tests/test_config.py
git commit -m "운영 설정과 의존성 기반 추가"
```

### Task 2: Stable errors, JSON logging, and request context

**Files:**
- Create: `app/core/errors.py`
- Create: `app/core/logging.py`
- Create: `app/middleware/__init__.py`
- Create: `app/middleware/request_context.py`
- Create: `tests/test_errors.py`
- Create: `tests/test_middleware.py`

**Interfaces:**
- Produces: `ApiError(status_code: int, code: str, message: str)`.
- Produces: `register_exception_handlers(app: FastAPI) -> None`.
- Produces: `configure_logging(level: str) -> None`.
- Produces: `RequestContextMiddleware` and `resolve_request_id(value: str | None) -> str`.

- [ ] **Step 1: Write failing tests**

```python
def test_request_id_accepts_safe_value():
    assert resolve_request_id("req-123") == "req-123"

def test_request_id_replaces_unsafe_value():
    assert resolve_request_id("!" * 129) != "!" * 129

def test_api_error_envelope(client):
    response = client.get("/test-error")
    assert response.status_code == 409
    assert set(response.json()) == {"code", "message", "request_id"}
```

- [ ] **Step 2: Verify the tests fail**

Run: `uv run pytest tests/test_errors.py tests/test_middleware.py -v`

Expected: FAIL because error and middleware modules do not exist.

- [ ] **Step 3: Implement the minimal contracts**

Use a stdlib `logging.Formatter` that emits JSON with UTC timestamp, level,
logger, message, request ID, method, path, status, duration, and exception type.
Never serialize request headers. Accept request IDs only when they match
`[A-Za-z0-9._-]{1,128}`; otherwise generate `uuid4()`.

Register handlers for `ApiError`, `RequestValidationError`, `HTTPException`, and
unexpected `Exception`. Map them respectively to the requested code,
`validation_error`, `http_error`, and `internal_error`.

- [ ] **Step 4: Run focused tests and formatting**

Run:

```bash
uv run pytest tests/test_errors.py tests/test_middleware.py -v
uv run ruff format --check app tests
uv run ruff check app tests
```

Expected: all commands PASS.

- [ ] **Step 5: Commit**

```bash
git add app/core app/middleware tests/test_errors.py tests/test_middleware.py
git commit -m "표준 오류 응답과 요청 로깅 추가"
```

### Task 3: Application factory, versioned API, and health probes

**Files:**
- Create: `app/api/__init__.py`
- Create: `app/api/router.py`
- Create: `app/api/routes/__init__.py`
- Create: `app/api/routes/health.py`
- Create: `tests/test_health.py`
- Modify: `app/main.py`
- Delete: `tests/test_main.py`

**Interfaces:**
- Produces: `create_app(settings: Settings | None = None) -> FastAPI`.
- Produces: `probe_supabase(settings: Settings) -> None`.
- Routes: `GET /`, `GET /health/live`, and `GET /health/ready`.

- [ ] **Step 1: Write failing route tests**

```python
def test_liveness(client):
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_readiness_maps_upstream_failure(client, app):
    async def unavailable():
        raise ApiError(503, "dependency_unavailable", "Supabase is unavailable")
    app.dependency_overrides[probe_supabase] = unavailable
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["code"] == "dependency_unavailable"
```

- [ ] **Step 2: Verify the tests fail**

Run: `uv run pytest tests/test_health.py -v`

Expected: FAIL because the versioned router and probes do not exist.

- [ ] **Step 3: Implement routes and factory**

`probe_supabase` performs `GET {SUPABASE_URL}/auth/v1/health` with the
publishable `apikey`, no retries, and the configured timeout. It accepts only a
2xx response and converts `httpx.HTTPError` or non-2xx responses into the
sanitized `503` error. Configure CORS only when the allowlist is non-empty.
Set docs URLs to `None` when `settings.docs_enabled` is false.

- [ ] **Step 4: Run focused and regression tests**

Run: `uv run pytest tests/test_health.py tests/test_errors.py tests/test_middleware.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/main.py app/api tests/test_health.py tests/test_main.py
git commit -m "애플리케이션 팩토리와 상태 점검 추가"
```

### Task 4: Supabase Auth and request-scoped RLS client

**Files:**
- Create: `app/integrations/__init__.py`
- Create: `app/integrations/supabase.py`
- Create: `app/api/routes/auth.py`
- Create: `tests/test_auth.py`
- Modify: `app/api/router.py`

**Interfaces:**
- Produces: immutable `AuthContext(user: User, client: AsyncClient)`.
- Produces: yield dependency `get_auth_context(...) -> AsyncIterator[AuthContext]`.
- Produces: yield dependency `get_admin_client(...) -> AsyncIterator[AsyncClient]`.
- Route: `GET /api/v1/auth/me` returning only `id` and `email`.

- [ ] **Step 1: Write failing authentication tests**

```python
def test_me_requires_bearer_token(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"

def test_me_returns_verified_identity(client, app, auth_context):
    async def authenticated():
        yield auth_context
    app.dependency_overrides[get_auth_context] = authenticated
    response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer test"})
    assert response.status_code == 200
    assert response.json() == {"id": "user-123", "email": "user@example.com"}
```

- [ ] **Step 2: Verify the tests fail**

Run: `uv run pytest tests/test_auth.py -v`

Expected: FAIL because the Supabase integration does not exist.

- [ ] **Step 3: Implement request-scoped async clients**

Create a fresh `httpx.AsyncClient` per dependency invocation and pass it through
`AsyncClientOptions(schema="ipo_stock", persist_session=False,
auto_refresh_token=False, postgrest_client_timeout=5.0, httpx_client=...)`.
Call `await client.auth.get_user(token)`, then `client.postgrest.auth(token)`,
and yield `AuthContext`. Close the httpx client in `finally`.

Catch `AuthApiError` as `401 invalid_access_token`; map transport failures to
`503 authentication_service_unavailable`. The administrator dependency requires
`SUPABASE_SECRET_KEY`, creates a separate client, and never accepts a user JWT.

- [ ] **Step 4: Run tests and static analysis**

Run:

```bash
uv run pytest tests/test_auth.py -v
uv run mypy app
uv run ruff check app tests
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/integrations app/api/routes/auth.py app/api/router.py tests/test_auth.py
git commit -m "Supabase 인증과 RLS 클라이언트 추가"
```

### Task 5: Supabase schema migration and live integration checks

**Files:**
- Create via CLI: `supabase/config.toml`
- Create via CLI: initial `supabase/migrations/*_init_ipo_stock.sql`
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/test_supabase.py`

**Interfaces:**
- Produces schema `ipo_stock`.
- Grants `USAGE` to `anon`, `authenticated`, and `service_role`.
- Gives default table, sequence, and routine privileges only to `service_role`.

- [ ] **Step 1: Discover and initialize the Supabase CLI**

Run:

```bash
npx --yes supabase@latest --help
npx --yes supabase@latest init
npx --yes supabase@latest migration new init_ipo_stock
```

Expected: CLI help succeeds and prints the exact generated migration path.

- [ ] **Step 2: Write the migration SQL**

```sql
create schema if not exists ipo_stock;
grant usage on schema ipo_stock to anon, authenticated, service_role;
alter default privileges in schema ipo_stock
  grant all on tables to service_role;
alter default privileges in schema ipo_stock
  grant all on sequences to service_role;
alter default privileges in schema ipo_stock
  grant execute on routines to service_role;
```

- [ ] **Step 3: Add environment-gated integration tests**

Test the Auth health endpoint, a real `SUPABASE_TEST_ACCESS_TOKEN` through
`/api/v1/auth/me`, and Data API schema exposure using `Accept-Profile: ipo_stock`.
Skip with the explicit message `Supabase integration credentials are not set`
when any required test value is absent.

- [ ] **Step 4: Validate migration and tests**

Run:

```bash
npx --yes supabase@latest db lint --local
uv run pytest -m integration -v
```

Expected: lint passes when local Supabase is running; integration tests pass
with credentials or report explicit skips without them.

- [ ] **Step 5: Commit**

```bash
git add supabase tests/integration
git commit -m "ipo_stock 스키마 마이그레이션과 통합 검증 추가"
```

### Task 6: CI, Vercel configuration, operations documentation, and final proof

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `vercel.json`
- Modify: `.gitignore`
- Modify: `README.md`

**Interfaces:**
- CI gate: locked sync, formatting, lint, mypy, tests with 90% coverage, audit.
- Deployment entrypoint: `app/main.py`.

- [ ] **Step 1: Add CI and Vercel configuration**

Use `actions/checkout@v4` and `astral-sh/setup-uv@v6` with Python 3.12. Run:

```bash
uv sync --locked --dev
uv run ruff format --check app tests
uv run ruff check app tests
uv run mypy app
uv run pytest -m "not integration" --cov=app --cov-report=term-missing
uv run pip-audit
```

Set `fluid: true`, `maxDuration: 30`, and exclude `tests/**`, `docs/**`,
`supabase/**`, and `.venv/**` from the `app/main.py` function bundle.

- [ ] **Step 2: Write the complete runbook**

Document `uv sync`, local `.env`, `uv run uvicorn app.main:app --reload`,
`vercel dev`, Supabase custom-schema exposure, migration commands, required
Preview/Production environment variables, Auth curl examples, CI commands,
deployment, rollback, and log/request-ID troubleshooting.

- [ ] **Step 3: Run the full local gate**

Run:

```bash
uv lock --check
uv run ruff format --check app tests
uv run ruff check app tests
uv run mypy app
uv run pytest -m "not integration" --cov=app --cov-report=term-missing
uv run pip-audit
python -m json.tool vercel.json >/dev/null
git diff --check
```

Expected: every command exits `0`, coverage is at least 90%, and audit reports no
known vulnerable installed dependency.

- [ ] **Step 4: Build and probe Vercel**

Run:

```bash
npx --yes vercel@latest build
npx --yes vercel@latest deploy --prebuilt
```

Probe the returned preview URL at `/`, `/health/live`, `/health/ready`, and
`/api/v1/auth/me` with an invalid bearer token. Expected statuses are `200`,
`200`, `200`, and `401`. Do not promote when readiness is `503`.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml vercel.json .gitignore README.md
git commit -m "Vercel 배포와 CI 운영 기준 완성"
```
