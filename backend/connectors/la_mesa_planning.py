import math
import re

import requests


CITY_ZONING_URL = (
    "https://utility.arcgis.com/usrsvcs/servers/"
    "f239405db9554f8e9e154ffcae0f3798/"
    "rest/services/CommDev/Zoning_AGO/MapServer/1"
)

CITY_SPECIFIC_PLANS_URL = (
    "https://services3.arcgis.com/iYP51zxNr6TITn6r/"
    "ArcGIS/rest/services/Specific_Plans/FeatureServer/14"
)

SANDAG_PLANNED_LAND_USE_URL = (
    "https://geo.sandag.org/server/rest/services/"
    "Hosted/Landuse_Forecast_2050_SG/FeatureServer/0"
)

REQUEST_TIMEOUT_SECONDS = 20


GENERAL_PLAN_NAMES = {
    "1": "Open Space",
    "2": "Rural Residential",
    "3": "Semi-Rural Residential",
    "4": "Suburban Residential",
    "5": "Urban Residential",
    "6": "Restricted Multiple Unit Residential",
    "7": "Multiple Unit Residential",
    "8": "Mixed Density Residential",
    "9": "Local Serving Commercial",
    "10": "Downtown Commercial",
    "11": "Mixed Use Urban",
    "12": "Regional Serving Commercial",
    "13": "Commercial Light Industrial",
    "CC": "Civic Center",
    "PSF": "Public Safety Facility",
    "PWF": "Public Works Facility",
    "GA": "Other Government Agencies",
    "E": "Elementary School",
    "MS": "Middle School",
    "HS": "High School",
    "N": "Neighborhood Park",
    "C": "Community Park",
    "R": "Regional Park",
    "RAIL": "Trolley Right of Way",
    "FWY": "Freeway",
    "ROAD": "Roadways",
    "T": "Trolley Station",
}


def clean_text(value) -> str | None:
    if value is None:
        return None

    cleaned = str(value).strip()

    if cleaned.upper() in {
        "",
        "-",
        "NULL",
        "NONE",
        "N/A",
        "NA",
    }:
        return None

    return cleaned


def clean_yes_no(value) -> bool | None:
    cleaned = clean_text(value)

    if cleaned is None:
        return None

    normalized = cleaned.upper()

    if normalized == "YES":
        return True

    if normalized == "NO":
        return False

    return None


def get_json(url: str, params: dict) -> dict:
    response = requests.get(
        url,
        params=params,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )

    response.raise_for_status()
    data = response.json()

    if not isinstance(data, dict):
        raise ValueError(
            "ArcGIS returned an invalid response."
        )

    if "error" in data:
        error = data["error"]
        message = error.get(
            "message",
            "ArcGIS returned an error.",
        )
        details = error.get("details", [])

        if details:
            message = (
                f"{message} "
                f"{' '.join(str(item) for item in details)}"
            )

        raise requests.RequestException(message)

    return data


def query_point(
    layer_url: str,
    latitude: float,
    longitude: float,
    out_fields: str = "*",
    distance_feet: int = 0,
) -> list[dict]:
    params = {
        "where": "1=1",
        "geometry": f"{longitude},{latitude}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": out_fields,
        "returnGeometry": "false",
        "f": "json",
    }

    if distance_feet > 0:
        params["distance"] = distance_feet
        params["units"] = "esriSRUnit_Foot"

    data = get_json(
        f"{layer_url.rstrip('/')}/query",
        params=params,
    )

    return data.get("features", [])


def empty_zoning_result(
    status: str,
    message: str,
    special_regulations: str | None = None,
) -> dict:
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
        "special_regulations": special_regulations,
        "ordinance": None,
        "case_number": None,
        "implementation_date": None,
        "jurisdiction": "City of La Mesa",
        "status": status,
        "source": "City of La Mesa Planning & Zoning Public GIS",
        "message": message,
        "lookup_method": None,
        "search_distance_feet": None,
    }


