from pydantic import BaseModel
from typing import Optional


class Property(BaseModel):
    address: str
    city: str
    state: str
    zip_code: Optional[str] = None

    # Parcel information
    apn: Optional[str] = None
    parcel_number: Optional[str] = None

    # Ownership
    owner: Optional[str] = None

    # Physical characteristics
    lot_size_sqft: Optional[float] = None
    acreage: Optional[float] = None

    # Location
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    # Planning information
    jurisdiction: Optional[str] = None
    zoning: Optional[str] = None
    allowed_uses: Optional[list[str]] = None

    # AI notes
    development_notes: Optional[str] = None

    # Data tracking
    source: Optional[str] = None