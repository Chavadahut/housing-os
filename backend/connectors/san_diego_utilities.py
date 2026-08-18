import requests

from pyproj import Transformer


WATER_DISTRICT_URL = (
    "https://gis-public.sandiegocounty.gov/arcgis/rest/services/"
    "HCD/HCD_Map/FeatureServer/16/query"
)

SANITATION_DISTRICT_URL = (
    "https://gis-public.sandiegocounty.gov/arcgis/rest/services/"
    "HCD/HCD_Map/FeatureServer/17/query"
)

WASTEWATER_PERMIT_URL = (
    "https://gis-public.sandiegocounty.gov/arcgis/rest/services/"
    "DPW/WASTEWATER/FeatureServer/33/query"
)


transformer = Transformer.from_crs(
    "EPSG:4326",
    "EPSG:2230",
    always_xy=True
)


def clean_text(value) -> str | None:

    if not isinstance(value, str):
        return None

    cleaned = value.strip()

    if cleaned in {
        "",
        "-",
        "NULL",
        "NONE",
        "N/A"
    }:
        return None

    return cleaned


def empty_utility_result(
    status: str,
    message: str
) -> dict:

    return {
        "water_district": None,
        "water_district_fund": None,
        "inside_water_district": None,
        "sanitation_district": None,
        "sanitation_district_fund": None,
        "inside_sanitation_district": None,
        "county_wastewater_permit_found": None,
        "wastewater_permits": [],
        "sewer_screening": None,
        "septic_screening": None,
        "constraint_level": None,
        "development_warning": None,
        "status": status,
        "source": (
            "County of San Diego Water District, "
            "Sanitation District, and Wastewater Layers"
        ),
        "message": message,
        "analysis_scope": "preliminary_utility_screening"
    }


