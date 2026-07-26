import pytest
from pydantic import ValidationError

from app.core.config import Settings, clear_settings_cache, get_settings


def test_schema_cannot_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_SCHEMA", "public")

    settings = Settings(
        SUPABASE_URL="https://test.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="sb_publishable_test",
    )

    assert settings.supabase_schema == "ipo_stock"


def test_production_disables_docs_by_default() -> None:
    settings = Settings(
        APP_ENV="production",
        SUPABASE_URL="https://test.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="sb_publishable_test",
    )

    assert settings.docs_enabled is False


def test_app_name_is_fixed() -> None:
    settings = Settings(
        SUPABASE_URL="https://test.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="sb_publishable_test",
    )

    assert settings.app_name == "IPO Stock API"


def test_docs_can_be_explicitly_enabled_in_production() -> None:
    settings = Settings(
        APP_ENV="production",
        ENABLE_DOCS=True,
        SUPABASE_URL="https://test.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="sb_publishable_test",
    )

    assert settings.docs_enabled is True


def test_timeout_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Settings(
            SUPABASE_TIMEOUT_SECONDS=0,
            SUPABASE_URL="https://test.supabase.co",
            SUPABASE_PUBLISHABLE_KEY="sb_publishable_test",
        )


def test_production_rejects_http_supabase_url() -> None:
    with pytest.raises(ValidationError):
        Settings(
            APP_ENV="production",
            SUPABASE_URL="http://localhost:54321",
            SUPABASE_PUBLISHABLE_KEY="sb_publishable_test",
        )


def test_local_allows_http_supabase_url() -> None:
    settings = Settings(
        SUPABASE_URL="http://localhost:54321",
        SUPABASE_PUBLISHABLE_KEY="sb_publishable_test",
    )

    assert str(settings.SUPABASE_URL) == "http://localhost:54321/"


@pytest.mark.parametrize("supabase_url", ["not-a-url", "ftp://test.supabase.co"])
def test_supabase_url_must_be_http_url(supabase_url: str) -> None:
    with pytest.raises(ValidationError):
        Settings(
            SUPABASE_URL=supabase_url,
            SUPABASE_PUBLISHABLE_KEY="sb_publishable_test",
        )


def test_cors_defaults_to_no_origins() -> None:
    settings = Settings(
        SUPABASE_URL="https://test.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="sb_publishable_test",
    )

    assert settings.CORS_ORIGINS == []


def test_cors_rejects_wildcard() -> None:
    with pytest.raises(ValidationError):
        Settings(
            CORS_ORIGINS=["*"],
            SUPABASE_URL="https://test.supabase.co",
            SUPABASE_PUBLISHABLE_KEY="sb_publishable_test",
        )


def test_publishable_key_must_not_be_blank() -> None:
    with pytest.raises(ValidationError):
        Settings(
            SUPABASE_URL="https://test.supabase.co",
            SUPABASE_PUBLISHABLE_KEY="   ",
        )


def test_blank_optional_secret_becomes_none() -> None:
    settings = Settings(
        SUPABASE_URL="https://test.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="sb_publishable_test",
        SUPABASE_SECRET_KEY="   ",
    )

    assert settings.SUPABASE_SECRET_KEY is None


def test_settings_cache_can_be_cleared(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_settings_cache()
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    first = get_settings()
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    assert get_settings() is first

    clear_settings_cache()
    assert get_settings().LOG_LEVEL == "DEBUG"
