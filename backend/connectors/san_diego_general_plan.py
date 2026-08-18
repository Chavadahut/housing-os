import requests

from pyproj import Transformer


URL = (
    "https://webmaps.sandiego.gov/arcgis/rest/services/"
    "Planning/PLN_LongRangePlanning/MapServer/24/query"
)

# GPS coordinates to San Diego State Plane coordinates.
# Same transform used by connectors/san_diego_zoning.py, kept consistent
# so both connectors agree on how a lat/lon becomes a query point.
transformer = Transformer.from_crs(
    "EPSG:4326",
    "EPSG:2230",
    always_xy=True
)


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
            "GP_LU_DESC,Density_Low,Density_Hi,"
            "Density_Bonus,plan_name,plan_desc,area_name"
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
        error_message = data["error"].get(
            "message",
            "The General Plan GIS returned an error."
        )

        raise requests.RequestException(error_message)

    return data.get("features", [])


def _round_or_none(value, digits=2):

    if value is None:
        return None

    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def get_san_diego_general_plan_data(
    latitude: float,
    longitude: float,
    parcel_acres: float | None = None
):
    """
    General Plan / Community Plan Land Use lookup for City of San Diego.

    Matches the same response shape used by unsupported_general_plan_result()
    in services.py and by the City of La Mesa general-plan connector, so
    downstream code (feasibility_summary, development_scenario) does not
    need special-casing per jurisdiction.
    """

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
            "jurisdiction": "City of San Diego",
            "status": "timeout",
            "source": (
                "City of San Diego General Plan / "
                "Community Plan Land Use Map"
            ),
            "message": (
                "The City of San Diego General Plan server took too "
                "long to respond. Please try again."
            ),
            "warning": None,
            "lookup_method": None,
            "search_distance_feet": None
        }

    except requests.RequestException as error:
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
            "jurisdiction": "City of San Diego",
            "status": "error",
            "source": (
                "City of San Diego General Plan / "
                "Community Plan Land Use Map"
            ),
            "message": str(error),
            "warning": None,
            "lookup_method": None,
            "search_distance_feet": None
        }

    except ValueError:
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
            "jurisdiction": "City of San Diego",
            "status": "error",
            "source": (
                "City of San Diego General Plan / "
                "Community Plan Land Use Map"
            ),
            "message": (
                "The General Plan server returned an invalid response."
            ),
            "warning": None,
            "lookup_method": None,
            "search_distance_feet": None
        }

    if not features:
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
            "jurisdiction": None,
            "status": "not_found",
            "source": (
                "City of San Diego General Plan / "
                "Community Plan Land Use Map"
            ),
            "message": (
                "No City of San Diego General Plan designation was "
                "found at or within 100 feet of this location."
            ),
            "warning": None,
            "lookup_method": None,
            "search_distance_feet": None
        }

    attributes = features[0].get("attributes", {})

    designation = attributes.get("GP_LU_DESC")
    plan_name = attributes.get("plan_name")
    plan_desc = attributes.get("plan_desc")
    area_name = attributes.get("area_name")

    density_low = _round_or_none(attributes.get("Density_Low"))
    density_high = _round_or_none(attributes.get("Density_Hi"))
    density_bonus = _round_or_none(attributes.get("Density_Bonus"))

    description = None

    if plan_desc:
        description = plan_desc
    elif plan_name or area_name:
        description = " / ".join(
            value
            for value in [plan_name, area_name]
            if value
        )

    gross_acres_per_unit = None

    if density_high and density_high > 0:
        gross_acres_per_unit = round(1 / density_high, 4)

    estimated_maximum_units = None
    estimate_status = "not_available"

    if (
        parcel_acres is not None
        and density_high is not None
        and density_high > 0
    ):
        estimated_maximum_units = round(
            parcel_acres * density_high
        )
        estimate_status = "preliminary"
    elif designation:
        estimate_status = "planning_designation_found"

    mixed_use = "YES" if designation == "Multiple Use" else "NO"

    return {
        "designation": designation,
        "designation_code": None,
        "description": description,
        "raw_density": density_low,
        "raw_potential_units": None,
        "maximum_density": density_high,
        "gross_acres_per_unit": gross_acres_per_unit,
        "estimated_maximum_units": estimated_maximum_units,
        "estimate_status": estimate_status,
        "mixed_use": mixed_use,
        "mixed_use_name": plan_name,
        "general_plan_code": None,
        "case_number": None,
        "adoption_date": None,
        "jurisdiction": "City of San Diego",
        "status": "found",
        "source": (
            "City of San Diego General Plan / "
            "Community Plan Land Use Map"
        ),
        "message": None,
        "warning": (
            "This is the illustrative Community Plan land-use "
            "designation, not a parcel-specific zoning determination. "
            "Refer to the adopted Community Plan and current zoning "
            "for the applicable development regulations. Density "
            "figures reflect the mapped Community Plan range and may "
            "not reflect bonus density, overlay zones, or subsequent "
            "amendments."
        ),
        "lookup_method": lookup_method,
        "search_distance_feet": search_distance,
        "density_bonus": density_bonus
    }