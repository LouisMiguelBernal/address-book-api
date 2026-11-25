"""HTTP endpoints for addresses.

Endpoints are plain ``def`` (not ``async def``) because SQLAlchemy's SQLite
driver is blocking. FastAPI runs sync endpoints in a threadpool, so a slow
query never blocks the event loop.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app import crud, geo
from app.database import get_db
from app.models import Address
from app.schemas import AddressIn, AddressOut, NearbyAddressOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/addresses", tags=["addresses"])

DbSession = Annotated[Session, Depends(get_db)]


def _get_or_404(db: Session, address_id: int) -> Address:
    address = crud.get_address(db, address_id)
    if address is None:
        logger.warning("Address id=%s not found", address_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found")
    return address


# Declared before "/{address_id}" so "nearby" is not parsed as an ID.
@router.get(
    "/nearby",
    response_model=list[NearbyAddressOut],
    summary="Find addresses within a distance of a point",
    description="Returns every address within `radius_km` of (`lat`, `lon`), nearest first. "
    "The radius is inclusive.",
)
def find_nearby_addresses(
    db: DbSession,
    lat: Annotated[
        float, Query(ge=-90, le=90, description="Latitude of the search point", examples=[14.5547])
    ],
    lon: Annotated[
        float, Query(ge=-180, le=180, description="Longitude of the search point", examples=[121.0244])
    ],
    radius_km: Annotated[
        float,
        Query(
            ge=0,
            le=geo.MAX_DISTANCE_KM,
            description=f"Search radius in km (max {geo.MAX_DISTANCE_KM:.1f}, which covers the whole Earth)",
            examples=[5],
        ),
    ],
) -> list[NearbyAddressOut]:
    return [
        NearbyAddressOut(**AddressOut.model_validate(address).model_dump(), distance_km=round(distance, 3))
        for address, distance in crud.find_nearby(db, lat, lon, radius_km)
    ]


@router.post(
    "",
    response_model=AddressOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create an address",
)
def create_address(data: AddressIn, db: DbSession) -> Address:
    return crud.create_address(db, data)


@router.get("", response_model=list[AddressOut], summary="List addresses")
def list_addresses(
    db: DbSession,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> list[Address]:
    return crud.list_addresses(db, offset, limit)


@router.get(
    "/{address_id}",
    response_model=AddressOut,
    summary="Get one address",
    responses={404: {"description": "Address not found"}},
)
def get_address(address_id: int, db: DbSession) -> Address:
    return _get_or_404(db, address_id)


@router.put(
    "/{address_id}",
    response_model=AddressOut,
    summary="Update an address",
    description="Replaces every field of the address.",
    responses={404: {"description": "Address not found"}},
)
def update_address(address_id: int, data: AddressIn, db: DbSession) -> Address:
    address = _get_or_404(db, address_id)
    return crud.update_address(db, address, data)


@router.delete(
    "/{address_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an address",
    responses={404: {"description": "Address not found"}},
)
def delete_address(address_id: int, db: DbSession) -> Response:
    address = _get_or_404(db, address_id)
    crud.delete_address(db, address)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
