import requests
from pyproj import Transformer

from address_parser import parse_address


URL = (
    "https://gis-public.sandiegocounty.gov/arcgis/rest/services/"
    "sdep_warehouse/ADDRAPN/FeatureServer/0/query"
)

# San Diego County State Plane (EPSG:2230) to GPS (EPSG:4326)
transformer = Transformer.from_crs(
    "EPSG:2230",
    "EPSG:4326",
    always_xy=True
)


def get_parcel_data(address: str):

    parsed = parse_address(address)

    if parsed is None:
        return {
            "address": address,
            "parcel_count": 0,
            "parcels": [],
            "source": "San Diego GIS",
            "status": "invalid_address",
            "message": "The address could not be understood."
        }

    where = (
        f"ADDRNMBR = {parsed['number']} "
        f"AND UPPER(ADDRNAME) = '{parsed['street']}' "
        f"AND UPPER(ADDRSFX) = '{parsed['suffix']}'"
    )

    params = {
        "where": where,
        "outFields": "*",
        "returnGeometry": "true",
        "f": "json"
    }

    try:
        response = requests.get(
            URL,
            params=params,
            timeout=30
        )

        response.raise_for_status()

        print("Status:", response.status_code)

        data = response.json()

    except requests.Timeout:
        return {
            "address": address,
            "parcel_count": 0,
            "parcels": [],
            "source": "San Diego GIS",
            "status": "timeout",
            "message": (
                "The San Diego County GIS server took too long "
                "to respond. Please try again."
            )
        }

    except requests.RequestException as error:
        return {
            "address": address,
            "parcel_count": 0,
            "parcels": [],
            "source": "San Diego GIS",
            "status": "error",
            "message": str(error)
        }

    except ValueError:
        return {
            "address": address,
            "parcel_count": 0,
            "parcels": [],
            "source": "San Diego GIS",
            "status": "error",
            "message": "The GIS server returned an invalid response."
        }

    if "features" not in data:
        print(data)

        return {
            "address": address,
            "parcel_count": 0,
            "parcels": [],
            "source": "San Diego GIS",
            "status": "error",
            "message": data.get(
                "error",
                "The GIS server did not return parcel records."
            )
        }

    parcels = []

    for feature in data["features"]:

        attrs = feature.get("attributes", {})
        geom = feature.get("geometry")

        if not geom:
            continue

        longitude, latitude = transformer.transform(
            geom["x"],
            geom["y"]
        )

        address_number = attrs.get("ADDRNMBR")
        street_name = attrs.get("ADDRNAME")
        street_suffix = attrs.get("ADDRSFX")

        if address_number is not None:
            try:
                address_number = int(address_number)
            except (TypeError, ValueError):
                pass

        parcel_address = " ".join(
            str(value)
            for value in [
                address_number,
                street_name,
                street_suffix
            ]
            if value not in [None, ""]
        )

        parcels.append({
            "apn": attrs.get("APN"),
            "address": parcel_address,
            "zip": attrs.get("ADDRZIP"),
            "community": attrs.get("COMMUNITY"),
            "latitude": latitude,
            "longitude": longitude
        })

    if not parcels:
        return {
            "address": address,
            "parcel_count": 0,
            "parcels": [],
            "source": "San Diego GIS",
            "status": "not_found",
            "message": "No parcels were found for this address."
        }

    return {
        "address": address,
        "parcel_count": len(parcels),
        "parcels": parcels,
        "source": "San Diego GIS",
        "status": "found",
        "message": None
    }