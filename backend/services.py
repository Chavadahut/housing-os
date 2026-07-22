from connectors.san_diego_gis import get_parcel_data


def lookup_property(address: str):

    parcel_data = get_parcel_data(address)

    return {
        "address": parcel_data["address"],

        # Parcel information
        "apn": parcel_data["apn"],
        "parcel_number": parcel_data["apn"],

        # Ownership
        "owner": parcel_data["owner"],

        # Physical characteristics
        "lot_size_sqft": parcel_data["lot_size_sqft"],
        "acreage": None,

        # Location
        "latitude": parcel_data["latitude"],
        "longitude": parcel_data["longitude"],

        # Planning information
        "jurisdiction": "San Diego County",
        "zoning": None,
        "allowed_uses": [],

        # AI notes
        "development_notes": None,

        # Data source
        "source": parcel_data["source"]
    }