def empty_general_plan_result(
    status: str,
    message: str,
) -> dict:
    return {
        "designation": None,
        "designation_code": None,
        "description": None,
        "raw_density": None,
        "raw_potential_units": None,
        "maximum_density": None,
        "gross_acres_per_unit": None,
        "estimated_maximum_units": None,
        "estimate_status": "not_available",
        "mixed_use": None,
        "mixed_use_name": None,
        "general_plan_code": None,
        "case_number": None,
        "adoption_date": None,
        "jurisdiction": "City of La Mesa",
        "status": status,
        "source": None,
        "message": message,
        "warning": None,
        "lookup_method": None,
        "search_distance_feet": None,
    }


def parse_density_range(
    description: str | None,
) -> tuple[float | None, float | None]:
    cleaned = clean_text(description)

    if cleaned is None:
        return None, None

    normalized = cleaned.upper()

    range_match = re.search(
        r"(\d+(?:\.\d+)?)\s*-\s*"
        r"(\d+(?:\.\d+)?)\s*DU\s*/?\s*ACRE",
        normalized,
    )

    if range_match:
        return (
            float(range_match.group(1)),
            float(range_match.group(2)),
        )

    single_match = re.search(
        r"(\d+(?:\.\d+)?)\s*DU\s*/?\s*ACRE",
        normalized,
    )

    if single_match:
        density = float(single_match.group(1))
        return density, density

    return None, None


def calculate_preliminary_units(
    parcel_acres: float | None,
    maximum_density: float | None,
) -> int | None:
    if (
        parcel_acres is None
        or maximum_density is None
        or parcel_acres <= 0
        or maximum_density <= 0
    ):
        return None

    return max(
        math.floor(parcel_acres * maximum_density),
        0,
    )


def get_specific_plan_name(
    latitude: float,
    longitude: float,
) -> str | None:
    try:
        features = query_point(
            layer_url=CITY_SPECIFIC_PLANS_URL,
            latitude=latitude,
            longitude=longitude,
            out_fields="*",
        )
    except (
        requests.RequestException,
        ValueError,
    ):
        return None

    if not features:
        return None

    attributes = features[0].get(
        "attributes",
        {},
    )

    preferred_fields = [
        "PLAN_NAME",
        "Plan_Name",
        "PLAN",
        "Plan",
        "NAME",
        "Name",
        "SPECIFIC_PLAN",
        "Specific_Plan",
        "SP_NAME",
    ]

    for field in preferred_fields:
        value = attributes.get(field)

        if value:
            return str(value).strip()

    for value in attributes.values():
        if (
            isinstance(value, str)
            and "specific" in value.lower()
        ):
            return value.strip()

    return None


def build_special_regulations(
    attributes: dict,
    fallback_specific_plan_name: str | None,
) -> str | None:
    messages = []

    specific_plan = (
        clean_text(attributes.get("SpecificPlan"))
        or fallback_specific_plan_name
    )

    if specific_plan:
        messages.append(
            f"Specific Plan: {specific_plan}"
        )

    overlay_fields = {
        "URBANDESIG": "Urban Design",
        "SCENICPRES": "Scenic Preservation",
        "NEIGHBOR1": "Neighborhood Overlay 1",
        "NEIGHBOR2": "Neighborhood Overlay 2",
        "MIXEDUSE": "Mixed Use",
        "MOBILEHOME": "Mobile Home",
        "HILLSIDE": "Hillside",
        "GROSSMONT": "Grossmont",
        "FLOODWAY": "Floodway",
        "BRIARTRACT": "Briar Tract",
        "BOWLINGGRE": "Bowling Green",
    }

    active_overlays = []

    for field, label in overlay_fields.items():
        if clean_yes_no(
            attributes.get(field)
        ) is True:
            active_overlays.append(label)

    if active_overlays:
        messages.append(
            "Mapped zoning overlays/flags: "
            + ", ".join(active_overlays)
        )

    split_zone = clean_text(
        attributes.get("SPLIT_ZONE")
    )

    if split_zone:
        messages.append(
            f"Split-zone flag: {split_zone}"
        )

    split_gp = clean_text(
        attributes.get("SPLIT_GP")
    )

    if split_gp:
        messages.append(
            f"Split-General-Plan flag: {split_gp}"
        )

    return (
        "; ".join(messages)
        if messages
        else None
    )


