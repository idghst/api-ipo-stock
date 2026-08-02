from functools import lru_cache
from ipaddress import ip_address
from typing import Annotated, ClassVar, Literal
from urllib.parse import urlsplit

from pydantic import (
    AnyHttpUrl,
    Field,
    SecretStr,
    TypeAdapter,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

_http_url_adapter = TypeAdapter(AnyHttpUrl)


def _has_valid_host(host: str | None) -> bool:
    if not host:
        return False
    if host.startswith("[") and host.endswith("]"):
        try:
            ip_address(host[1:-1])
        except ValueError:
            return False
        return True

    try:
        ip_address(host)
    except ValueError:
        pass
    else:
        return True

    host = host.removesuffix(".")
    if not host or len(host) > 253:
        return False
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return False
    return all(
        label
        and len(label) <= 63
        and not label.startswith("-")
        and not label.endswith("-")
        and all(
            character.isascii() and (character.isalnum() or character == "-")
            for character in label
        )
        for label in ascii_host.split(".")
    )


def _require_http_origin(value: object, *, allow_root_path: bool) -> str:
    if isinstance(value, AnyHttpUrl):
        value = str(value)
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\\" in value
        or any(character.isspace() for character in value)
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError("must be a concrete HTTP(S) origin")

    try:
        raw_url = urlsplit(value)
        raw_port = raw_url.port
    except ValueError as error:
        raise ValueError("must use a valid authority") from error
    if not raw_url.netloc or raw_url.netloc.endswith(":"):
        raise ValueError("must use a valid authority")
    if raw_port is not None and not 0 < raw_port <= 65535:
        raise ValueError("must use a valid port")
    if raw_url.path not in ({"", "/"} if allow_root_path else {""}):
        raise ValueError("must be a concrete HTTP(S) origin")

    try:
        parsed_url = _http_url_adapter.validate_python(value)
    except ValidationError as error:
        raise ValueError("must be a concrete HTTP(S) origin") from error
    if (
        parsed_url.scheme not in {"http", "https"}
        or not _has_valid_host(parsed_url.host)
        or parsed_url.username is not None
        or parsed_url.password is not None
        or parsed_url.path != "/"
        or parsed_url.query is not None
        or parsed_url.fragment is not None
    ):
        raise ValueError("must be a concrete HTTP(S) origin")
    return value


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
    ADMIN_API_KEY: SecretStr | None = None

    app_name: ClassVar[str] = "IPO Stock API"
    supabase_schema: ClassVar[str] = "ipo_stock"

    @field_validator("CORS_ORIGINS")
    @classmethod
    def require_concrete_cors_origins(cls, values: list[str]) -> list[str]:
        return [_require_http_origin(value, allow_root_path=False) for value in values]

    @field_validator("SUPABASE_URL", mode="before")
    @classmethod
    def require_supabase_origin(cls, value: object) -> object:
        return _require_http_origin(value, allow_root_path=True)

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

    @field_validator("ADMIN_API_KEY", mode="before")
    @classmethod
    def normalize_blank_admin_api_key(cls, value: object) -> object:
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
            secret_key is None or self.ADMIN_API_KEY is None
        ):
            raise ValueError(
                "SUPABASE_SECRET_KEY and ADMIN_API_KEY are required in production"
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
