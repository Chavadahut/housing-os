"""Shared helpers for incorporated-city planning connectors."""

from __future__ import annotations

from typing import Any

import requests


CONNECT_TIMEOUT_SECONDS = 3.05
READ_TIMEOUT_SECONDS = 12


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    if not value or value.upper() in {"NULL", "NONE", "N/A", "NA", "-"}:
        return None
    return value


def query_arcgis_point(
    layer_url: str,
    latitude: float,
    longitude: float,
    *,
    out_fields: str = "*",
    distance_feet: int = 0,
) -> list[dict]:
    params = {
        "where": "1=1",
        "geometry": f"{longitude},{latitude}",
        "geometryType": "esriGeometryPoint",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": out_fields,
        "returnGeometry": "false",
        "f": "json",
    }

    if distance_feet:
        params.update({
            "distance": distance_feet,
            "units": "esriSRUnit_Foot",
        })

    response = requests.get(
        f"{layer_url.rstrip('/')}/query",
        params=params,
        timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
        headers={"User-Agent": "HousingOS/0.1 municipal-planning"},
    )
    response.raise_for_status()
    data = response.json()

    if data.get("error"):
        raise requests.RequestException(str(data["error"]))

    return data.get("features") or []


def empty_zoning(city: str, source: str, status: str, message: str) -> dict:
    return {
        "code": None,
        "use_regulation": None,
        "density": None,
        "minimum_lot_size": None,
        "building_type": None,
        "maximum_floor_area": None,
        "floor_area_ratio": None,
        "height": None,
        "coverage": None,
        "setback": None,
        "open_space": None,
        "animal_regulations": None,
        "special_regulations": None,
        "ordinance": None,
        "case_number": None,
        "implementation_date": None,
        "jurisdiction": city,
        "status": status,
        "source": source,
        "message": message,
        "lookup_method": None,
        "search_distance_feet": None,
    }


def manual_permit_result(
    city: str,
    portal_url: str,
    public_records_url: str | None,
    apn: str | None,
    address: str | None,
) -> dict:
    return {
        "discretionary_application_found": None,
        "discretionary_application_count": 0,
        "discretionary_applications": [],
        "building_permit_history_checked": False,
        "building_permit_found": None,
        "building_permit_count": 0,
        "building_permit_records": [],
        "building_inspection_history_checked": False,
        "building_inspection_count": 0,
        "building_inspection_records": [],
        "code_compliance_history_checked": False,
        "code_compliance_records": [],
        "permit_history_level": "manual_city_portal_review_required",
        "constraint_level": "unknown",
        "development_warning": (
            f"Complete parcel-level permit history for {city} must be "
            "confirmed in the official city portal."
        ),
        "manual_research_required": True,
        "citizen_access_url": portal_url,
        "public_records_url": public_records_url,
        "status": "manual_review_required",
        "source": f"{city} official permit and public-record portals",
        "message": (
            "Housing OS identified the official city research source but "
            "does not claim that a complete permit history was checked "
            "automatically."
        ),
        "analysis_scope": "jurisdiction_specific_manual_permit_screening",
        "jurisdiction": city,
        "lookup_apn": apn,
        "lookup_address": address,
    }