def build_city_zoning_result(
    attributes: dict,
    lookup_method: str,
    search_distance_feet: int,
    fallback_specific_plan_name: str | None,
) -> dict:
    zoning_code = clean_text(
        attributes.get("ZONING")
    )
    zoning_description = clean_text(
        attributes.get("Zone_Descr")
    )
    secondary_zoning = clean_text(
        attributes.get("ZONING2")
    )
    internal_pattern = clean_text(
        attributes.get("PINTERN")
    )

    special_regulations = build_special_regulations(
        attributes=attributes,
        fallback_specific_plan_name=(
            fallback_specific_plan_name
        ),
    )

    message_parts = []

    if (
        secondary_zoning
        and secondary_zoning not in {
            "0",
            zoning_code,
        }
    ):
        message_parts.append(
            f"Secondary zoning value: {secondary_zoning}."
        )

    if internal_pattern:
        message_parts.append(
            "The City GIS also returned internal planning "
            f"pattern code {internal_pattern}. Housing OS "
            "does not yet treat that field as a verified "
            "setback or development-standard schedule."
        )

    message_parts.append(
        "Base zoning was retrieved from the zoning layer used "
        "by the City of La Mesa public Planning & Zoning web map. "
        "Housing OS has not yet decoded the City's complete "
        "development standards, including setbacks, height, "
        "coverage, parking, and other zone-specific requirements."
    )

    return {
        "code": zoning_code,
        "use_regulation": zoning_description,
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
        "special_regulations": special_regulations,
        "ordinance": None,
        "case_number": None,
        "implementation_date": None,
        "jurisdiction": "City of La Mesa",
        "status": "found" if zoning_code else "partial",
        "source": (
            "City of La Mesa Planning & Zoning Public Web Map, "
            "Zoning (AGO) MapServer layer 1"
        ),
        "message": " ".join(message_parts),
        "lookup_method": lookup_method,
        "search_distance_feet": search_distance_feet,
    }


def get_la_mesa_zoning_data(
    latitude: float,
    longitude: float,
) -> dict:
    specific_plan_name = get_specific_plan_name(
        latitude=latitude,
        longitude=longitude,
    )

    out_fields = (
        "ZONING,ZONING2,ZONE_LABEL,Zone_Descr,"
        "PINTERN,SpecificPlan,URBANDESIG,SCENICPRES,"
        "NEIGHBOR1,NEIGHBOR2,MIXEDUSE,MOBILEHOME,"
        "HILLSIDE,GROSSMONT,FLOODWAY,BRIARTRACT,"
        "BOWLINGGRE,SPLIT_ZONE,SPLIT_GP"
    )

    try:
        features = query_point(
            layer_url=CITY_ZONING_URL,
            latitude=latitude,
            longitude=longitude,
            out_fields=out_fields,
        )

        if features:
            return build_city_zoning_result(
                attributes=features[0].get(
                    "attributes",
                    {},
                ),
                lookup_method="exact_point",
                search_distance_feet=0,
                fallback_specific_plan_name=(
                    specific_plan_name
                ),
            )

        nearby_features = query_point(
            layer_url=CITY_ZONING_URL,
            latitude=latitude,
            longitude=longitude,
            out_fields=out_fields,
            distance_feet=25,
        )

        if nearby_features:
            return build_city_zoning_result(
                attributes=nearby_features[0].get(
                    "attributes",
                    {},
                ),
                lookup_method="nearby_search",
                search_distance_feet=25,
                fallback_specific_plan_name=(
                    specific_plan_name
                ),
            )

        return empty_zoning_result(
            status="not_found",
            special_regulations=(
                f"Mapped Specific Plan area: {specific_plan_name}"
                if specific_plan_name
                else None
            ),
            message=(
                "The City of La Mesa public zoning layer "
                "returned no zoning polygon at or within "
                "25 feet of the property point."
            ),
        )

    except requests.Timeout:
        return empty_zoning_result(
            status="timeout",
            special_regulations=(
                f"Mapped Specific Plan area: {specific_plan_name}"
                if specific_plan_name
                else None
            ),
            message=(
                "The City of La Mesa zoning service took "
                "too long to respond."
            ),
        )

    except (
        requests.RequestException,
        ValueError,
    ) as error:
        return empty_zoning_result(
            status="error",
            special_regulations=(
                f"Mapped Specific Plan area: {specific_plan_name}"
                if specific_plan_name
                else None
            ),
            message=(
                "The City of La Mesa zoning service could "
                f"not be queried: {error}"
            ),
        )


