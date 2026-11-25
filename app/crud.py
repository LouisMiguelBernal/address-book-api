"""Database operations for addresses.

Routes call these functions instead of querying the database directly, which
keeps HTTP concerns (status codes, errors) separate from persistence.
"""

import heapq
import logging

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app import geo
from app.models import Address
from app.schemas import AddressIn

logger = logging.getLogger(__name__)


def create_address(db: Session, data: AddressIn) -> Address:
    address = Address(**data.model_dump())
    db.add(address)
    db.commit()
    db.refresh(address)
    logger.info("Created address id=%s", address.id)
    return address


def get_address(db: Session, address_id: int) -> Address | None:
    return db.get(Address, address_id)


def list_addresses(db: Session, offset: int, limit: int) -> list[Address]:
    stmt = select(Address).order_by(Address.id).offset(offset).limit(limit)
    return list(db.scalars(stmt))


def update_address(db: Session, address: Address, data: AddressIn) -> Address:
    """Replace every field of an existing address."""
    for field, value in data.model_dump().items():
        setattr(address, field, value)
    db.commit()
    db.refresh(address)
    logger.info("Updated address id=%s", address.id)
    return address


def delete_address(db: Session, address: Address) -> None:
    address_id = address.id
    db.delete(address)
    db.commit()
    logger.info("Deleted address id=%s", address_id)


def find_nearby(
    db: Session, lat: float, lon: float, radius_km: float, limit: int
) -> list[tuple[Address, float]]:
    """Return up to ``limit`` ``(address, distance_km)`` pairs within ``radius_km``.

    Results are nearest first; equal distances are ordered by ID so the output is
    deterministic. Two steps:
    1. SQL bounding-box filter on the indexed latitude/longitude columns, so the
       database only returns rows that could possibly be in range.
    2. Exact haversine distance in Python on those candidates.
    """
    box = geo.bounding_box(lat, lon, radius_km)

    lon_condition = (
        or_(Address.longitude >= box.min_lon, Address.longitude <= box.max_lon)
        if box.crosses_antimeridian
        else Address.longitude.between(box.min_lon, box.max_lon)
    )
    stmt = select(Address).where(and_(Address.latitude.between(box.min_lat, box.max_lat), lon_condition))
    candidates = db.scalars(stmt).all()

    matches = []
    for address in candidates:
        distance = geo.haversine_km(lat, lon, address.latitude, address.longitude)
        if distance <= radius_km:
            matches.append((address, distance))
    # nsmallest keeps only `limit` items: O(n log limit) instead of sorting everything.
    results = heapq.nsmallest(limit, matches, key=lambda pair: (pair[1], pair[0].id))

    logger.debug(
        "Nearby search lat=%s lon=%s radius_km=%s: %d candidates, %d matches, %d returned",
        lat,
        lon,
        radius_km,
        len(candidates),
        len(matches),
        len(results),
    )
    return results
