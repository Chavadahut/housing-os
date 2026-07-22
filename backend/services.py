def lookup_property(address: str):

    return {
        "address": address,

        # Parcel information
        "apn": None,
        "parcel_number": None,

        # Ownership
        "owner": None,

        # Physical characteristics
        "lot_size_sqft": None,
        "acreage": None,

        # Location
        "latitude": None,
        "longitude": None,

        # Planning information
        "jurisdiction": "San Diego County",
        "zoning": None,
        "allowed_uses": [],

        # AI notes
        "development_notes": None,

        # Data source
        "source": "placeholder"
    }