import requests


SAN_DIEGO_GIS_URL = "https://gis-public.sandiegocounty.gov/arcgis/rest/services"


def get_parcel_data(address: str):

    params = {
        "address": address
    }

    # Temporary test connection
    response = requests.get(
        SAN_DIEGO_GIS_URL,
        params=params,
        timeout=10
    )

    return {
        "address": address,
        "apn": None,
        "owner": None,
        "lot_size_sqft": None,
        "latitude": None,
        "longitude": None,
        "source": "San Diego GIS"
    }