"""Nearby search through the HTTP API.

The key test compares the API (bounding-box prefilter + haversine) with a
brute-force scan of every address. If the prefilter ever dropped a valid
point, the two result sets would differ.
"""

import random
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.geo import MAX_DISTANCE_KM, haversine_km
from app.main import create_app
from tests.conftest import settings_for
from tests.payloads import address

NEARBY = "/addresses/nearby"


def _random_points(seed: int, count: int) -> list[tuple[float, float]]:
    """Uniform points plus clusters near the 180th meridian and both poles."""
    rng = random.Random(seed)
    points = []
    for _ in range(count):
        kind = rng.random()
        if kind < 0.5:
            points.append((rng.uniform(-90, 90), rng.uniform(-180, 180)))
        elif kind < 0.75:
            points.append((rng.uniform(-10, 10), rng.choice([-1, 1]) * rng.uniform(178, 180)))
        else:
            points.append((rng.choice([-1, 1]) * rng.uniform(85, 90), rng.uniform(-180, 180)))
    return points


@pytest.fixture(scope="module")
def seeded(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[tuple[TestClient, dict[int, tuple[float, float]]]]:
    """One database with 300 random addresses, shared by the read-only tests below."""
    db_file: Path = tmp_path_factory.mktemp("nearby") / "test.db"
    with TestClient(create_app(settings_for(db_file))) as client:
        stored = {}
        for lat, lon in _random_points(seed=42, count=300):
            body = client.post("/addresses", json=address(latitude=lat, longitude=lon)).json()
            stored[body["id"]] = (lat, lon)
        yield client, stored


def _ids(response) -> list[int]:
    return [match["address"]["id"] for match in response.json()]


@pytest.mark.parametrize(
    ("lat", "lon", "radius_km"),
    [
        (0, 179.9, 300),  # crosses the 180th meridian eastwards
        (0, -179.9, 300),  # crosses the 180th meridian westwards
        (88, 0, 500),  # circle contains the North Pole
        (-90, 0, 1000),  # centred on the South Pole
        (14.55, 121.05, 2000),  # ordinary case
        (45, 90, 8000),  # very large radius
        (0, 0, MAX_DISTANCE_KM),  # whole Earth
    ],
)
def test_nearby_matches_brute_force(seeded, lat: float, lon: float, radius_km: float) -> None:
    client, stored = seeded
    distances = {aid: haversine_km(lat, lon, *point) for aid, point in stored.items()}
    expected = sorted((d, aid) for aid, d in distances.items() if d <= radius_km)

    response = client.get(NEARBY, params={"lat": lat, "lon": lon, "radius_km": radius_km, "limit": 1000})

    assert response.status_code == 200
    assert _ids(response) == [aid for _, aid in expected]  # same set, same order


def test_limit_returns_the_nearest_matches(seeded) -> None:
    client, stored = seeded
    params = {"lat": 0, "lon": 0, "radius_km": MAX_DISTANCE_KM}

    everything = _ids(client.get(NEARBY, params={**params, "limit": 1000}))
    first_ten = _ids(client.get(NEARBY, params={**params, "limit": 10}))
    default = _ids(client.get(NEARBY, params=params))

    assert len(everything) == len(stored)
    assert first_ten == everything[:10]
    assert default == everything[:100]


def test_response_shape_and_rounding(client: TestClient) -> None:
    created = client.post(
        "/addresses", json=address(name="Makati", latitude=14.5547, longitude=121.0244)
    ).json()

    response = client.get(NEARBY, params={"lat": 14.5507, "lon": 121.0494, "radius_km": 20})

    [match] = response.json()
    assert match["address"] == created
    assert match["distance_km"] == round(haversine_km(14.5507, 121.0494, 14.5547, 121.0244), 3)


def test_results_are_sorted_nearest_first(client: TestClient) -> None:
    # Search from Taguig: Makati ~3 km, Quezon City ~14 km, Cebu ~570 km (outside 20 km).
    for name, lat, lon in [
        ("Cebu", 10.3157, 123.8854),
        ("Quezon City", 14.6760, 121.0437),
        ("Makati", 14.5547, 121.0244),
    ]:
        client.post("/addresses", json=address(name=name, latitude=lat, longitude=lon))

    body = client.get(NEARBY, params={"lat": 14.5507, "lon": 121.0494, "radius_km": 20}).json()

    assert [m["address"]["name"] for m in body] == ["Makati", "Quezon City"]
    assert body[0]["distance_km"] < body[1]["distance_km"] <= 20


def test_equal_distances_are_ordered_by_id(client: TestClient) -> None:
    ids = [client.post("/addresses", json=address(latitude=10, longitude=20)).json()["id"] for _ in range(5)]

    response = client.get(NEARBY, params={"lat": 10, "lon": 20, "radius_km": 1})

    assert _ids(response) == ids


def test_radius_is_inclusive(client: TestClient) -> None:
    client.post("/addresses", json=address(name="Edge", latitude=14.6, longitude=121.1))
    exact = haversine_km(14.5, 121.0, 14.6, 121.1)

    response = client.get(NEARBY, params={"lat": 14.5, "lon": 121.0, "radius_km": repr(exact)})

    assert [m["address"]["name"] for m in response.json()] == ["Edge"]


def test_zero_radius_returns_only_exact_location(client: TestClient) -> None:
    client.post("/addresses", json=address(name="Here", latitude=10, longitude=20))
    client.post("/addresses", json=address(name="Close", latitude=10.0001, longitude=20))

    response = client.get(NEARBY, params={"lat": 10, "lon": 20, "radius_km": 0})

    assert [(m["address"]["name"], m["distance_km"]) for m in response.json()] == [("Here", 0.0)]


def test_no_matches_returns_empty_list(client: TestClient) -> None:
    client.post("/addresses", json=address(latitude=10, longitude=20))

    response = client.get(NEARBY, params={"lat": -10, "lon": -20, "radius_km": 1})

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize(
    "params",
    [
        {"lat": 91, "lon": 0, "radius_km": 1},
        {"lat": 0, "lon": -181, "radius_km": 1},
        {"lat": "nan", "lon": 0, "radius_km": 1},
        {"lat": 0, "lon": "inf", "radius_km": 1},
        {"lat": 0, "lon": 0, "radius_km": -1},
        {"lat": 0, "lon": 0, "radius_km": "nan"},
        {"lat": 0, "lon": 0, "radius_km": MAX_DISTANCE_KM + 1},
        {"lat": 0, "lon": 0, "radius_km": 1, "limit": 0},
        {"lat": 0, "lon": 0, "radius_km": 1, "limit": 1001},
        {"lat": 0, "lon": 0},  # radius missing
    ],
)
def test_invalid_search_parameters_are_rejected(client: TestClient, params: dict) -> None:
    assert client.get(NEARBY, params=params).status_code == 422
