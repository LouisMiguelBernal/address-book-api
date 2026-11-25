"""Application settings, read from environment variables.

Every setting has a working default, so the app runs with no configuration.
Override any of them with an ``ADDRESS_BOOK_`` prefixed environment variable,
e.g. ``ADDRESS_BOOK_LOG_LEVEL=DEBUG``.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ADDRESS_BOOK_")

    app_name: str = "Address Book API"
    database_url: str = "sqlite:///./address_book.db"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Return one shared Settings instance (environment is read once)."""
    return Settings()
