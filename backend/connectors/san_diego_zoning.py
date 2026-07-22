import requests
from datetime import datetime, timezone


URL = (
    "https://geo.sandag.org/server/rest/services/"
    "Hosted/Zoning_Base_SD/FeatureServer/0/query"
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

    params = {
        "where": "1=1",
        "geometry": f"{longitude},{latitude}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "zone_name,ordnum,imp_date",
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
        raise requests.RequestException(
            data["error"].get(
                "message",
                "The zoning GIS returned an error."
            )
        )

    return data.get("features", [])


def get_zoning_data(latitude: float, longitude: float):

    try:
        # First try the exact GPS point.
        features = query_zoning(
            latitude=latitude,
            longitude=longitude
        )

        lookup_method = "exact_point"
        search_distance = 0

        # If the point falls on a road or map gap,
        # search within 100 feet.
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
            "source": "SANDAG City of San Diego Zoning Base Layer",
            "message": (
                "The zoning GIS server took too long to respond. "
                "Please try again."
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
            "source": "SANDAG City of San Diego Zoning Base Layer",
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
            "source": "SANDAG City of San Diego Zoning Base Layer",
            "message": "The zoning GIS returned an invalid response.",
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
            "source": "SANDAG City of San Diego Zoning Base Layer",
            "message": (
                "No City of San Diego base zoning was found "
                "at or within 100 feet of this location."
            ),
            "lookup_method": None,
            "search_distance_feet": None
        }

    attributes = features[0].get("attributes", {})

    return {
        "code": attributes.get("zone_name"),
        "ordinance": attributes.get("ordnum"),
        "implementation_date": format_arcgis_date(
            attributes.get("imp_date")
        ),
        "jurisdiction": "City of San Diego",
        "status": "found",
        "source": "SANDAG City of San Diego Zoning Base Layer",
        "message": None,
        "lookup_method": lookup_method,
        "search_distance_feet": search_distance
    }