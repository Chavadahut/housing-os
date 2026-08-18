import math
import re
import requests

from datetime import datetime, timezone
from pyproj import Transformer


URL = (
    "https://gis-public.sandiegocounty.gov/arcgis/rest/services/"
    "DPLU/DPLU_Map/MapServer/11/query"
)

transformer = Transformer.from_crs(
    "EPSG:4326",
    "EPSG:2230",
    always_xy=True
)


GENERAL_PLAN_CODE_MAP = {
    1: "VR-30",
    2: "VR-24",
    40: "VR-20",
    3: "VR-15",
    4: "VR-10.9",
    5: "VR-7.3",
    6: "VR-4.3",
    7: "VR-2.9",
    8: "VR-2",
    41: "SR-0.5",
    9: "SR-1",
    11: "SR-2",
    13: "SR-4",
    17: "SR-10",
    18: "RL-20",
    19: "RL-40",
    20: "RL-80"
}


def format_arcgis_date(value):

    if value is None:
        return None

    try:
        date = datetime.fromtimestamp(
            value / 1000,
            tz=timezone.utc
        )

        return date.date().isoformat()

    except (TypeError, ValueError, OSError):
        return value


def extract_designation_code(
    designation: str | None
) -> str | None:

    if not designation:
        return None

    normalized = designation.upper()

    match = re.search(
        r"\b(VR|SR|RL)-(\d*\.?\d+)\b",
        normalized
    )

    if not match:
        return None

    prefix = match.group(1)
    value = match.group(2)

    if value.startswith("."):
        value = f"0{value}"

    return f"{prefix}-{value}"


def code_from_general_plan_value(
    general_plan_code
) -> str | None:

    if general_plan_code is None:
        return None

    try:
        numeric_code = int(
            float(general_plan_code)
        )

    except (TypeError, ValueError):
        return None

    return GENERAL_PLAN_CODE_MAP.get(
        numeric_code
    )


