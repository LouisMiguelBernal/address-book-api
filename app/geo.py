"""Distance maths for the nearby search.

The Earth is modelled as a sphere with the IUGG mean radius. Compared with the
WGS84 ellipsoid this is off by at most ~0.5%, which is acceptable for an
address book and keeps the code dependency-free.
"""

import math
from dataclasses import dataclass

EARTH_RADIUS_KM = 6371.0088
# The farthest any two points can be apart on the sphere (half a great circle).
MAX_DISTANCE_KM = math.pi * EARTH_RADIUS_KM

# Widen the bounding box slightly so floating-point rounding can never drop a
# point that lies exactly on the search radius. ~1 cm; the exact haversine
# check afterwards removes anything outside the radius.
_BOX_PADDING_DEG = 1e-7


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres between two points given in degrees."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)

    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    # min() guards against a value of 1.0000000002 from rounding, which asin rejects.
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


@dataclass(frozen=True)
class BoundingBox:
    """Lat/lon rectangle that contains every point within a radius of a centre.

    When ``min_lon > max_lon`` the box crosses the 180th meridian and the
    longitude condition becomes ``lon >= min_lon OR lon <= max_lon``.
    """

    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float

    @property
    def crosses_antimeridian(self) -> bool:
        return self.min_lon > self.max_lon


def bounding_box(lat: float, lon: float, radius_km: float) -> BoundingBox:
    """Smallest lat/lon box containing the circle of ``radius_km`` around a point.

    Method: J. P. Matuschek, "Finding Points Within a Distance of a
    Latitude/Longitude Using Bounding Coordinates".
    """
    angular = radius_km / EARTH_RADIUS_KM  # radius as an angle (radians)
    lat_r, lon_r = math.radians(lat), math.radians(lon)

    min_lat = lat_r - angular
    max_lat = lat_r + angular

    if min_lat > -math.pi / 2 and max_lat < math.pi / 2:
        # Longitude span widens with latitude because meridians converge.
        delta_lon = math.asin(math.sin(angular) / math.cos(lat_r))
        min_lon_deg = math.degrees(lon_r - delta_lon) - _BOX_PADDING_DEG
        max_lon_deg = math.degrees(lon_r + delta_lon) + _BOX_PADDING_DEG
        # Wrap into [-180, 180]; a wrapped box crosses the antimeridian.
        if min_lon_deg < -180:
            min_lon_deg += 360
        if max_lon_deg > 180:
            max_lon_deg -= 360
    else:
        # The circle contains a pole, so every longitude is in range.
        min_lat = max(min_lat, -math.pi / 2)
        max_lat = min(max_lat, math.pi / 2)
        min_lon_deg, max_lon_deg = -180.0, 180.0

    return BoundingBox(
        min_lat=math.degrees(min_lat) - _BOX_PADDING_DEG,
        max_lat=math.degrees(max_lat) + _BOX_PADDING_DEG,
        min_lon=min_lon_deg,
        max_lon=max_lon_deg,
    )
