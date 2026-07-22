from pydantic import BaseModel


class PropertySearch(BaseModel):
    address: str