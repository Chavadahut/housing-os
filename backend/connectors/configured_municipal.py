"""Verified field-mapped municipal ArcGIS connectors."""

from __future__ import annotations

import re

import requests

from connectors.municipal_common import clean_text, empty_zoning, manual_permit_result, query_arcgis_point


SANDAG_PLANNED_LAND_USE = (
    "https://geo.sandag.org/server/rest/services/Hosted/"
    "Landuse_Forecast_2050_SG/FeatureServer/0"
)

CITY_CONFIG = {
    "chula_vista": {
        "city": "City of Chula Vista",
        "zoning": "https://services2.arcgis.com/2nV1ORz8qFa0iiF2/arcgis/rest/services/Chula_Vista_Zoning_District_Boundary_Data/FeatureServer/10",
        "zoning_code": "ZONE",
        "zoning_description": "ZoneDesc",
        "zoning_category": "ZoneCategory",
        "zoning_special": "PCDistrict",
        "general_plan": "https://services2.arcgis.com/2nV1ORz8qFa0iiF2/arcgis/rest/services/Chula_Vista_General_Plan_Data/FeatureServer/3",
        "general_plan_code": "CODE",
        "permit_url": "https://www.chulavistaca.gov/departments/development-services/permit-information",
        "records_url": "https://www.chulavistaca.gov/departments/city-clerk/public-records",
    },
    "escondido": {
        "city": "City of Escondido",
        "zoning": "https://services2.arcgis.com/eJcVbjTyyZIzZ5Ye/arcgis/rest/services/Zoning/FeatureServer/0",
        "zoning_code": "ZONING",
        "general_plan": "https://services2.arcgis.com/eJcVbjTyyZIzZ5Ye/arcgis/rest/services/General_Plan/FeatureServer/0",
        "general_plan_code": "GENPLAN",
        "permit_url": "https://portal.maintstar.co/escondido/portal/#/modules/permit/permitSearch",
        "records_url": "https://www.escondido.gov/1127/Public-Records-Request",
    },
    "oceanside": {
        "city": "City of Oceanside",
        "zoning": "https://gis.oceansideca.org/gis/rest/services/WebService/Planning_Hub/FeatureServer/11",
        "zoning_code": "Zone_Code",
        "zoning_description": "Zone_Descr",
        "zoning_category": "Category",
        "zoning_special": "MP_SP",
        "height": "Height",
        "setback": "Front_Setb",
        "minimum_lot_size": "Min_Lot_Si",
        "floor_area_ratio": "Floor_Area",
        "coverage": "Lot_Covera",
        "density": "Density",
        "general_plan": "https://gis.oceansideca.org/gis/rest/services/WebService/Planning_Hub/FeatureServer/10",
        "general_plan_code": "Landuse_Code",
        "general_plan_description": "Category",
        "permit_url": "https://public-access.oceansideca.org/etrakit/",
        "records_url": "https://www.ci.oceanside.ca.us/government/city-clerk/public-records",
    },
    "poway": {
        "city": "City of Poway",
        "zoning": "https://powaygis.poway.org/powaygis/rest/services/Public/PowHUB_Planning_Survey_Street_Transportation_Layers/MapServer/4",
        "zoning_code": "ZoningCode",
        "zoning_description": "ZoningDescription",
        "general_plan": SANDAG_PLANNED_LAND_USE,
        "general_plan_code": "plu",
        "general_plan_description": "plannedlu",
        "general_plan_is_regional_fallback": True,
        "permit_url": "https://poway.org/636/Online-Services",
        "records_url": "https://poway.org/636/Public-Records",
    },
    "lemon_grove": {
        "city": "City of Lemon Grove",
        "zoning": "https://services7.arcgis.com/D1qgPMtsRENpZIBr/ArcGIS/rest/services/Zoning___STA_Overlay/FeatureServer/51",
        "zoning_code": "FIRST_ZONE",
        "zoning_description": "FIRST_LABEL",
        "zoning_special": "CODE",
        "general_plan": SANDAG_PLANNED_LAND_USE,
        "general_plan_code": "plu",
        "general_plan_description": "plannedlu",
        "general_plan_is_regional_fallback": True,
        "permit_url": "https://www.lemongrove.ca.gov/business/development-services/permits",
        "records_url": "https://www.lemongrove.ca.gov/government/city-clerk/public-records",
    },
    "santee": {
        "city": "City of Santee",
        "zoning": "https://services7.arcgis.com/z04laB9joMn9C8en/ArcGIS/rest/services/Santee_City_SUs_AND_Buffers_upd_4_8_22/FeatureServer/19",
        "zoning_code": "ZONE_CODE",
        "zoning_description": "ZONE_DESCR",
        "zoning_special": "OVRLY_CODE",
        "general_plan": SANDAG_PLANNED_LAND_USE,
        "general_plan_code": "plu",
        "general_plan_description": "plannedlu",
        "general_plan_is_regional_fallback": True,
        "permit_url": "https://www.cityofsanteeca.gov/government/development-services/building/permits",
        "records_url": "https://www.cityofsanteeca.gov/government/city-clerk/public-records",
    },
    "coronado": {"city": "City of Coronado", "zoning": None, "zoning_map_url": "https://www.coronado.ca.us/DocumentCenter/View/222/Residential-and-Business-Zoning-Map-PDF", "general_plan": SANDAG_PLANNED_LAND_USE, "general_plan_code": "plu", "general_plan_description": "plannedlu", "general_plan_is_regional_fallback": True, "permit_url": "https://www.coronado.ca.us/269/Planning-Zoning", "records_url": "https://www.coronado.ca.us/244/Public-Records-Request"},
    "del_mar": {"city": "City of Del Mar", "zoning": None, "zoning_map_url": "https://delmar.geoviewer.io/", "general_plan": SANDAG_PLANNED_LAND_USE, "general_plan_code": "plu", "general_plan_description": "plannedlu", "general_plan_is_regional_fallback": True, "permit_url": "https://www.delmar.ca.us/865/eTRAKIT---Online-Portal", "records_url": "https://www.delmar.ca.us/179/Public-Records"},
    "el_cajon": {"city": "City of El Cajon", "zoning": "https://services2.arcgis.com/sNwJsChyrhgtFVFc/arcgis/rest/services/EnerGov/FeatureServer/4", "zoning_code": "Zone", "zoning_description": "Zone_Description", "general_plan": "https://services2.arcgis.com/sNwJsChyrhgtFVFc/arcgis/rest/services/EnerGov/FeatureServer/6", "general_plan_code": "GPLABEL", "general_plan_description": "Land_Use_Element", "permit_url": "https://www.elcajon.gov/your-government/departments/community-development", "records_url": "https://www.elcajon.gov/your-government/departments/city-clerk/public-records"},
    "imperial_beach": {"city": "City of Imperial Beach", "zoning": None, "zoning_map_url": "https://www.imperialbeachca.gov/250/Planning-Division-Forms-Applications", "general_plan": SANDAG_PLANNED_LAND_USE, "general_plan_code": "plu", "general_plan_description": "plannedlu", "general_plan_is_regional_fallback": True, "permit_url": "https://imperialbeachca-energovpub.tylerhost.net/Apps/SelfService#/home", "records_url": "https://www.imperialbeachca.gov/127/Public-Records"},
    "national_city": {"city": "National City", "zoning": "https://services7.arcgis.com/RLQtED7qlYHuT1ha/arcgis/rest/services/NC_Zoning_Web_Map_WFL1/FeatureServer/20", "zoning_code": "Zoning", "zoning_description": "Land_Use", "zoning_special": "Spec_Plan", "floor_area_ratio": "FAR", "general_plan": SANDAG_PLANNED_LAND_USE, "general_plan_code": "plu", "general_plan_description": "plannedlu", "general_plan_is_regional_fallback": True, "permit_url": "https://www.nationalcityca.gov/government/community-development/building", "records_url": "https://www.nationalcityca.gov/government/city-clerk/public-records-request"},
    "san_marcos": {"city": "City of San Marcos", "zoning": "https://services1.arcgis.com/e7Mp0AHrN8K5Kx6X/arcgis/rest/services/Zoning/FeatureServer/16", "zoning_code": "ZoneCode", "zoning_description": "ZoneFull", "zoning_special": "SpecificPlanArea", "density": "Density_Intensity", "general_plan": SANDAG_PLANNED_LAND_USE, "general_plan_code": "plu", "general_plan_description": "plannedlu", "general_plan_is_regional_fallback": True, "permit_url": "https://www.san-marcos.net/departments/development-services", "records_url": "https://www.san-marcos.net/departments/city-clerk/public-records"},
    "solana_beach": {"city": "City of Solana Beach", "zoning": "https://services1.arcgis.com/66rlqhJHNZTkrmk1/arcgis/rest/services/Zoning/FeatureServer/0", "zoning_code": "ZONING", "general_plan": SANDAG_PLANNED_LAND_USE, "general_plan_code": "plu", "general_plan_description": "plannedlu", "general_plan_is_regional_fallback": True, "permit_url": "https://www.cityofsolanabeach.org/en/government/community-development", "records_url": "https://www.cityofsolanabeach.org/en/government/city-clerk"},
    "vista": {"city": "City of Vista", "zoning": None, "zoning_map_url": "https://gis.cityofvista.com/gvimages/general/Map-Zoning.pdf", "general_plan": SANDAG_PLANNED_LAND_USE, "general_plan_code": "plu", "general_plan_description": "plannedlu", "general_plan_is_regional_fallback": True, "permit_url": "https://www.cityofvista.com/departments/community-development/building", "records_url": "https://www.cityofvista.com/city-hall/city-clerk/public-records"},
}


