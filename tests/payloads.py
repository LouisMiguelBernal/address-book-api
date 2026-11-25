"""Shared test data."""

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


def address(**overrides: object) -> dict:
    """A valid address payload with any fields overridden."""
    return {**VALID_ADDRESS, **overrides}
