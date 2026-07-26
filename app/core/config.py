from functools import lru_cache
from typing import Annotated, ClassVar, Literal

from pydantic import AnyHttpUrl, Field, SecretStr, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated runtime configuration loaded from the environment."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_ENV: Literal["development", "test", "production"] = "development"
    LOG_LEVEL: str = "INFO"
    ENABLE_DOCS: bool | None = None
    CORS_ORIGINS: list[str] = []
    SUPABASE_URL: AnyHttpUrl
    SUPABASE_PUBLISHABLE_KEY: SecretStr
    SUPABASE_SECRET_KEY: SecretStr | None = None
    SUPABASE_TIMEOUT_SECONDS: Annotated[float, Field(gt=0)] = 5.0

    app_name: ClassVar[str] = "IPO Stock API"
    supabase_schema: ClassVar[str] = "ipo_stock"

    @field_validator("CORS_ORIGINS")
    @classmethod
    def require_concrete_cors_origins(cls, values: list[str]) -> list[str]:
        if "*" in values:
            raise ValueError("CORS_ORIGINS must not include '*'")
        return values

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
        return value

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
