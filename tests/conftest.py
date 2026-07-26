import pytest

from app.core.config import clear_settings_cache


@pytest.fixture(autouse=True)
def clear_cached_settings() -> None:
    clear_settings_cache()
    yield
    clear_settings_cache()
