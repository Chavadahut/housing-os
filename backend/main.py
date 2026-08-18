from fastapi import FastAPI
from pydantic import BaseModel

import progressive_lookup
import quick_lookup
import services

from models import Property
from analysis import analyze
from parcel_locator import get_parcel_data_resilient
from search_models import (
    PropertyLookupRequest,
    PropertySearchResponse,
)
from property_cache import (
    clear_expired_cache,
    get_cached_by_address_or_apn,
    initialize_cache_database,
    save_cached_property,
)
from performance_cache import install_dataset_cache


app = FastAPI()


def full_result_is_cacheable(result: dict) -> bool:
    parcels = result.get("parcels") or []

    if not parcels:
        return False

    transient_statuses = {
        "timeout",
        "service_error",
        "error",
        "invalid_response",
    }

    for parcel in parcels:
        lot_size = parcel.get("lot_size") or {}
        if not lot_size.get("acreage"):
            return False

        for section in ("zoning", "general_plan"):
            status = (parcel.get(section) or {}).get("status")
            if status in transient_statuses:
                return False

    return True


class ProgressiveSectionRequest(BaseModel):
    address: str
    section: str


# Use one resilient parcel locator everywhere.
services.get_parcel_data = get_parcel_data_resilient
quick_lookup.get_parcel_data = get_parcel_data_resilient
progressive_lookup.get_parcel_data = get_parcel_data_resilient

# All modules share the same SQLite dataset cache. A dataset loaded by
# one endpoint is therefore reused by the other endpoints.
install_dataset_cache(services)
install_dataset_cache(quick_lookup)
install_dataset_cache(progressive_lookup)


@app.on_event("startup")
def startup_event():
    initialize_cache_database()
    clear_expired_cache()


@app.get("/")
def home():
    return {"message": "Housing OS Land Agent is online"}


@app.post("/lookup-property/base")
def lookup_base(request: PropertyLookupRequest):
    """
    Return the parcel, acreage, and basic map as soon as possible.
    No secondary government dataset can hold this response open.
    """
    cached_full = get_cached_by_address_or_apn(
        cache_type="full",
        address=request.address,
    )

    if cached_full is not None:
        requested_zip_match = __import__("re").search(r"\b(\d{5})\b", request.address)
        cached_parcels = cached_full.get("parcels") or []
        cached_zip = str(cached_parcels[0].get("zip") or "") if cached_parcels else ""
        # Do not let an old alias/cache entry bind a repeated street address
        # to a parcel in a different city/ZIP.
        if not requested_zip_match or not cached_zip or cached_zip == requested_zip_match.group(1):
            return cached_full

    return progressive_lookup.lookup_property_base(
        request.address
    )


@app.get("/diagnostics/version")
def diagnostics_version():
    """Small local-development marker used to verify reloads."""
    return {"parcel_locator_revision": "exact-official-v2"}




@app.post("/lookup-property/section")
def lookup_section(request: ProgressiveSectionRequest):
    """
    Load exactly one independent dataset. The frontend fires these
    requests concurrently and inserts each result as it finishes.
    """
    cached_full = get_cached_by_address_or_apn(
        cache_type="full",
        address=request.address,
    )

    if cached_full is not None:
        parcels = cached_full.get("parcels") or []

        return {
            "section": request.section,
            "status": "complete",
            "results": [
                {
                    "apn": parcel.get("apn"),
                    "data": parcel.get(request.section),
                }
                for parcel in parcels
            ],
            "source": "full_property_cache",
        }

    return progressive_lookup.lookup_property_section(
        address=request.address,
        section=request.section,
    )


@app.post(
    "/lookup-property/quick",
    response_model=PropertySearchResponse,
)
def lookup_quick(request: PropertyLookupRequest):
    cached_full = get_cached_by_address_or_apn(
        cache_type="full",
        address=request.address,
    )

    if cached_full is not None:
        return cached_full

    cached_quick = get_cached_by_address_or_apn(
        cache_type="quick",
        address=request.address,
    )

    if cached_quick is not None:
        return cached_quick

    result = quick_lookup.lookup_property_quick(
        request.address
    )

    if result.get("parcels"):
        save_cached_property(
            cache_type="quick",
            address=request.address,
            result=result,
        )

    return result


@app.post(
    "/lookup-property",
    response_model=PropertySearchResponse,
)
def lookup(request: PropertyLookupRequest):
    """
    Run a fresh full-property lookup.

    The full-cache read is temporarily bypassed here so code and connector
    changes can be tested without an older saved property response masking
    the new result. Successful results are still saved back into the full
    property cache.
    """
    result = services.lookup_property(
        request.address
    )

    if full_result_is_cacheable(result):
        save_cached_property(
            cache_type="full",
            address=request.address,
            result=result,
        )

    return result


@app.post("/analyze-property")
def analyze_property(property: Property):
    cached = get_cached_by_address_or_apn(
        cache_type="full",
        address=property.address,
    )

    if cached is not None:
        property_data = cached
    else:
        property_data = services.lookup_property(
            property.address
        )

        if full_result_is_cacheable(property_data):
            save_cached_property(
                cache_type="full",
                address=property.address,
                result=property_data,
            )

    results = analyze(property)

    return {
        "lookup": property_data,
        "property": property,
        "analysis": results,
    }
