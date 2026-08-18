"""Official City of Carlsbad parcel planning attributes."""

import re

import requests

from connectors.municipal_common import clean_text, empty_zoning, query_arcgis_point


CITY = "City of Carlsbad"
SOURCE = "City of Carlsbad official eZoning GIS"
PARCEL_LAYER = (
    "https://utility.arcgis.com/usrsvcs/servers/"
    "60bfb0d5790046a3a81522ec9cfbaf38/rest/services/"
    "SecuredAGOL/eZoning/FeatureServer/4"
)
SANDAG_PLANNED_LAND_USE = (
    "https://geo.sandag.org/server/rest/services/Hosted/"
    "Landuse_Forecast_2050_SG/FeatureServer/0"
)


def _query(latitude: float, longitude: float) -> dict | None:
    features = query_arcgis_point(PARCEL_LAYER, latitude, longitude)
    return (features[0].get("attributes") or {}) if features else None


def get_carlsbad_zoning_data(latitude: float, longitude: float) -> dict:
    try:
        attributes = _query(latitude, longitude)
    except requests.Timeout:
        return empty_zoning(CITY, SOURCE, "timeout", "The Carlsbad GIS timed out.")
    except (requests.RequestException, ValueError) as error:
        return empty_zoning(CITY, SOURCE, "error", str(error))

    if not attributes:
        return empty_zoning(CITY, SOURCE, "not_found", "No Carlsbad parcel planning record was found.")

    zone1 = clean_text(attributes.get("ZONECLASS"))
    description = clean_text(attributes.get("ZONEDESC"))
    return {
        **empty_zoning(CITY, SOURCE, "found", None),
        "code": zone1,
        "use_regulation": description,
        "lookup_method": "exact_point",
        "search_distance_feet": 0,
    }


def get_carlsbad_general_plan_data(
    latitude: float,
    longitude: float,
    parcel_acres: float | None = None,
) -> dict:
    try:
        features = query_arcgis_point(SANDAG_PLANNED_LAND_USE, latitude, longitude)
        attributes = (features[0].get("attributes") or {}) if features else None
    except requests.Timeout:
        attributes = None
        status, message = "timeout", "The Carlsbad GIS timed out."
    except (requests.RequestException, ValueError) as error:
        attributes = None
        status, message = "error", str(error)
    else:
        status, message = ("found", None) if attributes else ("not_found", "No Carlsbad parcel planning record was found.")

    code = clean_text((attributes or {}).get("plu"))
    description = clean_text((attributes or {}).get("plannedlu"))
    density = None
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:DU|DWELLING UNITS?)", description or "", re.I)
    if match:
        density = float(match.group(1))
    units = max(1, int(parcel_acres * density)) if parcel_acres and density else None

    return {
        "designation": description or code,
        "designation_code": code,
        "description": description,
        "raw_density": f"{density:g} dwelling units per acre" if density else None,
        "raw_potential_units": parcel_acres * density if parcel_acres and density else None,
        "maximum_density": density,
        "gross_acres_per_unit": 1 / density if density else None,
        "estimated_maximum_units": units,
        "estimate_status": "regional_fallback_only",
        "mixed_use": None,
        "mixed_use_name": None,
        "general_plan_code": code,
        "case_number": None,
        "adoption_date": None,
        "jurisdiction": CITY,
        "status": status,
        "source": "SANDAG regional planned-land-use screening fallback",
        "message": message,
        "warning": (
            "This is regional screening data, not the controlling City of Carlsbad General Plan determination. "
            "Confirm controlling designations, Specific Plans, overlays, and development standards with Carlsbad."
        ),
        "lookup_method": "exact_point" if attributes else None,
        "search_distance_feet": 0 if attributes else None,
    }
