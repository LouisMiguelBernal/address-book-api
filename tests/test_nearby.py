"""Nearby search through the HTTP API.

The key test compares the API (bounding-box prefilter + haversine) with a
brute-force scan of every address. If the prefilter ever dropped a valid
point, the two result sets would differ.
"""

import random

import pytest
from fastapi.testclient import TestClient

from app.geo import MAX_DISTANCE_KM, haversine_km


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


@pytest.fixture
def seeded(client: TestClient, make_address) -> dict[int, tuple[float, float]]:
    """Store random addresses; return {id: (lat, lon)}."""
    stored = {}
    for lat, lon in _random_points(seed=42, count=200):
        body = client.post("/addresses", json=make_address(latitude=lat, longitude=lon)).json()
        stored[body["id"]] = (lat, lon)
    return stored


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
def test_nearby_matches_brute_force(
    client: TestClient, seeded: dict[int, tuple[float, float]], lat: float, lon: float, radius_km: float
) -> None:
    expected = {
        address_id
        for address_id, (a_lat, a_lon) in seeded.items()
        if haversine_km(lat, lon, a_lat, a_lon) <= radius_km
    }

    response = client.get("/addresses/nearby", params={"lat": lat, "lon": lon, "radius_km": radius_km})

    assert response.status_code == 200
    assert {a["id"] for a in response.json()} == expected


def test_whole_earth_radius_returns_everything(client: TestClient, seeded) -> None:
    response = client.get("/addresses/nearby", params={"lat": 0, "lon": 0, "radius_km": MAX_DISTANCE_KM})
    assert len(response.json()) == len(seeded)


def test_results_are_sorted_with_distances(client: TestClient, make_address) -> None:
    # Taguig search point; Makati ~3 km away, Quezon City ~12 km, Cebu ~570 km.
    for name, lat, lon in [
        ("Cebu", 10.3157, 123.8854),
        ("Quezon City", 14.6760, 121.0437),
        ("Makati", 14.5547, 121.0244),
    ]:
        client.post("/addresses", json=make_address(name=name, latitude=lat, longitude=lon))

    response = client.get("/addresses/nearby", params={"lat": 14.5507, "lon": 121.0494, "radius_km": 20})

    body = response.json()
    assert [a["name"] for a in body] == ["Makati", "Quezon City"]
    assert body[0]["distance_km"] < body[1]["distance_km"] <= 20


def test_zero_radius_returns_only_exact_location(client: TestClient, make_address) -> None:
    client.post("/addresses", json=make_address(name="Here", latitude=10, longitude=20))
    client.post("/addresses", json=make_address(name="Close", latitude=10.0001, longitude=20))

    response = client.get("/addresses/nearby", params={"lat": 10, "lon": 20, "radius_km": 0})

    assert [(a["name"], a["distance_km"]) for a in response.json()] == [("Here", 0.0)]


def test_no_matches_returns_empty_list(client: TestClient, make_address) -> None:
    client.post("/addresses", json=make_address(latitude=10, longitude=20))

    response = client.get("/addresses/nearby", params={"lat": -10, "lon": -20, "radius_km": 1})

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize(
    "params",
    [
        {"lat": 91, "lon": 0, "radius_km": 1},
        {"lat": 0, "lon": -181, "radius_km": 1},
        {"lat": 0, "lon": 0, "radius_km": -1},
        {"lat": 0, "lon": 0, "radius_km": MAX_DISTANCE_KM + 1},
        {"lat": 0, "lon": 0},  # radius missing
    ],
)
def test_invalid_search_parameters_are_rejected(client: TestClient, params: dict) -> None:
    assert client.get("/addresses/nearby", params=params).status_code == 422
