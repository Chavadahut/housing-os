from fastapi import FastAPI

from models import Property
from analysis import analyze
from services import lookup_property
from search_models import (
    PropertyLookupRequest,
    PropertySearchResponse,
)

app = FastAPI()


@app.get("/")
def home():
    return {
        "message": "Housing OS Land Agent is online"
    }


@app.post("/lookup-property", response_model=PropertySearchResponse)
def lookup(request: PropertyLookupRequest):

    return lookup_property(request.address)


@app.post("/analyze-property")
def analyze_property(property: Property):

    property_data = lookup_property(property.address)

    results = analyze(property)

    return {
        "lookup": property_data,
        "property": property,
        "analysis": results
    }