def query_district(
    url: str,
    latitude: float,
    longitude: float
) -> dict | None:

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
        "outFields": "DISTRICT,FUND",
        "returnGeometry": "false",
        "f": "json"
    }

    response = requests.get(
        url,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    if "error" in data:

        error_details = data["error"]

        message = error_details.get(
            "message",
            "The utility district service returned an error."
        )

        details = error_details.get(
            "details",
            []
        )

        if details:
            message = f"{message} {' '.join(details)}"

        raise requests.RequestException(
            message
        )

    features = data.get(
        "features",
        []
    )

    if not features:
        return None

    return features[0].get(
        "attributes",
        {}
    )


def query_wastewater_permits(
    apn: str
) -> list[str]:

    if not apn:
        return []

    escaped_apn = apn.replace(
        "'",
        "''"
    )

    params = {
        "where": f"APN = '{escaped_apn}'",
        "outFields": (
            "APN,PERMIT_CURRENT,PERMIT_1,"
            "PERMIT_2,PERMIT_3,PERMIT_4,"
            "PERMIT_5,PERMIT_6,PERMIT_7,"
            "PERMIT_8"
        ),
        "returnGeometry": "false",
        "f": "json"
    }

    response = requests.get(
        WASTEWATER_PERMIT_URL,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    if "error" in data:

        error_details = data["error"]

        message = error_details.get(
            "message",
            "The wastewater permit service returned an error."
        )

        details = error_details.get(
            "details",
            []
        )

        if details:
            message = f"{message} {' '.join(details)}"

        raise requests.RequestException(
            message
        )

    features = data.get(
        "features",
        []
    )

    permits = []

    permit_fields = [
        "PERMIT_CURRENT",
        "PERMIT_1",
        "PERMIT_2",
        "PERMIT_3",
        "PERMIT_4",
        "PERMIT_5",
        "PERMIT_6",
        "PERMIT_7",
        "PERMIT_8"
    ]

    for feature in features:

        attributes = feature.get(
            "attributes",
            {}
        )

        for field in permit_fields:

            permit_value = clean_text(
                attributes.get(field)
            )

            if (
                permit_value
                and permit_value not in permits
            ):
                permits.append(
                    permit_value
                )

    return permits


def interpret_utility_screening(
    water_district: str | None,
    sanitation_district: str | None,
    permits: list[str]
) -> dict:

    inside_water_district = (
        water_district is not None
    )

    inside_sanitation_district = (
        sanitation_district is not None
    )

    permit_found = len(permits) > 0

    if inside_sanitation_district and permit_found:

        sewer_screening = (
            "The parcel point is inside a mapped sanitation "
            "district and County wastewater permit records "
            "were found for the APN."
        )

        septic_screening = (
            "Septic may not be the primary wastewater option, "
            "but sewer connection capacity and permit status "
            "must still be confirmed."
        )

        constraint_level = "low"

        warning = (
            "Mapped district coverage and wastewater permit "
            "records do not guarantee an available sewer "
            "connection, capacity, lateral, or right to connect."
        )

    elif inside_sanitation_district:

        sewer_screening = (
            "The parcel point is inside a mapped sanitation "
            "district, but no County wastewater permit record "
            "was found for the APN."
        )

        septic_screening = (
            "Confirm whether sewer service is available. "
            "Do not assume septic is permitted or necessary "
            "based only on this screening."
        )

        constraint_level = "unknown"

        warning = (
            "The parcel may be within a sanitation district, "
            "but sewer availability, capacity, connection fees, "
            "and lateral location remain unconfirmed."
        )

    elif permit_found:

        sewer_screening = (
            "County wastewater permit records were found, "
            "but the parcel point was not inside the mapped "
            "sanitation-district polygon."
        )

        septic_screening = (
            "The conflicting screening results require direct "
            "confirmation with the wastewater agency."
        )

        constraint_level = "unknown"

        warning = (
            "Wastewater permit records and mapped district "
            "coverage do not fully agree. Agency confirmation "
            "is required."
        )

    else:

        sewer_screening = (
            "The parcel point was not identified inside a mapped "
            "sanitation district, and no County wastewater permit "
            "record was found for the APN."
        )

        septic_screening = (
            "The project may need an onsite wastewater or septic "
            "system, subject to soils, percolation testing, reserve "
            "area, setbacks, groundwater, and County approval."
        )

        constraint_level = "moderate"

        warning = (
            "This result does not prove that sewer is unavailable "
            "or that septic is feasible. Both must be confirmed "
            "before development planning."
        )

    if inside_water_district:

        water_message = (
            f"The parcel point is inside the mapped "
            f"{water_district} water district."
        )

    else:

        water_message = (
            "The parcel point was not identified inside a mapped "
            "water district. A private well or another water source "
            "may need to be investigated."
        )

        if constraint_level == "low":
            constraint_level = "moderate"

    return {
        "inside_water_district": inside_water_district,
        "inside_sanitation_district": inside_sanitation_district,
        "permit_found": permit_found,
        "water_screening": water_message,
        "sewer_screening": sewer_screening,
        "septic_screening": septic_screening,
        "constraint_level": constraint_level,
        "development_warning": warning
    }


def get_utility_data(
    latitude: float,
    longitude: float,
    apn: str | None
) -> dict:

    try:

        water_attributes = query_district(
            url=WATER_DISTRICT_URL,
            latitude=latitude,
            longitude=longitude
        )

        sanitation_attributes = query_district(
            url=SANITATION_DISTRICT_URL,
            latitude=latitude,
            longitude=longitude
        )

        permits = query_wastewater_permits(
            apn=apn or ""
        )

    except requests.Timeout:

        return empty_utility_result(
            status="timeout",
            message=(
                "A utility GIS server took too long "
                "to respond. Please try again."
            )
        )

    except requests.RequestException as error:

        return empty_utility_result(
            status="error",
            message=str(error)
        )

    except ValueError:

        return empty_utility_result(
            status="error",
            message=(
                "A utility GIS server returned "
                "an invalid response."
            )
        )

    water_district = None
    water_fund = None

    if water_attributes:

        water_district = clean_text(
            water_attributes.get("DISTRICT")
        )

        water_fund = water_attributes.get(
            "FUND"
        )

    sanitation_district = None
    sanitation_fund = None

    if sanitation_attributes:

        sanitation_district = clean_text(
            sanitation_attributes.get("DISTRICT")
        )

        sanitation_fund = sanitation_attributes.get(
            "FUND"
        )

    interpretation = interpret_utility_screening(
        water_district=water_district,
        sanitation_district=sanitation_district,
        permits=permits
    )

    return {
        "water_district": water_district,
        "water_district_fund": water_fund,
        "inside_water_district": interpretation[
            "inside_water_district"
        ],
        "water_screening": interpretation[
            "water_screening"
        ],
        "sanitation_district": sanitation_district,
        "sanitation_district_fund": sanitation_fund,
        "inside_sanitation_district": interpretation[
            "inside_sanitation_district"
        ],
        "county_wastewater_permit_found": interpretation[
            "permit_found"
        ],
        "wastewater_permits": permits,
        "sewer_screening": interpretation[
            "sewer_screening"
        ],
        "septic_screening": interpretation[
            "septic_screening"
        ],
        "constraint_level": interpretation[
            "constraint_level"
        ],
        "development_warning": interpretation[
            "development_warning"
        ],
        "status": "found",
        "source": (
            "County of San Diego Water District, "
            "Sanitation District, and Wastewater Layers"
        ),
        "message": (
            "This is a preliminary utility screening. District "
            "coverage does not guarantee service, capacity, "
            "connection rights, permits, or septic feasibility."
        ),
        "analysis_scope": "preliminary_utility_screening"
    }