def build_city_general_plan_result(
    attributes: dict,
    lookup_method: str,
    search_distance_feet: int,
    parcel_acres: float | None,
) -> dict:
    code = clean_text(
        attributes.get("GPLABEL")
    )
    raw_description = clean_text(
        attributes.get("DESCR")
    )
    description = (
        raw_description
        or GENERAL_PLAN_NAMES.get(code)
    )
    designation = (
        GENERAL_PLAN_NAMES.get(code)
        or description
        or code
    )

    minimum_density, maximum_density = (
        parse_density_range(description)
    )
    estimated_units = calculate_preliminary_units(
        parcel_acres=parcel_acres,
        maximum_density=maximum_density,
    )

    existing_dwelling_units = attributes.get(
        "DWELLUNITS"
    )
    specific_plan = clean_text(
        attributes.get("SpecificPlan")
    )
    mixed_use_flag = clean_yes_no(
        attributes.get("MIXEDUSE")
    )

    if mixed_use_flag is not None:
        mixed_use_bool = mixed_use_flag
    elif code is not None:
        mixed_use_bool = code in {"8", "11"}
    else:
        mixed_use_bool = None

    mixed_use = (
        "YES"
        if mixed_use_bool is True
        else (
            "NO"
            if mixed_use_bool is False
            else None
        )
    )

    density_text = None

    if (
        minimum_density is not None
        and maximum_density is not None
    ):
        if minimum_density == maximum_density:
            density_text = (
                f"{maximum_density:g} dwelling units per acre"
            )
        else:
            density_text = (
                f"{minimum_density:g}-{maximum_density:g} "
                "dwelling units per acre"
            )

    estimate_status = (
        "preliminary_gross_density_estimate"
        if estimated_units is not None
        else "planning_designation_found"
    )

    warning_parts = [
        (
            "This General Plan result comes from the same "
            "City of La Mesa zoning/land-use layer used by the "
            "public Planning & Zoning web map."
        )
    ]

    if estimated_units is not None:
        warning_parts.append(
            "The unit count is a preliminary gross-density "
            "screen calculated from parcel acreage and the "
            "maximum density parsed from the mapped General "
            "Plan description. It is not an entitlement "
            "determination and does not account for zoning "
            "development standards, lot configuration, parking, "
            "Specific Plans, overlays, state housing law, or "
            "other project requirements."
        )
    else:
        warning_parts.append(
            "A parcel-level unit estimate was not calculated "
            "because the mapped General Plan description did "
            "not provide a density that Housing OS could "
            "reliably parse."
        )

    if specific_plan:
        warning_parts.append(
            f"The GIS identifies Specific Plan: {specific_plan}. "
            "Specific Plan requirements must be reviewed before "
            "relying on the density screen."
        )

    return {
        "designation": designation,
        "designation_code": code,
        "description": description,
        "raw_density": density_text,
        "raw_potential_units": (
            parcel_acres * maximum_density
            if (
                parcel_acres is not None
                and maximum_density is not None
            )
            else None
        ),
        "maximum_density": maximum_density,
        "gross_acres_per_unit": (
            1 / maximum_density
            if (
                maximum_density is not None
                and maximum_density > 0
            )
            else None
        ),
        "estimated_maximum_units": estimated_units,
        "estimate_status": estimate_status,
        "mixed_use": mixed_use,
        "mixed_use_name": (
            designation
            if mixed_use_bool is True
            else None
        ),
        "general_plan_code": code,
        "case_number": None,
        "adoption_date": None,
        "jurisdiction": "City of La Mesa",
        "status": "found",
        "source": (
            "City of La Mesa Planning & Zoning Public Web Map, "
            "Zoning (AGO) MapServer layer 1"
        ),
        "message": (
            f"Existing dwelling-unit field in City GIS: "
            f"{existing_dwelling_units}."
            if existing_dwelling_units is not None
            else None
        ),
        "warning": " ".join(warning_parts),
        "lookup_method": lookup_method,
        "search_distance_feet": search_distance_feet,
    }


