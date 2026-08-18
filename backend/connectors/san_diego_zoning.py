import requests
from datetime import datetime, timezone

from pyproj import Transformer


URL = (
    "https://webmaps.sandiego.gov/arcgis/rest/services/"
    "DSD/Zoning_Base/MapServer/0/query"
)

# GPS coordinates to San Diego State Plane coordinates
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


def query_zoning(
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
        "outFields": "*",
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
            "The zoning GIS returned an error."
        )

        raise requests.RequestException(error_message)

    return data.get("features", [])


def get_zoning_data(latitude: float, longitude: float):

    try:
        features = query_zoning(
            latitude=latitude,
            longitude=longitude
        )

        lookup_method = "exact_point"
        search_distance = 0

        if not features:
            features = query_zoning(
                latitude=latitude,
                longitude=longitude,
                search_distance=100
            )

            lookup_method = "nearby_search"
            search_distance = 100

    except requests.Timeout:
        return {
            "code": None,
            "ordinance": None,
            "implementation_date": None,
            "jurisdiction": "City of San Diego",
            "status": "timeout",
            "source": "City of San Diego Official Zoning Map",
            "message": (
                "The City of San Diego zoning server took too long "
                "to respond. Please try again."
            ),
            "lookup_method": None,
            "search_distance_feet": None
        }

    except requests.RequestException as error:
        return {
            "code": None,
            "ordinance": None,
            "implementation_date": None,
            "jurisdiction": "City of San Diego",
            "status": "error",
            "source": "City of San Diego Official Zoning Map",
            "message": str(error),
            "lookup_method": None,
            "search_distance_feet": None
        }

    except ValueError:
        return {
            "code": None,
            "ordinance": None,
            "implementation_date": None,
            "jurisdiction": "City of San Diego",
            "status": "error",
            "source": "City of San Diego Official Zoning Map",
            "message": "The zoning server returned an invalid response.",
            "lookup_method": None,
            "search_distance_feet": None
        }

    if not features:
        return {
            "code": None,
            "ordinance": None,
            "implementation_date": None,
            "jurisdiction": None,
            "status": "not_found",
            "source": "City of San Diego Official Zoning Map",
            "message": (
                "No City of San Diego zoning was found at or "
                "within 100 feet of this location."
            ),
            "lookup_method": None,
            "search_distance_feet": None
        }

    attributes = features[0].get("attributes", {})

    zoning_code = (
        attributes.get("ZONE_NAME")
        or attributes.get("zone_name")
    )

    ordinance = (
        attributes.get("ORD_NUM")
        or attributes.get("ORDNUM")
        or attributes.get("ordnum")
    )

    implementation_date = (
        attributes.get("IMP_DATE")
        or attributes.get("imp_date")
    )

    return {
        "code": zoning_code,
        "ordinance": ordinance,
        "implementation_date": format_arcgis_date(
            implementation_date
        ),
        "jurisdiction": "City of San Diego",
        "status": "found",
        "source": "City of San Diego Official Zoning Map",
        "message": None,
        "lookup_method": lookup_method,
        "search_distance_feet": search_distance
    }