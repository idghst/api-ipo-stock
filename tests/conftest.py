import os

import pytest
from pydantic_settings import SettingsConfigDict

from app.core.config import Settings, clear_settings_cache

os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")

Settings.model_config = SettingsConfigDict(env_file=None, extra="ignore")


@pytest.fixture(autouse=True)
def clear_cached_settings() -> None:
    clear_settings_cache()
    yield
    clear_settings_cache()
