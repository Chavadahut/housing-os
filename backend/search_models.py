from pydantic import BaseModel
from typing import Optional, Any


class PropertyLookupRequest(BaseModel):
    address: str


class Zoning(BaseModel):
    code: Optional[str] = None
    ordinance: Optional[str] = None
    implementation_date: Optional[Any] = None
    jurisdiction: Optional[str] = None
    status: Optional[str] = None
    source: Optional[str] = None
    message: Optional[str] = None
    lookup_method: Optional[str] = None
    search_distance_feet: Optional[int] = None


class Parcel(BaseModel):
    apn: Optional[str] = None
    address: Optional[str] = None
    zip: Optional[str] = None
    community: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    zoning: Optional[Zoning] = None


class PropertySearchResponse(BaseModel):
    address: str
    parcel_count: int
    parcels: list[Parcel]
    source: str
    status: Optional[str] = None
    message: Optional[str] = None