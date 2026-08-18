"""Official City of Encinitas zoning connector."""

import re

import requests

from connectors.municipal_common import (
    clean_text,
    empty_zoning,
    query_arcgis_point,
)


CITY = "City of Encinitas"
SOURCE = "City of Encinitas E-Zoning GIS"
ZONING_LAYER = (
    "https://coemapservices.encinitasca.gov/hypegis/rest/services/"
    "Unsecured/E_Zoning/MapServer/0"
)


def _attribute(attributes: dict, suffix: str):
    suffix = suffix.lower()
    for key, value in attributes.items():
        if str(key).lower().split(".")[-1] == suffix:
            return value
    return None


def get_encinitas_zoning_data(latitude: float, longitude: float) -> dict:
    try:
        features = query_arcgis_point(ZONING_LAYER, latitude, longitude)
    except requests.Timeout:
        return empty_zoning(CITY, SOURCE, "timeout", "The Encinitas zoning service timed out.")
    except (requests.RequestException, ValueError) as error:
        return empty_zoning(CITY, SOURCE, "error", str(error))

    if not features:
        return empty_zoning(
            CITY,
            SOURCE,
            "not_found",
            "No official Encinitas zoning polygon intersected the parcel point.",
        )

    attributes = features[0].get("attributes") or {}
    code = clean_text(_attribute(attributes, "ZoneDesignation"))
    description = clean_text(_attribute(attributes, "Description"))
    plan_name = clean_text(_attribute(attributes, "PlanName"))

    density = None
    density_match = re.search(r"(?:R|SFR|RS)(\d+(?:\.\d+)?)", code or "")
    if density_match:
        density = f"{density_match.group(1)} dwelling units per acre"

    return {
        **empty_zoning(CITY, SOURCE, "found", None),
        "code": code,
        "use_regulation": description,
        "density": density,
        "special_regulations": plan_name,
        "lookup_method": "exact_point",
        "search_distance_feet": 0,
    }


def get_encinitas_general_plan_data(
    latitude: float,
    longitude: float,
    parcel_acres: float | None = None,
) -> dict:
    zoning = get_encinitas_zoning_data(latitude, longitude)
    code = zoning.get("code")
    density = None
    density_match = re.search(r"(?:R|SFR|RS)(\d+(?:\.\d+)?)", code or "")
    if density_match:
        density = float(density_match.group(1))

    estimated_units = None
    if density and parcel_acres:
        estimated_units = max(1, int(parcel_acres * density))

    return {
        "designation": zoning.get("use_regulation") or code,
        "designation_code": code,
        "description": zoning.get("use_regulation"),
        "raw_density": (
            f"{density:g} dwelling units per acre" if density else None
        ),
        "raw_potential_units": parcel_acres * density if parcel_acres and density else None,
        "maximum_density": density,
        "gross_acres_per_unit": 1 / density if density else None,
        "estimated_maximum_units": estimated_units,
        "estimate_status": "zoning_based_screening_only",
        "mixed_use": "YES" if "CM" in (code or "") else None,
        "mixed_use_name": zoning.get("use_regulation") if "CM" in (code or "") else None,
        "general_plan_code": code,
        "case_number": None,
        "adoption_date": None,
        "jurisdiction": CITY,
        "status": zoning.get("status"),
        "source": "City of Encinitas E-Zoning GIS (zoning-based General Plan screening)",
        "message": zoning.get("message"),
        "warning": (
            "This is a zoning-based screening result, not a separate controlling "
            "General Plan map query. Specific Plans, overlays, net acreage, "
            "environmental limits, and city confirmation still control capacity."
        ),
        "lookup_method": zoning.get("lookup_method"),
        "search_distance_feet": zoning.get("search_distance_feet"),
    }