def interpret_general_plan(
    designation: str | None,
    parcel_acres: float | None,
    general_plan_code=None,
    raw_density=None,
    raw_potential_units=None
) -> dict:

    designation_code = (
        extract_designation_code(
            designation
        )
        or code_from_general_plan_value(
            general_plan_code
        )
    )

    result = {
        "designation_code": designation_code,
        "maximum_density": None,
        "gross_acres_per_unit": None,
        "estimated_maximum_units": None,
        "estimate_status": "not_available",
        "warning": (
            "Actual development potential depends on zoning, "
            "parcel configuration, legal lot status, access, "
            "utilities, septic or sewer, environmental "
            "constraints, and agency review."
        )
    }

    # GPCODE95 = 22 means Specific Plan Area in the County layer.
    # In that case SPA_DENSIT is an overall Specific Plan density,
    # not a parcel-level entitlement. Preserve the density information
    # but do not manufacture a parcel-level unit count from it.
    try:
        gp_numeric_code = int(
            float(general_plan_code)
        ) if general_plan_code is not None else None

    except (TypeError, ValueError):
        gp_numeric_code = None

    if gp_numeric_code == 22:

        try:
            specific_plan_density = float(
                raw_density
            )

        except (TypeError, ValueError):
            specific_plan_density = None

        if (
            specific_plan_density is not None
            and specific_plan_density > 0
        ):

            result["maximum_density"] = (
                f"{specific_plan_density:g} dwelling units per acre "
                "across the Specific Plan Area"
            )

        result["estimate_status"] = (
            "specific_plan_review_required"
        )

        result["warning"] = (
            "This parcel is within a County Specific Plan Area. "
            "The GIS density is an overall Specific Plan density "
            "and should not be multiplied by this individual parcel "
            "to claim a parcel-level unit entitlement. Review the "
            "applicable Specific Plan, subdivision history, legal lot "
            "status, zoning, and prior approvals before estimating "
            "additional dwelling-unit potential."
        )

        return result

    if not designation_code:
        return result

    try:
        numeric_value = float(
            designation_code.split("-")[1]
        )

    except (IndexError, TypeError, ValueError):
        return result

    if numeric_value <= 0:
        return result

    if designation_code.startswith("VR-"):

        units_per_acre = numeric_value

        result["maximum_density"] = (
            f"{units_per_acre:g} dwelling units per gross acre"
        )

        if parcel_acres is not None:

            try:
                parcel_acres = float(
                    parcel_acres
                )

                raw_unit_math = (
                    parcel_acres
                    * units_per_acre
                )

                calculated_units = math.floor(
                    raw_unit_math
                )

                if (
                    calculated_units < 1
                    and parcel_acres > 0
                ):
                    result["estimated_maximum_units"] = 1
                    result["estimate_status"] = (
                        "preliminary_existing_legal_lot_assumption"
                    )
                    result["warning"] = (
                        "The General Plan density math is below one "
                        "whole dwelling unit for this parcel. Housing "
                        "OS displays one unit as a preliminary legal-lot "
                        "screening assumption because fractional units "
                        "are not meaningful at the parcel level. This "
                        "does not confirm that one dwelling is legally "
                        "permitted or that additional units are allowed."
                    )

                else:
                    result["estimated_maximum_units"] = (
                        calculated_units
                    )
                    result["estimate_status"] = "preliminary"

            except (TypeError, ValueError):
                pass

    elif designation_code.startswith(
        ("SR-", "RL-")
    ):

        acres_per_unit = numeric_value

        result["gross_acres_per_unit"] = (
            acres_per_unit
        )

        result["maximum_density"] = (
            f"1 dwelling unit per "
            f"{acres_per_unit:g} gross acres"
        )

        if parcel_acres is not None:

            try:
                parcel_acres = float(
                    parcel_acres
                )

                calculated_units = math.floor(
                    parcel_acres
                    / acres_per_unit
                )

                if (
                    calculated_units < 1
                    and parcel_acres > 0
                ):
                    result["estimated_maximum_units"] = 1
                    result["estimate_status"] = (
                        "preliminary_existing_legal_lot_assumption"
                    )
                    result["warning"] = (
                        "The General Plan gross-density math is below "
                        "one whole dwelling unit for this parcel. "
                        "Housing OS displays one unit only as a "
                        "preliminary legal-lot screening assumption. "
                        "This does not confirm legal development rights."
                    )

                else:
                    result["estimated_maximum_units"] = (
                        calculated_units
                    )
                    result["estimate_status"] = "preliminary"

            except (TypeError, ValueError):
                pass

    if (
        result["estimated_maximum_units"] is None
        and raw_potential_units is not None
    ):

        try:
            raw_units = float(
                raw_potential_units
            )

            if raw_units > 0:

                result["estimated_maximum_units"] = max(
                    1,
                    math.floor(raw_units)
                )

                result["estimate_status"] = (
                    "preliminary_from_county_attribute"
                )

        except (TypeError, ValueError):
            pass

    if (
        result["maximum_density"] is None
        and raw_density is not None
    ):

        try:
            numeric_density = float(
                raw_density
            )

            if numeric_density > 0:

                result["maximum_density"] = (
                    f"County GIS density attribute: "
                    f"{numeric_density:g}"
                )

        except (TypeError, ValueError):
            pass

    return result


def empty_general_plan_result(
    status: str,
    message: str
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
        "jurisdiction": "Unincorporated San Diego County",
        "status": status,
        "source": "County of San Diego General Plan",
        "message": message,
        "warning": None,
        "lookup_method": None,
        "search_distance_feet": None
    }


