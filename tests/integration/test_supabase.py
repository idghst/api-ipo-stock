import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

pytestmark = pytest.mark.integration

_CREDENTIALS_SKIP_MESSAGE = "Supabase integration credentials are not set"
_CREDENTIAL_ENV_NAMES = (
    "SUPABASE_TEST_URL",
    "SUPABASE_TEST_PUBLISHABLE_KEY",
    "SUPABASE_TEST_ACCESS_TOKEN",
)


@dataclass(frozen=True)
class IntegrationCredentials:
    url: str
    publishable_key: str
    access_token: str


def load_integration_credentials() -> IntegrationCredentials:
    values = {name: os.getenv(name, "").strip() for name in _CREDENTIAL_ENV_NAMES}
    if not all(values.values()):
        pytest.skip(_CREDENTIALS_SKIP_MESSAGE)
    return IntegrationCredentials(
        url=values["SUPABASE_TEST_URL"].rstrip("/"),
        publishable_key=values["SUPABASE_TEST_PUBLISHABLE_KEY"],
        access_token=values["SUPABASE_TEST_ACCESS_TOKEN"],
    )


@pytest.fixture(scope="session")
def credentials() -> IntegrationCredentials:
    return load_integration_credentials()


def test_initial_migration_creates_only_ipo_stock_schema_contract() -> None:
    migration = next(
        (Path(__file__).parents[2] / "supabase" / "migrations").glob(
            "*_init_ipo_stock.sql"
        )
    )

    assert (
        migration.read_text()
        == """create schema if not exists ipo_stock;
grant usage on schema ipo_stock to anon, authenticated, service_role;
alter default privileges in schema ipo_stock
  grant all on tables to service_role;
alter default privileges in schema ipo_stock
  grant all on sequences to service_role;
alter default privileges in schema ipo_stock
  grant execute on routines to service_role;
"""
    )


def test_local_data_api_exposes_ipo_stock_schema() -> None:
    config = Path(__file__).parents[2] / "supabase" / "config.toml"

    assert 'schemas = ["public", "graphql_public", "ipo_stock"]' in config.read_text()


def test_local_supabase_project_id_is_unique_to_ipo_stock_service() -> None:
    config = Path(__file__).parents[2] / "supabase" / "config.toml"

    with config.open("rb") as config_file:
        assert tomllib.load(config_file)["project_id"] == "fastapi-ipo-stock"


@pytest.mark.parametrize("missing_name", _CREDENTIAL_ENV_NAMES)
@pytest.mark.parametrize("missing_value", [None, "", " \t "])
def test_integration_credential_gate_rejects_unset_empty_and_whitespace_values(
    monkeypatch: pytest.MonkeyPatch, missing_name: str, missing_value: str | None
) -> None:
    for name in _CREDENTIAL_ENV_NAMES:
        monkeypatch.setenv(name, "value")
    if missing_value is None:
        monkeypatch.delenv(missing_name)
    else:
        monkeypatch.setenv(missing_name, missing_value)

    def unexpected_network(*_: object, **__: object) -> None:
        pytest.fail("credential gate attempted a live network call")

    monkeypatch.setattr(httpx, "get", unexpected_network)

    with pytest.raises(pytest.skip.Exception, match=_CREDENTIALS_SKIP_MESSAGE):
        load_integration_credentials()


def test_auth_health_endpoint(credentials: IntegrationCredentials) -> None:
    response = httpx.get(
        f"{credentials.url}/auth/v1/health",
        headers={"apikey": credentials.publishable_key},
        timeout=5.0,
    )

    assert response.is_success, response.text


def test_verified_access_token_reaches_auth_me(
    credentials: IntegrationCredentials,
) -> None:
    settings = Settings(
        SUPABASE_URL=credentials.url,
        SUPABASE_PUBLISHABLE_KEY=credentials.publishable_key,
    )
    with TestClient(create_app(settings)) as client:
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {credentials.access_token}"},
        )

    assert response.status_code == 200, response.text
    assert response.json()["id"]


def test_data_api_accepts_ipo_stock_schema_profile(
    credentials: IntegrationCredentials,
) -> None:
    response = httpx.get(
        f"{credentials.url}/rest/v1/",
        headers={
            "apikey": credentials.publishable_key,
            "Authorization": f"Bearer {credentials.access_token}",
            "Accept-Profile": "ipo_stock",
        },
        timeout=5.0,
    )

    assert response.is_success, response.text