def _density_number(value) -> float | None:
    text = clean_text(value)
    if not text:
        return None
    patterns = (
        r"(\d+(?:\.\d+)?)\s*(?:DU|DWELLING UNITS?)\s*/?\s*(?:AC|ACRE)",
        r"(?:R|RM|RH|RS)[- ]?(\d+(?:\.\d+)?)",
    )
    for pattern in patterns:
        matches = re.findall(pattern, text.upper())
        if matches:
            return max(float(match) for match in matches)
    return None


def get_configured_zoning_data(city_key: str, latitude: float, longitude: float, apn: str | None = None) -> dict:
    config = CITY_CONFIG[city_key]
    city = config["city"]
    source = f"{city} official planning GIS"
    if city_key == "imperial_beach" and apn:
        try:
            response = requests.get(
                f"https://imperialbeachca.mapgeo.io/api/ui/datasets/public-access/{apn}",
                headers={"Accept": "application/json"},
                timeout=15,
            )
            response.raise_for_status()
            attrs = response.json().get("data") or {}
        except requests.Timeout:
            return empty_zoning(city, "City of Imperial Beach official MapGeo parcel GIS", "timeout", "The Imperial Beach parcel service timed out.")
        except (requests.RequestException, ValueError) as error:
            return empty_zoning(city, "City of Imperial Beach official MapGeo parcel GIS", "error", str(error))
        if attrs:
            return {
                **empty_zoning(city, "City of Imperial Beach official MapGeo parcel GIS", "found", None),
                "code": clean_text(attrs.get("zongp")),
                "use_regulation": clean_text(attrs.get("zondesc")),
                "ordinance": clean_text(attrs.get("zonlnk")),
                "lookup_method": "exact_apn",
                "search_distance_feet": 0,
            }
    if not config.get("zoning"):
        return {
            **empty_zoning(city, f"{city} official zoning map", "manual_review_required", "The city does not publish a reliable public parcel-query zoning service; confirm the parcel on the official city map."),
            "zoning_map_url": config.get("zoning_map_url"),
            "manual_research_required": True,
        }
    try:
        features = query_arcgis_point(config["zoning"], latitude, longitude)
    except requests.Timeout:
        return empty_zoning(city, source, "timeout", f"The {city} zoning service timed out.")
    except (requests.RequestException, ValueError) as error:
        return empty_zoning(city, source, "error", str(error))
    if not features:
        return empty_zoning(city, source, "not_found", "No official city zoning polygon intersected the parcel point.")
    attrs = features[0].get("attributes") or {}
    special_values = [
        clean_text(attrs.get(config.get("zoning_special"))) if config.get("zoning_special") else None,
        clean_text(attrs.get("Overlay1")),
        clean_text(attrs.get("Overlay2")),
    ]
    return {
        **empty_zoning(city, source, "found", None),
        "code": clean_text(attrs.get(config["zoning_code"])),
        "use_regulation": clean_text(attrs.get(config.get("zoning_description"))) if config.get("zoning_description") else clean_text(attrs.get(config.get("zoning_category"))),
        "density": clean_text(attrs.get(config.get("density"))) if config.get("density") else None,
        "minimum_lot_size": clean_text(attrs.get(config.get("minimum_lot_size"))) if config.get("minimum_lot_size") else None,
        "floor_area_ratio": clean_text(attrs.get(config.get("floor_area_ratio"))) if config.get("floor_area_ratio") else None,
        "height": clean_text(attrs.get(config.get("height"))) if config.get("height") else None,
        "coverage": clean_text(attrs.get(config.get("coverage"))) if config.get("coverage") else None,
        "setback": clean_text(attrs.get(config.get("setback"))) if config.get("setback") else None,
        "special_regulations": "; ".join(value for value in special_values if value) or None,
        "lookup_method": "exact_point",
        "search_distance_feet": 0,
    }


