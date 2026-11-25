"""Request IDs, logging and the handling of unexpected errors."""

import logging
import re

import pytest
from fastapi.testclient import TestClient

from tests.payloads import address

GENERATED_ID = re.compile(r"[0-9a-f]{12}")


def test_valid_client_request_id_is_reused(client: TestClient) -> None:
    response = client.get("/addresses", headers={"X-Request-ID": "trace-abc-123"})
    assert response.headers["X-Request-ID"] == "trace-abc-123"


@pytest.mark.parametrize("supplied", ["x" * 65, "has space", "semi;colon", ""])
def test_unsafe_client_request_id_is_replaced(client: TestClient, supplied: str) -> None:
    response = client.get("/addresses", headers={"X-Request-ID": supplied})
    assert GENERATED_ID.fullmatch(response.headers["X-Request-ID"])


def test_request_is_logged_with_its_request_id(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        client.post("/addresses", json=address(), headers={"X-Request-ID": "req-1"})

    lines = [r for r in caplog.records if getattr(r, "request_id", None) == "req-1"]
    messages = [r.getMessage() for r in lines]
    assert any(m.startswith("Created address id=") for m in messages)
    assert any(m.startswith("POST /addresses -> 201") for m in messages)


def test_validation_log_names_fields_but_not_values(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    secret = "742 Evergreen Terrace"
    with caplog.at_level(logging.WARNING):
        client.post("/addresses", json=address(street=secret, latitude=95))

    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("body.latitude: less_than_equal" in m for m in warnings)
    assert not any(secret in m or "95" in m for m in warnings)


def test_unhandled_error_returns_json_500_and_is_logged_once(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    def broken_endpoint() -> None:
        raise RuntimeError("simulated failure")

    client.app.add_api_route("/broken", broken_endpoint)

    with caplog.at_level(logging.INFO):
        response = client.get("/broken", headers={"X-Request-ID": "req-500"})

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert response.headers["X-Request-ID"] == "req-500"
    assert "simulated failure" not in response.text  # no internals leaked to the client

    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert errors[0].exc_info is not None
    assert any(r.getMessage().startswith("GET /broken -> 500") for r in caplog.records)
