from functools import lru_cache
from typing import Annotated, ClassVar, Literal

from pydantic import (
    AnyHttpUrl,
    Field,
    SecretStr,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.url_validation import require_http_origin


class Settings(BaseSettings):
    """Validated runtime configuration loaded from the environment."""

    model_config = SettingsConfigDict(env_file=(".env", ".env.local"), extra="ignore")

    APP_ENV: Literal["development", "test", "production"] = "development"
    LOG_LEVEL: str = "INFO"
    ENABLE_DOCS: bool | None = None
    CORS_ORIGINS: list[str] = []
    SUPABASE_URL: AnyHttpUrl
    SUPABASE_PUBLISHABLE_KEY: SecretStr
    SUPABASE_SECRET_KEY: SecretStr | None = None
    SUPABASE_TIMEOUT_SECONDS: Annotated[float, Field(gt=0)] = 5.0
    IPO_STOCK_API_KEY: SecretStr | None = None

    app_name: ClassVar[str] = "IPO Stock API"
    supabase_schema: ClassVar[str] = "ipo-stock"

    @field_validator("CORS_ORIGINS")
    @classmethod
    def require_concrete_cors_origins(cls, values: list[str]) -> list[str]:
        return [require_http_origin(value, allow_root_path=False) for value in values]

    @field_validator("SUPABASE_URL", mode="before")
    @classmethod
    def require_supabase_origin(cls, value: object) -> object:
        return require_http_origin(value, allow_root_path=True)

    @field_validator("SUPABASE_URL")
    @classmethod
    def require_https_supabase_in_production(
        cls, value: AnyHttpUrl, info: ValidationInfo
    ) -> AnyHttpUrl:
        if info.data.get("APP_ENV") == "production" and value.scheme != "https":
            raise ValueError("SUPABASE_URL must use HTTPS in production")
        return value

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
    def require_server_only_administrator_credentials_in_production(self) -> "Settings":
        secret_key = self.SUPABASE_SECRET_KEY
        if secret_key is not None and secret_key.get_secret_value() == (
            self.SUPABASE_PUBLISHABLE_KEY.get_secret_value()
        ):
            raise ValueError(
                "SUPABASE_SECRET_KEY must not equal SUPABASE_PUBLISHABLE_KEY"
            )
        if self.APP_ENV == "production" and (
            secret_key is None or self.IPO_STOCK_API_KEY is None
        ):
            raise ValueError(
                "SUPABASE_SECRET_KEY and IPO_STOCK_API_KEY are required in production"
            )
        return self

    @property
    def docs_enabled(self) -> bool:
        return (
            self.ENABLE_DOCS
            if self.ENABLE_DOCS is not None
            else self.APP_ENV != "production"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # Loaded from the environment.


def clear_settings_cache() -> None:
    get_settings.cache_clear()
