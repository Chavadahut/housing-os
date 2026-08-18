import requests
from datetime import datetime, timezone

from pyproj import Transformer


URL = (
    "https://gis-public.sandiegocounty.gov/arcgis/rest/services/"
    "sdep_warehouse/ZONING_CN/FeatureServer/0/query"
)

# GPS coordinates to San Diego County State Plane coordinates
transformer = Transformer.from_crs(
    "EPSG:4326",
    "EPSG:2230",
    always_xy=True
)


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


def empty_zoning_result(
    status: str,
    message: str
):

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
        "jurisdiction": "Unincorporated San Diego County",
        "status": status,
        "source": "County of San Diego Official Zoning Layer",
        "message": message,
        "lookup_method": None,
        "search_distance_feet": None
    }


def query_county_zoning(
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
            "USEREG,ANIMALREGS,DENSITY,LOT,BUILDTYPE,"
            "MAXFLR,FLRAREARATIO,HEIGHT,COVERAGE,"
            "SETBACK,OPENSPACE,SPECIALREGS,USEREGS,"
            "ADOPTDATE,CASE_NO,ORDINANCE_NO,LEGEND"
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
            "The County zoning GIS returned an error."
        )

        details = error_details.get("details", [])

        if details:
            message = f"{message} {' '.join(details)}"

        raise requests.RequestException(message)

    return data.get("features", [])


def get_county_zoning_data(
    latitude: float,
    longitude: float
):

    try:
        features = query_county_zoning(
            latitude=latitude,
            longitude=longitude
        )

        lookup_method = "exact_point"
        search_distance = 0

        if not features:
            features = query_county_zoning(
                latitude=latitude,
                longitude=longitude,
                search_distance=100
            )

            lookup_method = "nearby_search"
            search_distance = 100

    except requests.Timeout:
        return empty_zoning_result(
            status="timeout",
            message=(
                "The County zoning server took too long "
                "to respond. Please try again."
            )
        )

    except requests.RequestException as error:
        return empty_zoning_result(
            status="error",
            message=str(error)
        )

    except ValueError:
        return empty_zoning_result(
            status="error",
            message=(
                "The County zoning server returned "
                "an invalid response."
            )
        )

    if not features:
        return empty_zoning_result(
            status="not_found",
            message=(
                "No County zoning was found at or "
                "within 100 feet of this location."
            )
        )

    attributes = features[0].get("attributes", {})

    use_regulation = attributes.get("USEREG")
    zoning_legend = attributes.get("LEGEND")

    if use_regulation and zoning_legend:
        zoning_code = f"{use_regulation} - {zoning_legend}"
    else:
        zoning_code = use_regulation or zoning_legend

    return {
        "code": zoning_code,
        "use_regulation": use_regulation,
        "density": attributes.get("DENSITY"),
        "minimum_lot_size": attributes.get("LOT"),
        "building_type": attributes.get("BUILDTYPE"),
        "maximum_floor_area": attributes.get("MAXFLR"),
        "floor_area_ratio": attributes.get("FLRAREARATIO"),
        "height": attributes.get("HEIGHT"),
        "coverage": attributes.get("COVERAGE"),
        "setback": attributes.get("SETBACK"),
        "open_space": attributes.get("OPENSPACE"),
        "animal_regulations": attributes.get("ANIMALREGS"),
        "special_regulations": attributes.get("SPECIALREGS"),
        "ordinance": attributes.get("ORDINANCE_NO"),
        "case_number": attributes.get("CASE_NO"),
        "implementation_date": format_arcgis_date(
            attributes.get("ADOPTDATE")
        ),
        "jurisdiction": "Unincorporated San Diego County",
        "status": "found",
        "source": "County of San Diego Official Zoning Layer",
        "message": None,
        "lookup_method": lookup_method,
        "search_distance_feet": search_distance
    }