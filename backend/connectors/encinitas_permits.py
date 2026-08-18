from connectors.municipal_common import manual_permit_result


def get_encinitas_permit_history_data(apn: str | None, address: str | None = None) -> dict:
    return manual_permit_result(
        city="City of Encinitas",
        portal_url="https://portal.laserfiche.com/Portal/Browse.aspx?id=175544&repo=r-1f1a0b8c",
        public_records_url="https://www.encinitasca.gov/government/departments/city-clerk/public-records-request",
        apn=apn,
        address=address,
    )
