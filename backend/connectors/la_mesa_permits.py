from typing import Any


LA_MESA_MAINTSTAR_URL = (
    "https://h9.maintstar.co/LaMesa/portal/"
)

LA_MESA_PUBLIC_RECORDS_URL = (
    "https://la-mesa-ca.nextrequest.com/"
)

LA_MESA_BUILDING_DIVISION_URL = (
    "https://www.cityoflamesa.gov/111/Building"
)


def clean_text(
    value: Any
) -> str | None:

    if value is None:
        return None

    cleaned = str(
        value
    ).strip()

    if cleaned.upper() in {
        "",
        "-",
        "NULL",
        "NONE",
        "N/A",
        "NA"
    }:
        return None

    return cleaned


def normalize_apn(
    apn: str | None
) -> str | None:

    if not apn:
        return None

    digits = "".join(
        character
        for character in str(apn)
        if character.isdigit()
    )

    if len(digits) != 10:
        return None

    return digits


def normalize_address(
    address: str | None
) -> str | None:

    cleaned = clean_text(
        address
    )

    if cleaned is None:
        return None

    return " ".join(
        cleaned.upper().split()
    )


def get_la_mesa_permit_history_data(
    apn: str | None,
    address: str | None = None
) -> dict:

    normalized_apn = normalize_apn(
        apn
    )

    normalized_address = normalize_address(
        address
    )

    lookup_identifiers = []

    if normalized_apn:

        lookup_identifiers.append(
            f"APN {normalized_apn}"
        )

    if normalized_address:

        lookup_identifiers.append(
            normalized_address
        )

    identifier_text = (
        " and ".join(
            lookup_identifiers
        )
        if lookup_identifiers
        else "the property"
    )

    return {
        "discretionary_application_found": None,
        "discretionary_application_count": 0,
        "discretionary_applications": [],
        "building_permit_history_checked": False,
        "building_permit_records": [],
        "code_compliance_history_checked": False,
        "code_compliance_records": [],
        "permit_history_level": (
            "manual_city_portal_review_required"
        ),
        "constraint_level": "unknown",
        "development_warning": (
            "The City of La Mesa uses the MaintStar permit "
            "portal for permit activity, but Housing OS does "
            "not currently have a verified public API that can "
            "retrieve complete La Mesa permit-history records "
            "automatically. Permit and planning history must "
            "therefore be confirmed through the City's portal "
            "and public-record channels."
        ),
        "manual_research_required": True,
        "citizen_access_url": LA_MESA_MAINTSTAR_URL,
        "public_records_url": (
            LA_MESA_PUBLIC_RECORDS_URL
        ),
        "status": "manual_review_required",
        "source": (
            "City of La Mesa MaintStar Permit Portal, "
            "Building Division, and Public Records Portal"
        ),
        "message": (
            "Housing OS identified the correct City of La Mesa "
            f"permit-research sources for {identifier_text}. "
            "Automated record retrieval is not yet available. "
            "The MaintStar portal can be used to check current "
            "permit status and activity, while older or otherwise "
            "unavailable records may require a City public-records "
            "request."
        ),
        "analysis_scope": (
            "jurisdiction_specific_manual_permit_screening"
        ),
        "jurisdiction": "City of La Mesa",
        "lookup_apn": normalized_apn,
        "lookup_address": normalized_address,
        "permit_portal": {
            "name": "City of La Mesa MaintStar Permit Portal",
            "url": LA_MESA_MAINTSTAR_URL,
            "automated_lookup_available": False,
            "supports_manual_status_lookup": True
        },
        "building_division": {
            "name": "City of La Mesa Building Division",
            "url": LA_MESA_BUILDING_DIVISION_URL
        },
        "public_records_portal": {
            "name": "City of La Mesa Public Records Portal",
            "url": LA_MESA_PUBLIC_RECORDS_URL
        }
    }