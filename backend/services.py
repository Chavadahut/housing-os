from connectors.san_diego_gis import get_parcel_data
from connectors.san_diego_zoning import get_zoning_data


def lookup_property(address: str):

    property_data = get_parcel_data(address)

    for parcel in property_data["parcels"]:

        zoning = get_zoning_data(
            latitude=parcel["latitude"],
            longitude=parcel["longitude"],
        )

        parcel["zoning"] = zoning

    return property_data