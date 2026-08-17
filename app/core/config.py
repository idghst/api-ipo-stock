from functools import lru_cache
from typing import ClassVar, Literal
from urllib.parse import urlsplit

from pydantic import AnyHttpUrl, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.url_validation import require_http_origin

type AppEnv = Literal["development", "test", "production"]


def resolve_app_env(host: str = "", url: str = "") -> AppEnv:
    """Host/URL hostname에 test → test, dev|localhost|127.0.0.1 → development, 그 외 production."""

    parts = [host]
    if url:
        parsed = urlsplit(url)
        if parsed.hostname:
            parts.append(parsed.hostname)
        if parsed.netloc:
            parts.append(parsed.netloc)
    haystack = " ".join(parts).lower()
    if "test" in haystack:
        return "test"
    if "dev" in haystack or "localhost" in haystack or "127.0.0.1" in haystack:
        return "development"
    return "production"


class Settings(BaseSettings):
    """Validated runtime configuration loaded from the environment."""

    model_config = SettingsConfigDict(env_file=(".env", ".env.local"), extra="ignore")

    SUPABASE_URL: AnyHttpUrl
    SUPABASE_PUBLISHABLE_KEY: SecretStr
    SUPABASE_SECRET_KEY: SecretStr | None = None
    IPO_STOCK_API_KEY: SecretStr | None = None

    app_name: ClassVar[str] = "IPO Stock API"
    supabase_schema: ClassVar[str] = "ipo_stock"
    CORS_ORIGINS: ClassVar[list[str]] = [
        require_http_origin("http://localhost:3000", allow_root_path=False)
    ]
    SUPABASE_TIMEOUT_SECONDS: ClassVar[float] = 5.0

    @field_validator("SUPABASE_URL", mode="before")
    @classmethod
    def require_supabase_origin(cls, value: object) -> object:
        return require_http_origin(value, allow_root_path=True)

    @field_validator("SUPABASE_PUBLISHABLE_KEY", mode="before")
    @classmethod
    def require_nonblank_publishable_key(cls, value: object) -> object:
        raw_value = value.get_secret_value() if isinstance(value, SecretStr) else value
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise ValueError("SUPABASE_PUBLISHABLE_KEY must not be blank")
        return value

    @field_validator("SUPABASE_SECRET_KEY", mode="before")
    @classmethod
    def normalize_blank_secret_key(cls, value: object) -> object:
        raw_value = value.get_secret_value() if isinstance(value, SecretStr) else value
        if isinstance(raw_value, str) and not raw_value.strip():
            return None
        if isinstance(raw_value, str) and raw_value.startswith("sb_publishable_"):
            raise ValueError("SUPABASE_SECRET_KEY must not be a publishable key")
        return value

    @field_validator("IPO_STOCK_API_KEY", mode="before")
    @classmethod
    def normalize_blank_ipo_stock_api_key(cls, value: object) -> object:
        raw_value = value.get_secret_value() if isinstance(value, SecretStr) else value
        if isinstance(raw_value, str) and not raw_value.strip():
            return None
        return value

    @model_validator(mode="after")
    def reject_matching_publishable_and_secret_keys(self) -> "Settings":
        secret_key = self.SUPABASE_SECRET_KEY
        if secret_key is not None and secret_key.get_secret_value() == (
            self.SUPABASE_PUBLISHABLE_KEY.get_secret_value()
        ):
            raise ValueError(
                "SUPABASE_SECRET_KEY must not equal SUPABASE_PUBLISHABLE_KEY"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # Loaded from the environment.


def clear_settings_cache() -> None:
    get_settings.cache_clear()
