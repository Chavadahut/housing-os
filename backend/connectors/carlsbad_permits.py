from connectors.municipal_common import manual_permit_result


def get_carlsbad_permit_history_data(apn: str | None, address: str | None = None) -> dict:
    return manual_permit_result(
        city="City of Carlsbad",
        portal_url="https://aca-prod.accela.com/CARLSBAD/Default.aspx",
        public_records_url="https://www.carlsbadca.gov/city-hall/city-clerk/public-records-request",
        apn=apn,
        address=address,
    )
