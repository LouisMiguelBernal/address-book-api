from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

VALID_ADDRESS = {
    "name": "Eastvantage BGC Office",
    "street": "26th Street corner 5th Avenue",
    "city": "Taguig",
    "state": "Metro Manila",
    "postal_code": "1634",
    "country": "Philippines",
    "latitude": 14.5507,
    "longitude": 121.0494,
}


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings pointing at a fresh SQLite file per test."""
    return Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", log_level="DEBUG")


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    # The context manager runs the app's lifespan, which creates the tables.
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def make_address() -> Callable[..., dict]:
    """Build a valid address payload, overriding any fields."""

    def _make(**overrides: object) -> dict:
        return {**VALID_ADDRESS, **overrides}

    return _make
