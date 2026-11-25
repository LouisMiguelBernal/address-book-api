from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def settings_for(db_file: Path) -> Settings:
    return Settings(database_url=f"sqlite:///{db_file}", log_level="DEBUG")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings pointing at a fresh SQLite file per test."""
    return settings_for(tmp_path / "test.db")


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    # The context manager runs the app's lifespan, which creates the tables.
    with TestClient(create_app(settings)) as test_client:
        yield test_client