def get_configured_general_plan_data(
    city_key: str,
    latitude: float,
    longitude: float,
    parcel_acres: float | None = None,
) -> dict:
    config = CITY_CONFIG[city_key]
    city = config["city"]
    source = (
        "SANDAG regional planned-land-use screening fallback"
        if config.get("general_plan_is_regional_fallback")
        else f"{city} official General Plan GIS"
    )
    try:
        features = query_arcgis_point(config["general_plan"], latitude, longitude)
    except requests.Timeout:
        features, status, message = [], "timeout", f"The {city} planning service timed out."
    except (requests.RequestException, ValueError) as error:
        features, status, message = [], "error", str(error)
    else:
        status, message = ("found", None) if features else ("not_found", "No planning designation intersected the parcel point.")
    attrs = (features[0].get("attributes") or {}) if features else {}
    code = clean_text(attrs.get(config["general_plan_code"]))
    description = clean_text(attrs.get(config.get("general_plan_description"))) if config.get("general_plan_description") else code
    density = _density_number(description or code)
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
        "estimate_status": "regional_fallback_only" if config.get("general_plan_is_regional_fallback") else ("preliminary_gross_density_estimate" if units else "designation_found_density_not_parsed"),
        "mixed_use": None,
        "mixed_use_name": None,
        "general_plan_code": code,
        "case_number": None,
        "adoption_date": None,
        "jurisdiction": city,
        "status": status,
        "source": source,
        "message": message,
        "warning": (
            "This is regional screening data, not the controlling city General Plan determination."
            if config.get("general_plan_is_regional_fallback")
            else "Confirm density, overlays, Specific Plans, and development standards with the city."
        ),
        "lookup_method": "exact_point" if features else None,
        "search_distance_feet": 0 if features else None,
    }


def get_configured_permit_history_data(city_key: str, apn: str | None, address: str | None = None) -> dict:
    config = CITY_CONFIG[city_key]
    return manual_permit_result(
        city=config["city"],
        portal_url=config["permit_url"],
        public_records_url=config["records_url"],
        apn=apn,
        address=address,
    )
