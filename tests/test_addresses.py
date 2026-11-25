"""Create, read, update and delete through the HTTP API, including validation."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.config import Settings
from app.main import create_app
from app.models import Address
from app.schemas import MAX_DB_INT
from tests.payloads import address


def test_create_returns_201_and_stored_address(client: TestClient) -> None:
    payload = address()
    response = client.post("/addresses", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert {k: body[k] for k in payload} == payload
    assert body["created_at"].endswith("Z")  # UTC


def test_get_returns_created_address(client: TestClient) -> None:
    created = client.post("/addresses", json=address()).json()

    response = client.get(f"/addresses/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created


def test_list_returns_addresses_in_id_order_with_paging(client: TestClient) -> None:
    for name in ["A", "B", "C"]:
        client.post("/addresses", json=address(name=name))

    assert [a["name"] for a in client.get("/addresses").json()] == ["A", "B", "C"]
    page = client.get("/addresses", params={"offset": 1, "limit": 1}).json()
    assert [a["name"] for a in page] == ["B"]


def test_update_replaces_fields_and_bumps_updated_at(client: TestClient) -> None:
    created = client.post("/addresses", json=address()).json()
    # Backdate updated_at so the bump is visible regardless of clock resolution.
    with client.app.state.session_factory() as db:
        db.execute(update(Address).values(updated_at=datetime(2000, 1, 1)))
        db.commit()
    new_data = address(name="Home", city="Makati", latitude=14.5547, longitude=121.0244, state=None)

    response = client.put(f"/addresses/{created['id']}", json=new_data)

    assert response.status_code == 200
    body = response.json()
    assert {k: body[k] for k in new_data} == new_data
    assert body["created_at"] == created["created_at"]
    assert body["updated_at"] >= created["created_at"]
    assert client.get(f"/addresses/{created['id']}").json()["city"] == "Makati"


def test_delete_removes_address(client: TestClient) -> None:
    created = client.post("/addresses", json=address()).json()

    response = client.delete(f"/addresses/{created['id']}")

    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"/addresses/{created['id']}").status_code == 404


@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE"])
def test_missing_address_returns_404(client: TestClient, method: str) -> None:
    kwargs = {"json": address()} if method == "PUT" else {}
    response = client.request(method, "/addresses/999", **kwargs)

    assert response.status_code == 404
    assert response.json() == {"detail": "Address not found"}


@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE"])
@pytest.mark.parametrize("address_id", [0, -1, MAX_DB_INT + 1, "abc"])
def test_out_of_range_id_returns_422_not_500(client: TestClient, method: str, address_id) -> None:
    kwargs = {"json": address()} if method == "PUT" else {}
    response = client.request(method, f"/addresses/{address_id}", **kwargs)

    assert response.status_code == 422


def test_largest_valid_id_returns_404(client: TestClient) -> None:
    assert client.get(f"/addresses/{MAX_DB_INT}").status_code == 404


@pytest.mark.parametrize(
    "params", [{"offset": -1}, {"offset": MAX_DB_INT + 1}, {"limit": 0}, {"limit": 1001}]
)
def test_invalid_paging_returns_422(client: TestClient, params: dict) -> None:
    assert client.get("/addresses", params=params).status_code == 422


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("latitude", 90),
        ("latitude", -90),
        ("longitude", 180),
        ("longitude", -180),
        ("latitude", 10),  # whole numbers are valid JSON numbers
        ("state", None),
        ("postal_code", None),
        ("name", "Café Ñiño 東京"),  # any non-control Unicode text
    ],
)
def test_valid_edge_values_are_accepted(client: TestClient, field: str, value) -> None:
    response = client.post("/addresses", json=address(**{field: value}))

    assert response.status_code == 201
    assert response.json()[field] == value


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("latitude", 90.0001),
        ("latitude", -90.0001),
        ("longitude", 180.0001),
        ("longitude", -180.0001),
        ("latitude", True),  # would otherwise be coerced to 1.0
        ("latitude", "10.5"),  # strings are not numbers
        ("latitude", None),
        ("name", ""),
        ("name", "   "),
        ("name", "line\nbreak"),
        ("name", "nul\x00byte"),
        ("street", "tab\there"),
        ("city", "x" * 101),
        ("postal_code", "1" * 21),
    ],
)
def test_invalid_values_are_rejected(client: TestClient, field: str, value) -> None:
    response = client.post("/addresses", json=address(**{field: value}))

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", field]


@pytest.mark.parametrize("field", ["name", "street", "city", "country", "latitude", "longitude"])
def test_missing_required_field_is_rejected(client: TestClient, field: str) -> None:
    payload = address()
    del payload[field]

    assert client.post("/addresses", json=payload).status_code == 422


@pytest.mark.parametrize("extra", [{"id": 999}, {"created_at": "2000-01-01T00:00:00Z"}, {"lattitude": 1}])
def test_unknown_fields_are_rejected(client: TestClient, extra: dict) -> None:
    response = client.post("/addresses", json={**address(), **extra})

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "extra_forbidden"


def test_malformed_json_is_rejected(client: TestClient) -> None:
    response = client.post("/addresses", content=b"{not json", headers={"Content-Type": "application/json"})
    assert response.status_code == 422


def test_update_is_validated_and_leaves_data_unchanged(client: TestClient) -> None:
    created = client.post("/addresses", json=address()).json()

    response = client.put(f"/addresses/{created['id']}", json=address(latitude=91))

    assert response.status_code == 422
    assert client.get(f"/addresses/{created['id']}").json() == created


def test_whitespace_is_trimmed(client: TestClient) -> None:
    response = client.post("/addresses", json=address(name="  Home  "))
    assert response.json()["name"] == "Home"


def test_data_persists_across_restart(settings: Settings) -> None:
    with TestClient(create_app(settings)) as first_run:
        created = first_run.post("/addresses", json=address()).json()

    with TestClient(create_app(settings)) as second_run:
        assert second_run.get(f"/addresses/{created['id']}").json() == created
