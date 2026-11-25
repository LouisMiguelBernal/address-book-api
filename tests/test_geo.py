"""Distance and bounding-box maths."""

import math

import pytest

from app.geo import EARTH_RADIUS_KM, MAX_DISTANCE_KM, bounding_box, haversine_km

ONE_DEGREE_KM = math.pi * EARTH_RADIUS_KM / 180  # 111.195 km along a great circle


@pytest.mark.parametrize(
    ("a", "b", "expected_km"),
    [
        # Exact properties of the sphere.
        ((0, 0), (0, 0), 0.0),
        ((0, 0), (1, 0), ONE_DEGREE_KM),  # one degree along a meridian
        ((0, 0), (0, 1), ONE_DEGREE_KM),  # one degree along the equator
        ((0, 179.5), (0, -179.5), ONE_DEGREE_KM),  # across the 180th meridian
        ((0, 0), (0, 90), MAX_DISTANCE_KM / 2),  # quarter of the equator
        ((90, 0), (-90, 0), MAX_DISTANCE_KM),  # pole to pole
        ((89.9, 0), (89.9, 180), 0.2 * ONE_DEGREE_KM),  # over the North Pole
    ],
)
def test_haversine_exact_values(a, b, expected_km: float) -> None:
    assert haversine_km(*a, *b) == pytest.approx(expected_km, abs=1e-6)


@pytest.mark.parametrize(
    ("a", "b", "expected_km"),
    [
        # Real city pairs; expected values are WGS84 ellipsoid distances computed
        # with GeographicLib (Karney). The sphere model may differ by up to ~0.5%.
        ((51.5074, -0.1278), (48.8566, 2.3522), 343.9),  # London - Paris
        ((40.7128, -74.0060), (34.0522, -118.2437), 3944.4),  # New York - Los Angeles
        ((14.5995, 120.9842), (10.3157, 123.8854), 569.2),  # Manila - Cebu City
    ],
)
def test_haversine_matches_real_distances(a, b, expected_km: float) -> None:
    assert haversine_km(*a, *b) == pytest.approx(expected_km, rel=0.01)


def test_haversine_is_symmetric() -> None:
    assert haversine_km(14.55, 121.05, -33.87, 151.21) == haversine_km(-33.87, 151.21, 14.55, 121.05)


def test_bounding_box_normal_case() -> None:
    box = bounding_box(14.55, 121.05, 10)

    assert not box.crosses_antimeridian
    assert box.min_lat < 14.55 < box.max_lat
    assert box.min_lon < 121.05 < box.max_lon


def test_bounding_box_wraps_across_antimeridian() -> None:
    box = bounding_box(0, 179.9, 50)

    assert box.crosses_antimeridian
    assert box.min_lon > 179
    assert box.max_lon < -179


def test_bounding_box_covering_a_pole_spans_all_longitudes() -> None:
    box = bounding_box(89.95, 10, 50)

    assert box.max_lat >= 90
    assert (box.min_lon, box.max_lon) == (-180.0, 180.0)
