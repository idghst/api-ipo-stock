import pytest
from pydantic import ValidationError

from app.core.config import (
    Settings,
    clear_settings_cache,
    get_settings,
    resolve_app_env,
)
from app.core.url_validation import require_http_origin


@pytest.mark.parametrize(
    ("host", "url", "expected"),
    [
        ("testserver", "http://testserver/docs", "test"),
        ("api-test.vercel.app", "", "test"),
        ("", "https://ipo-test.example.com/health", "test"),
        ("dev.example.com", "", "development"),
        ("localhost:8000", "http://localhost:8000/", "development"),
        ("127.0.0.1:8000", "", "development"),
        ("api.example.com", "https://api.example.com/docs", "production"),
        ("fastapi-ipo-stock.vercel.app", "", "production"),
        ("test-dev.example.com", "", "test"),
    ],
)
def test_resolve_app_env_from_host_and_url(host: str, url: str, expected: str) -> None:
    assert resolve_app_env(host, url) == expected


def test_removed_env_fields_are_not_settings() -> None:
    assert "APP_ENV" not in Settings.model_fields
    assert "LOG_LEVEL" not in Settings.model_fields
    assert "ENABLE_DOCS" not in Settings.model_fields
    assert "CORS_ORIGINS" not in Settings.model_fields
    assert "DB_TIMEOUT_SECONDS" not in Settings.model_fields


def test_app_name_is_fixed() -> None:
    settings = Settings(
        DATABASE_URL="postgresql://app@db.test/ipostock",
    )

    assert settings.app_name == "IPO Stock API"


def test_timeout_is_fixed() -> None:
    settings = Settings(
        DATABASE_URL="postgresql://app@db.test/ipostock",
    )

    assert settings.DB_TIMEOUT_SECONDS == 5


def test_cors_origins_are_fixed() -> None:
    settings = Settings(
        DATABASE_URL="postgresql://app@db.test/ipostock",
    )

    assert settings.CORS_ORIGINS == ["http://localhost:3000"]
    assert "*" not in settings.CORS_ORIGINS


def test_cors_rejects_wildcard() -> None:
    with pytest.raises(ValueError):
        require_http_origin("*", allow_root_path=False)


@pytest.mark.parametrize(
    "cors_origin",
    [
        "null",
        "ftp://localhost:3000",
        "http://user:password@localhost:3000",
        "http://localhost:3000/api",
        "http://localhost:3000/",
        "http://localhost:3000?preview=true",
        "http://localhost:3000#section",
        "http:///missing-host",
        "http://localhost\\evil.com",
        "http://localhost:",
        "http://.",
        " http://localhost:3000",
        "http://localhost:3000 ",
        "http://localhost:3000\n",
        "http://localhost:3000\x00",
        "",
    ],
)
def test_cors_rejects_non_origin_values(cors_origin: str) -> None:
    with pytest.raises(ValueError):
        require_http_origin(cors_origin, allow_root_path=False)


@pytest.mark.parametrize(
    "cors_origin",
    [
        "http://localhost:3000",
        "http://127.0.0.1:8000",
        "http://[::1]:8000",
        "https://api.example.com:8443",
    ],
)
def test_cors_allows_concrete_origins(cors_origin: str) -> None:
    assert require_http_origin(cors_origin, allow_root_path=False) == cors_origin


def test_administrator_credentials_are_optional_at_settings_time() -> None:
    settings = Settings(
        DATABASE_URL="postgresql://app@db.test/ipostock",
        IPO_STOCK_API_KEY="   ",
    )

    assert settings.IPO_STOCK_API_KEY is None


@pytest.mark.parametrize(
    "database_url",
    ["", "   ", "https://db.test/ipostock", "mysql://app@db.test/ipostock"],
)
def test_database_url_must_be_postgres(database_url: str) -> None:
    with pytest.raises(ValidationError):
        Settings(DATABASE_URL=database_url)


def test_database_url_is_secret() -> None:
    settings = Settings(DATABASE_URL="postgres://app:pw@db.test/ipostock")

    assert "pw" not in repr(settings)


def test_settings_cache_can_be_cleared(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_settings_cache()
    monkeypatch.setenv("DATABASE_URL", "postgresql://app@db.test/ipostock")
    first = get_settings()
    monkeypatch.setenv("DATABASE_URL", "postgresql://app@other.test/ipostock")
    assert get_settings() is first

    clear_settings_cache()
    assert (
        get_settings().DATABASE_URL.get_secret_value()
        == "postgresql://app@other.test/ipostock"
    )
