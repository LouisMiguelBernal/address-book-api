"""Request and response schemas. All input validation happens here."""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

# Largest value SQLite can store in an INTEGER column; larger IDs would overflow the driver.
MAX_DB_INT = 2**63 - 1


def _text(max_length: int) -> StringConstraints:
    # Trimmed before the checks, so "   " is rejected as empty. Control characters
    # (newlines, tabs, NUL...) are rejected; any other Unicode text is allowed.
    return StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=max_length,
        pattern=r"^[^\x00-\x1f\x7f]+$",
    )


# strict=True: accept JSON numbers only. Without it, true would become 1.0 and "10.5" would be parsed.
Latitude = Annotated[
    float,
    Field(strict=True, ge=-90, le=90, allow_inf_nan=False, description="Degrees (WGS84)", examples=[14.5507]),
]
Longitude = Annotated[
    float,
    Field(
        strict=True, ge=-180, le=180, allow_inf_nan=False, description="Degrees (WGS84)", examples=[121.0494]
    ),
]

_EXAMPLE_IN = {
    "name": "Eastvantage BGC Office",
    "street": "26th Street corner 5th Avenue",
    "city": "Taguig",
    "state": "Metro Manila",
    "postal_code": "1634",
    "country": "Philippines",
    "latitude": 14.5507,
    "longitude": 121.0494,
}
_EXAMPLE_OUT = {
    "id": 1,
    **_EXAMPLE_IN,
    "created_at": "2026-11-25T08:00:00Z",
    "updated_at": "2026-11-25T08:00:00Z",
}


class AddressIn(BaseModel):
    """Body for creating an address and for replacing one (PUT)."""

    # Unknown fields (typos, or read-only fields like "id") are rejected instead of silently dropped.
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [_EXAMPLE_IN]})

    name: Annotated[str, _text(100)] = Field(description="Label for the address, e.g. 'Home'")
    street: Annotated[str, _text(200)]
    city: Annotated[str, _text(100)]
    state: Annotated[str, _text(100)] | None = None
    postal_code: Annotated[str, _text(20)] | None = None
    country: Annotated[str, _text(100)]
    latitude: Latitude
    longitude: Longitude


class AddressOut(BaseModel):
    """An address as stored in the database."""

    model_config = ConfigDict(from_attributes=True, json_schema_extra={"examples": [_EXAMPLE_OUT]})

    id: int
    name: str
    street: str
    city: str
    state: str | None
    postal_code: str | None
    country: str
    latitude: float
    longitude: float
    created_at: datetime = Field(description="UTC")
    updated_at: datetime = Field(description="UTC")

    @field_validator("created_at", "updated_at")
    @classmethod
    def _assume_utc(cls, value: datetime) -> datetime:
        # SQLite stores datetimes without a timezone; the app always writes UTC.
        return value if value.tzinfo else value.replace(tzinfo=UTC)


class NearbyAddressOut(BaseModel):
    """One nearby-search match: the address and its distance from the search point."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"address": _EXAMPLE_OUT, "distance_km": 2.727}]}
    )

    address: AddressOut
    distance_km: float = Field(description="Great-circle distance from the search point, in km (3 decimals)")
