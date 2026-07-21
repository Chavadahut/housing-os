from pydantic import BaseModel
from typing import Optional


class Property(BaseModel):
    address: str
    city: str
    state: str
    zip_code: Optional[str] = None
    
    parcel_number: Optional[str] = None
    owner: Optional[str] = None
    
    lot_size_sqft: Optional[float] = None
    zoning: Optional[str] = None
    
    allowed_uses: Optional[list[str]] = None
    development_notes: Optional[str] = None