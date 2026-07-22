from fastapi import FastAPI
from models import Property
from analysis import analyze
from services import lookup_property
from search_models import PropertySearch
app = FastAPI()


@app.get("/")
def home():
    return {
        "message": "Housing OS Land Agent is online"
    }


@app.post("/analyze-property")
def analyze_property(property: Property):

    property_data = lookup_property(property.address)

    results = analyze(property)

    return {
        "lookup": property_data,
        "property": property,
        "analysis": results
    }
@app.post("/lookup-property")
def lookup_property_endpoint(search: PropertySearch):

    property_data = lookup_property(search.address)

    return {
        "property": property_data
    }