def query_general_plan(
    latitude: float,
    longitude: float,
    search_distance: int = 0
):

    x, y = transformer.transform(
        longitude,
        latitude
    )

    params = {
        "where": "1=1",
        "geometry": f"{x},{y}",
        "geometryType": "esriGeometryPoint",
        "inSR": "2230",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": (
            "SPA_NAME,SPA_DENSIT,SPA_UNITS,"
            "MUNAME,MIXED_USE,GPCODE95,"
            "DESCRIPTION,ADOPT_DATE,CASE_NO"
        ),
        "returnGeometry": "false",
        "f": "json"
    }

    if search_distance > 0:

        params["distance"] = search_distance
        params["units"] = "esriSRUnit_Foot"

    response = requests.get(
        URL,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    if "error" in data:

        error_details = data["error"]

        message = error_details.get(
            "message",
            "The General Plan service returned an error."
        )

        details = error_details.get(
            "details",
            []
        )

        if details:

            message = (
                f"{message} "
                f"{' '.join(str(item) for item in details)}"
            )

        raise requests.RequestException(
            message
        )

    return data.get(
        "features",
        []
    )


def get_county_general_plan_data(
    latitude: float,
    longitude: float,
    parcel_acres: float | None = None
) -> dict:

    try:

        features = query_general_plan(
            latitude=latitude,
            longitude=longitude
        )

        lookup_method = "exact_point"
        search_distance = 0

        if not features:

            features = query_general_plan(
                latitude=latitude,
                longitude=longitude,
                search_distance=100
            )

            lookup_method = "nearby_search"
            search_distance = 100

    except requests.Timeout:

        return empty_general_plan_result(
            status="timeout",
            message=(
                "The General Plan server took too long "
                "to respond. Please try again."
            )
        )

    except requests.RequestException as error:

        return empty_general_plan_result(
            status="error",
            message=str(error)
        )

    except ValueError:

        return empty_general_plan_result(
            status="error",
            message=(
                "The General Plan server returned "
                "an invalid response."
            )
        )

    if not features:

        return empty_general_plan_result(
            status="not_found",
            message=(
                "No County General Plan designation was "
                "found at or within 100 feet of this location."
            )
        )

    attributes = features[0].get(
        "attributes",
        {}
    )

    raw_spa_name = attributes.get(
        "SPA_NAME"
    )

    description = attributes.get(
        "DESCRIPTION"
    )

    general_plan_code = attributes.get(
        "GPCODE95"
    )

    try:
        numeric_general_plan_code = int(
            float(general_plan_code)
        ) if general_plan_code is not None else None

    except (TypeError, ValueError):
        numeric_general_plan_code = None

    if numeric_general_plan_code == 22:

        cleaned_spa_name = (
            str(raw_spa_name).strip()
            if raw_spa_name
            else None
        )

        designation = (
            f"{cleaned_spa_name} (Specific Plan Area)"
            if cleaned_spa_name
            else "Specific Plan Area"
        )

    else:

        designation = (
            raw_spa_name
            or description
        )

    interpretation = interpret_general_plan(
        designation=designation,
        parcel_acres=parcel_acres,
        general_plan_code=general_plan_code,
        raw_density=attributes.get(
            "SPA_DENSIT"
        ),
        raw_potential_units=attributes.get(
            "SPA_UNITS"
        )
    )

    designation_code = interpretation[
        "designation_code"
    ]

    if (
        designation
        and designation_code
        and designation_code not in designation.upper()
    ):

        designation = (
            f"{designation} ({designation_code})"
        )

    return {
        "designation": designation,
        "designation_code": designation_code,
        "description": description,
        "raw_density": attributes.get(
            "SPA_DENSIT"
        ),
        "raw_potential_units": attributes.get(
            "SPA_UNITS"
        ),
        "maximum_density": interpretation[
            "maximum_density"
        ],
        "gross_acres_per_unit": interpretation[
            "gross_acres_per_unit"
        ],
        "estimated_maximum_units": interpretation[
            "estimated_maximum_units"
        ],
        "estimate_status": interpretation[
            "estimate_status"
        ],
        "mixed_use": attributes.get(
            "MIXED_USE"
        ),
        "mixed_use_name": attributes.get(
            "MUNAME"
        ),
        "general_plan_code": general_plan_code,
        "case_number": attributes.get(
            "CASE_NO"
        ),
        "adoption_date": format_arcgis_date(
            attributes.get(
                "ADOPT_DATE"
            )
        ),
        "jurisdiction": (
            "Unincorporated San Diego County"
        ),
        "status": "found",
        "source": "County of San Diego General Plan",
        "message": None,
        "warning": interpretation[
            "warning"
        ],
        "lookup_method": lookup_method,
        "search_distance_feet": search_distance
    }