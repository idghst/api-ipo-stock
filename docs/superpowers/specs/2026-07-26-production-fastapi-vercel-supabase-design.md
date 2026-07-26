# Production FastAPI on Vercel with Supabase

## Scope

Upgrade `fastapi-ipo-stock` from a minimal FastAPI scaffold to a production-ready
service foundation. The service deploys to Vercel, uses its own Supabase
project, uses Supabase Auth, and accesses tables in the `ipo_stock` schema
through the Supabase Data API.

Business tables, business endpoints, frontend authentication UI, and
application-specific authorization rules are outside this foundation.

## Decisions

- Runtime: Python 3.12 on Vercel Functions with Fluid Compute.
- Package management: `uv` with a committed lockfile.
- Data access: Supabase Data API through the asynchronous Python client.
- Authentication: Supabase Auth bearer access tokens.
- Authorization: Postgres grants and Row Level Security.
- Schema: `ipo_stock`.
- Logging: structured JSON using the Python standard library.
- Rate limiting: Vercel Firewall, not process memory.
- Production API documentation: disabled by default.

## Architecture

```text
Client Bearer JWT
  -> FastAPI authentication dependency
  -> Supabase Auth token validation
  -> request-scoped asynchronous Supabase client
  -> ipo_stock schema through the Data API
  -> Postgres grants and RLS
```

`app/main.py` remains the Vercel-discoverable ASGI entrypoint. The application
is split into API routes, core configuration and errors, middleware, and the
Supabase integration. A user-scoped client is created per request so one
request cannot mutate authentication state used by another concurrent request.
An administrator client is exposed only through a separate explicit dependency.

## Components

- `app/main.py`: application factory and exported ASGI application.
- `app/api/router.py`: versioned API router.
- `app/api/routes/health.py`: liveness and Supabase readiness endpoints.
- `app/api/routes/auth.py`: protected `/api/v1/auth/me` verification endpoint.
- `app/core/config.py`: typed environment configuration and fixed schema name.
- `app/core/errors.py`: stable error codes and exception handlers.
- `app/core/logging.py`: JSON log formatter and log initialization.
- `app/middleware/request_context.py`: request ID, timing, and access logging.
- `app/integrations/supabase.py`: request-scoped user and isolated admin clients.
- `supabase/migrations/`: schema, grants, and future RLS migrations.

## Configuration

`SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` are required outside tests.
`SUPABASE_SECRET_KEY` is optional and only enables explicit administrator
dependencies. `CORS_ORIGINS`, `LOG_LEVEL`, `APP_ENV`, and `ENABLE_DOCS` control
runtime behavior. Secrets are supplied through Vercel environment variables and
never committed. The application fails early when production configuration is
invalid.

## Security

- Only an explicit CORS allowlist is accepted.
- Missing, malformed, expired, or invalid bearer tokens return `401`.
- Supabase permission and RLS failures return `403` without leaking internals.
- `Authorization`, tokens, API keys, and secret values are never logged.
- Every business table must enable RLS and define operation-specific policies.
- Ownership columns used by RLS must be indexed.
- `UPDATE` policies require `SELECT`, `USING`, and `WITH CHECK`.
- Authorization data belongs in `app_metadata`, never user-editable metadata.
- The custom schema must be explicitly exposed in Supabase Data API settings.
- Migrations grant only required schema, table, routine, and sequence privileges.
- The secret key and administrator client never enter normal user request paths.

## Errors and Observability

API errors use a stable envelope containing `code`, `message`, and `request_id`.
Validation, authentication, authorization, not-found, upstream, and unexpected
errors map to distinct codes and appropriate HTTP status values. Clients may
provide `X-Request-ID`; otherwise the service creates one. The same ID is
returned in the response and included in structured access and error logs.

Logs include method, path, status, duration, environment, and request ID.
Vercel runtime logs and observability consume stdout JSON. No in-process metrics
server or persistent local state is introduced.

## Health

- `GET /health/live` has no external dependency.
- `GET /health/ready` calls Supabase Auth `/auth/v1/health` with a short timeout.
- `GET /api/v1/auth/me` validates a real Supabase access token.

Readiness returns a sanitized `503` when Supabase is unavailable. It never
returns project URLs, keys, or upstream response bodies.

## Testing and CI

Unit tests cover configuration, public routes, request IDs, error envelopes,
authentication success and failure, CORS, and readiness mapping. Supabase calls
are replaced at the dependency boundary, not patched inside route logic.

Environment-gated integration tests use a real Supabase project to validate
Auth, custom-schema access, and RLS isolation. They skip clearly when required
test credentials are absent.

GitHub Actions runs on Python 3.12:

1. `uv sync --locked --dev`
2. `ruff format --check`
3. `ruff check`
4. `mypy`
5. `pytest` with coverage
6. `pip-audit`

## Vercel Deployment

Vercel uses `app/main.py`, Fluid Compute, and a 30-second function timeout.
Tests, fixtures, local Supabase data, and design documents are excluded from the
function bundle. Preview and Production environments receive separate Supabase
credentials. Git integration creates preview deployments; promotion to
production happens only after CI and the live health probes pass.

## Database Migrations

The initial migration creates `ipo_stock`, applies required role grants, and
configures default privileges. It creates no business tables. Every later table
migration must include RLS enablement, explicit policies, and indexes supporting
policy predicates. Migrations are generated with the Supabase CLI and reviewed
before being applied to each isolated project.

## Success Criteria

- Local lint, type checking, unit tests, coverage, and dependency audit pass.
- Vercel builds and serves the FastAPI application.
- Liveness and Supabase readiness probes return expected status codes.
- A real Supabase token succeeds at `/api/v1/auth/me`; an invalid token returns
  the documented `401` envelope.
- A production Data API probe reaches the `ipo_stock` schema with expected RLS
  behavior once a business table and policy exist.
- No secret appears in source, logs, responses, or the Vercel bundle.