def build_sandag_fallback_result(
    attributes: dict,
) -> dict:
    planned_land_use = attributes.get("plannedlu")
    plu = attributes.get("plu")

    description = (
        str(planned_land_use).strip()
        if planned_land_use
        else None
    )
    code = (
        str(plu)
        if plu is not None
        else None
    )

    return {
        "designation": description,
        "designation_code": code,
        "description": description,
        "raw_density": None,
        "raw_potential_units": None,
        "maximum_density": None,
        "gross_acres_per_unit": None,
        "estimated_maximum_units": None,
        "estimate_status": "regional_fallback_only",
        "mixed_use": None,
        "mixed_use_name": None,
        "general_plan_code": code,
        "case_number": None,
        "adoption_date": None,
        "jurisdiction": "City of La Mesa",
        "status": "found",
        "source": (
            "SANDAG Landuse Forecast 2050 regional "
            "planned-land-use crosswalk"
        ),
        "message": (
            "The City of La Mesa public Planning & Zoning "
            "service could not provide a usable General Plan "
            "result, so Housing OS used SANDAG's regional "
            "planned-land-use crosswalk as a screening fallback."
        ),
        "warning": (
            "This SANDAG designation is descriptive regional "
            "screening data and is not the controlling City of "
            "La Mesa General Plan determination. Confirm the "
            "official designation with the City before relying "
            "on it for entitlement or unit calculations."
        ),
        "lookup_method": "exact_point_regional_fallback",
        "search_distance_feet": 0,
    }


def get_la_mesa_general_plan_data(
    latitude: float,
    longitude: float,
    parcel_acres: float | None = None,
) -> dict:
    city_error = None
    out_fields = (
        "GPLABEL,DESCR,DWELLUNITS,MIXEDUSE,"
        "SpecificPlan,SPLIT_GP,ZONEGPEQ"
    )

    try:
        features = query_point(
            layer_url=CITY_ZONING_URL,
            latitude=latitude,
            longitude=longitude,
            out_fields=out_fields,
        )

        if features:
            return build_city_general_plan_result(
                attributes=features[0].get(
                    "attributes",
                    {},
                ),
                lookup_method="exact_point",
                search_distance_feet=0,
                parcel_acres=parcel_acres,
            )

        nearby_features = query_point(
            layer_url=CITY_ZONING_URL,
            latitude=latitude,
            longitude=longitude,
            out_fields=out_fields,
            distance_feet=25,
        )

        if nearby_features:
            return build_city_general_plan_result(
                attributes=nearby_features[0].get(
                    "attributes",
                    {},
                ),
                lookup_method="nearby_search",
                search_distance_feet=25,
                parcel_acres=parcel_acres,
            )

    except requests.Timeout:
        city_error = (
            "City of La Mesa Planning & Zoning GIS timed out."
        )

    except (
        requests.RequestException,
        ValueError,
    ) as error:
        city_error = str(error)

    try:
        fallback_features = query_point(
            layer_url=SANDAG_PLANNED_LAND_USE_URL,
            latitude=latitude,
            longitude=longitude,
            out_fields="plu,plannedlu",
        )

    except requests.Timeout:
        return empty_general_plan_result(
            status="timeout",
            message=(
                "Both the City of La Mesa planning layer "
                "and the SANDAG regional fallback were unavailable."
            ),
        )

    except (
        requests.RequestException,
        ValueError,
    ) as error:
        return empty_general_plan_result(
            status="error",
            message=(
                "City of La Mesa planning data was unavailable"
                + (
                    f" ({city_error})"
                    if city_error
                    else ""
                )
                + ". The SANDAG fallback also failed: "
                + str(error)
            ),
        )

    if fallback_features:
        return build_sandag_fallback_result(
            attributes=fallback_features[0].get(
                "attributes",
                {},
            )
        )

    return empty_general_plan_result(
        status="not_found",
        message=(
            "No City of La Mesa General Plan polygon or "
            "SANDAG regional planned-land-use polygon was "
            "found at this location."
        ),
    )