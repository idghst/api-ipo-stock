# fastapi-ipo-stock

맥미니 Postgres의 `ipostock` DB(스키마 `ipostock`)에 직접 붙는 읽기 전용 FastAPI
서비스입니다. IPO 목록/상세는 서버 전용 `X-Admin-Key`로 보호하고 `ipostock.v_offerings`만
SELECT합니다. Supabase(PostgREST, Auth)는 쓰지 않습니다.

## Local development

Python 3.12와 [uv](https://docs.astral.sh/uv/)가 필요합니다.

```bash
uv sync --locked --dev
```

`.env.example`을 `.env.local`로 복사한 뒤 `DATABASE_URL`과 키를 넣으세요. 실제 값은 절대
커밋하지 마세요.

```bash
uv run uvicorn app.main:app --reload
```

- API: <http://127.0.0.1:8000>
- Docs (localhost / Host에 `dev` 또는 `test`): <http://127.0.0.1:8000/docs>
- Liveness: <http://127.0.0.1:8000/health/live>
- Readiness: <http://127.0.0.1:8000/health/ready>

Vercel 런타임을 로컬에서 확인할 때는 Vercel에 연결된 프로젝트의 환경 변수를
가져온 뒤 실행합니다.

```bash
vercel dev
```

## Database setup

데이터와 스키마는 `ipostock` 공모주 파이프라인(`데이터베이스` 저장소의 `ipostock-api`)이
관리합니다. 이 API는 앱 전용 읽기 전용 롤 `ipostock_app`으로만 접속합니다.

1. 롤과 권한을 만듭니다(슈퍼유저, 한 번만). `v_offerings`가 `security_invoker` 뷰라서
   뷰가 읽는 표 7개에 SELECT와 RLS 읽기 정책을 함께 줍니다. 쓰기 권한은 없고
   `default_transaction_read_only = on`입니다.

   ```bash
   APP_DB_PASSWORD=$(openssl rand -hex 24)
   docker exec -i -u postgres postgres psql -d ipostock -v ON_ERROR_STOP=1 \
     -v app_password="$APP_DB_PASSWORD" < sql/ipostock_app.sql
   ```

2. API가 도는 네트워크에서 접속을 허용합니다. `pg_hba.conf`에
   `host ipostock ipostock_app <앱 서브넷> scram-sha-256` 줄을 게이트웨이 거부 줄 아래에 넣고
   `select pg_reload_conf()`를 실행합니다(`데이터베이스/README.md`의 "접근 정책").
3. `DATABASE_URL=postgresql://ipostock_app:<password>@<host>:5432/ipostock`을 설정합니다.

### Supabase에서 옮길 때

- 기존 `.env.local`의 `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY`는
  더 읽지 않습니다. `DATABASE_URL`을 추가한 뒤 확인이 끝나면 지웁니다. Vercel 환경 변수도 같습니다.
- Supabase를 지우기 전에는 대시보드에서 그 키들을 폐기(rotate)합니다.
- `/api/v1/auth/me`는 Supabase Auth 토큰 검증에 의존했습니다. 토큰이 없으면 `401`, 있으면
  자체 인증을 정할 때까지 `503 authentication_service_unavailable`을 반환합니다.

## IPO stock API

모든 IPO 요청은 아래 헤더가 필요합니다. `IPO_STOCK_API_KEY`가 없으면 운영 host는
`/health/live` 외 모든 요청을 `503`으로 거부하고, development에서는 목록/상세 요청만 `503`으로
거부됩니다. 키가 틀리거나 없으면 동일한 `401` 오류를 반환합니다.

```http
X-Admin-Key: <IPO_STOCK_API_KEY>
```

공개 경로는 GET만 있습니다. `ipostock.v_offerings` SELECT만 사용합니다.

| Method | Path | Response |
| --- | --- | --- |
| `GET` | `/api/v1/ipo-stocks?limit=100&offset=0` | `{ "items": [...], "count": 42 }` |
| `GET` | `/api/v1/ipo-stocks/{id}` | IPO 1건 |

목록의 `limit`은 `1`~`200`이며 기본값은 `100`, `offset`은 `0` 이상입니다. response는
camelCase JSON입니다. 기존 필드(`companyName`, `ticker`, `market`, `offerPrice`,
`subscriptionStart`, `subscriptionEnd`, `listingDate`, `status`, `memo`)는 유지하고,
뷰 컬럼은 값이 있을 때만 additive로 내려갑니다. `status`는 `scheduled`,
`subscription_open`, `subscription_closed`, `listed`, `cancelled`로 정규화하고
원문은 `statusRaw`입니다. 없는 ID는 `404`입니다.

```bash
curl -i \
  -H "X-Admin-Key: $IPO_STOCK_API_KEY" \
  http://127.0.0.1:8000/api/v1/ipo-stocks
```

## CI

GitHub Actions는 잠금 파일, 포맷, lint, 타입, 비통합 테스트(coverage 90% 이상),
의존성 취약점을 검사합니다. 로컬에서도 같은 게이트를 실행합니다.

```bash
uv lock --check
uv run ruff format --check app tests
uv run ruff check app tests
uv run mypy app
uv run pytest -m "not integration" --cov=app --cov-report=term-missing
uv run pip-audit
```

통합 테스트는 `ipostock` 스키마가 있는 테스트 DB에 `ipostock_app`으로 붙어 실행합니다.
운영 DB 대신 임시 컨테이너에 스키마만 넣어 씁니다.

```bash
DATABASE_TEST_URL=postgresql://ipostock_app:<password>@127.0.0.1:<port>/ipostock \
  uv run pytest -m integration
```

## Vercel deployment

`vercel.json`은 FastAPI framework preset과 `app/main.py` 함수 진입점을 고정하고,
Fluid Compute와 `maxDuration: 30`을 설정합니다. `.vercelignore`는 root allowlist로
런타임에 필요한 `app/**/*.py`, `pyproject.toml`, `uv.lock`, `.python-version`,
`vercel.json`만 업로드합니다. 그러므로 `tests/`, `docs/`, `sql/`, `.venv/`는
함수 번들에 포함되지 않습니다.

Vercel Dashboard에서 **같은 `fastapi-ipo-stock` 프로젝트의** Preview와 Production
환경을 분리해 아래 변수를 모두 설정합니다.

환경은 요청 Host/URL hostname으로만 가릅니다. `test`면 test, `dev` 또는
localhost/127.0.0.1이면 development, 그 외는 production입니다. production host에서는
`/docs` `/redoc` `/openapi.json`을 비공개하고, `IPO_STOCK_API_KEY`가 필요합니다. 로그 레벨은 INFO로 고정입니다.

| Variable | Preview | Production | Notes |
| --- | --- | --- | --- |
| `DATABASE_URL` | 필수 | 필수 | `ipostock_app` 접속 URL. API에서 Postgres에 닿아야 함 |
| `IPO_STOCK_API_KEY` | 필수 | 필수 | 긴 난수; 관리페이지 서버만 `X-Admin-Key`로 전달 |

배포 전에 CLI 상태와 build 인자를 확인하고, Vercel 프로젝트
`fastapi-ipo-stock`을 명시적으로 연결한 뒤 Preview 설정만 가져옵니다. Vercel link는
프로젝트에 연결하는 작업이며, 이 **한 프로젝트** 안에 Preview와 Production 환경 변수
세트를 각각 둡니다. `.vercel/`은 gitignore 대상이므로 연결 정보와 원격 환경 값은
커밋되지 않습니다. 이 runbook은 `--prod`, `vercel promote`, `--prebuilt`를 사용하지
않습니다.

```bash
vercel whoami
vercel build --help
vercel project list --scope idghst
# fastapi-ipo-stock이 없다면 한 번만 명시적으로 생성
vercel project add fastapi-ipo-stock --scope idghst
# 새 프로젝트 또는 기존 Other preset을 FastAPI로 맞춤
vercel project update fastapi-ipo-stock --framework fastapi --scope idghst
vercel link --yes --team idghst --project fastapi-ipo-stock
vercel pull --environment=preview
# 로컬 호환성 검증 전용. 이 결과물을 배포하지 않습니다.
vercel build --target=preview
# source를 직접 업로드하는 Preview 배포만 사용합니다.
vercel deploy --target=preview
```

로컬 build는 호환성 검증 전용입니다. Vercel CLI의 local build는 source upload 단계의
`.vercelignore` 필터를 적용하지 않으므로, 생성된 `.vercel/output`은 배포하지 말고
검증 후 삭제합니다. deploy는 `.vercelignore` allowlist가 적용되는 direct source
deployment를 사용합니다. 현재 작업 디렉터리에서 `--prebuilt`는 사용하지 않습니다.
배포 후 probe 전에 반환된 URL/ID를
`vercel inspect <preview-url-or-deployment-id> --format=json`으로 확인하고 Target이
Preview인지 검증합니다. Preview 배포가 `/health/ready`에서 `200`을 반환하기 전에는
`vercel promote` 또는 `--prod`를 실행하지 않습니다.

반환된 Preview URL에서 다음 상태를 확인합니다. `/health/ready`가 `503`이면
promotion하지 말고 `DATABASE_URL`, `pg_hba.conf`, 네트워크 경로를 점검합니다.

```bash
curl -i https://preview.example.vercel.app/
curl -i https://preview.example.vercel.app/health/live
curl -i https://preview.example.vercel.app/health/ready
```

기대 상태는 각각 `200`, `200`, `200`입니다.

## Rollback and incident response

장애 배포는 Vercel Dashboard의 이전 정상 deployment로 rollback하거나, 확인한
deployment URL/ID를 사용해 실행합니다.

```bash
vercel rollback <deployment-url-or-id>
```

장애 조사 순서:

1. 응답의 `X-Request-ID`와 배포 URL을 확보합니다.
2. Vercel Functions 로그에서 같은 request ID를 검색합니다.
3. `500`이면 배포 환경 변수와 import 오류를, `503`이면 Postgres 상태·네트워크·timeout을
   확인합니다.
4. IPO 목록/상세의 `401`이면 관리페이지 서버의 `X-Admin-Key`만 확인합니다. 키 원문은 로그에
   남기지 않습니다.
5. `403` 또는 빈 결과면 `ipostock_app`의 SELECT 권한과 `ipostock_app_read` RLS 정책을
   확인합니다(`sql/ipostock_app.sql`). 다른 롤에 권한을 넓히지 않습니다.

키나 JWT 원문은 issue, 로그, 커밋에 넣지 않습니다.
