"""Create, read, update and delete through the HTTP API, including validation."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_create_returns_201_and_stored_address(client: TestClient, make_address) -> None:
    payload = make_address()
    response = client.post("/addresses", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert {k: body[k] for k in payload} == payload
    assert body["created_at"].endswith("Z")  # UTC


def test_get_returns_created_address(client: TestClient, make_address) -> None:
    created = client.post("/addresses", json=make_address()).json()

    response = client.get(f"/addresses/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created


def test_list_returns_all_addresses(client: TestClient, make_address) -> None:
    client.post("/addresses", json=make_address(name="A"))
    client.post("/addresses", json=make_address(name="B"))

    response = client.get("/addresses")

    assert response.status_code == 200
    assert [a["name"] for a in response.json()] == ["A", "B"]


def test_update_replaces_fields(client: TestClient, make_address) -> None:
    created = client.post("/addresses", json=make_address()).json()
    new_data = make_address(name="Home", city="Makati", latitude=14.5547, longitude=121.0244, state=None)

    response = client.put(f"/addresses/{created['id']}", json=new_data)

    assert response.status_code == 200
    body = response.json()
    assert {k: body[k] for k in new_data} == new_data
    assert client.get(f"/addresses/{created['id']}").json()["city"] == "Makati"


def test_delete_removes_address(client: TestClient, make_address) -> None:
    created = client.post("/addresses", json=make_address()).json()

    response = client.delete(f"/addresses/{created['id']}")

    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"/addresses/{created['id']}").status_code == 404


@pytest.mark.parametrize("method", ["get", "put", "delete"])
def test_missing_address_returns_404(client: TestClient, make_address, method: str) -> None:
    kwargs = {"json": make_address()} if method == "put" else {}
    response = client.request(method.upper(), "/addresses/999", **kwargs)

    assert response.status_code == 404
    assert response.json() == {"detail": "Address not found"}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("latitude", 90),
        ("latitude", -90),
        ("longitude", 180),
        ("longitude", -180),
        ("state", None),
        ("postal_code", None),
    ],
)
def test_boundary_values_are_accepted(client: TestClient, make_address, field: str, value) -> None:
    response = client.post("/addresses", json=make_address(**{field: value}))
    assert response.status_code == 201


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("latitude", 90.0001),
        ("latitude", -90.0001),
        ("longitude", 180.0001),
        ("longitude", -180.0001),
        ("latitude", "north"),
        ("name", ""),
        ("name", "   "),
        ("city", "x" * 101),
        ("postal_code", "1" * 21),
    ],
)
def test_invalid_values_are_rejected(client: TestClient, make_address, field: str, value) -> None:
    response = client.post("/addresses", json=make_address(**{field: value}))

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", field]


@pytest.mark.parametrize("field", ["name", "street", "city", "country", "latitude", "longitude"])
def test_missing_required_field_is_rejected(client: TestClient, make_address, field: str) -> None:
    payload = make_address()
    del payload[field]

    assert client.post("/addresses", json=payload).status_code == 422


def test_update_is_validated(client: TestClient, make_address) -> None:
    created = client.post("/addresses", json=make_address()).json()

    response = client.put(f"/addresses/{created['id']}", json=make_address(latitude=91))

    assert response.status_code == 422
    assert client.get(f"/addresses/{created['id']}").json()["latitude"] == created["latitude"]


def test_whitespace_is_trimmed(client: TestClient, make_address) -> None:
    response = client.post("/addresses", json=make_address(name="  Home  "))
    assert response.json()["name"] == "Home"


def test_data_persists_across_restart(settings: Settings, make_address) -> None:
    with TestClient(create_app(settings)) as first_run:
        created = first_run.post("/addresses", json=make_address()).json()

    with TestClient(create_app(settings)) as second_run:
        assert second_run.get(f"/addresses/{created['id']}").json() == created


def test_response_carries_request_id(client: TestClient) -> None:
    response = client.get("/addresses", headers={"X-Request-ID": "abc123"})
    assert response.headers["X-Request-ID"] == "abc123"
