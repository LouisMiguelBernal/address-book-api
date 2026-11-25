"""Request and response schemas. All input validation happens here."""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


def _text(max_length: int) -> StringConstraints:
    # Strings are trimmed before the length check, so "   " is rejected as empty.
    return StringConstraints(strip_whitespace=True, min_length=1, max_length=max_length)


Latitude = Annotated[
    float,
    Field(ge=-90, le=90, allow_inf_nan=False, description="Degrees (WGS84)", examples=[14.5507]),
]
Longitude = Annotated[
    float,
    Field(ge=-180, le=180, allow_inf_nan=False, description="Degrees (WGS84)", examples=[121.0494]),
]

_EXAMPLE = {
    "name": "Eastvantage BGC Office",
    "street": "26th Street corner 5th Avenue",
    "city": "Taguig",
    "state": "Metro Manila",
    "postal_code": "1634",
    "country": "Philippines",
    "latitude": 14.5507,
    "longitude": 121.0494,
}


class AddressIn(BaseModel):
    """Body for creating an address and for replacing one (PUT)."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE]})

    name: Annotated[str, _text(100)] = Field(description="Label for the address, e.g. 'Home'")
    street: Annotated[str, _text(200)]
    city: Annotated[str, _text(100)]
    state: Annotated[str, _text(100)] | None = None
    postal_code: Annotated[str, _text(20)] | None = None
    country: Annotated[str, _text(100)]
    latitude: Latitude
    longitude: Longitude


class AddressOut(AddressIn):
    """An address as stored in the database."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime = Field(description="UTC")
    updated_at: datetime = Field(description="UTC")

    @field_validator("created_at", "updated_at")
    @classmethod
    def _assume_utc(cls, value: datetime) -> datetime:
        # SQLite stores datetimes without a timezone; the app always writes UTC.
        return value if value.tzinfo else value.replace(tzinfo=UTC)


class NearbyAddressOut(AddressOut):
    """An address returned by the nearby search, with its distance from the search point."""

    distance_km: float = Field(description="Great-circle distance from the search point, in km")
