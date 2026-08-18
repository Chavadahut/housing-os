from typing import Any


SAN_DIEGO_ACCELA_URL = (
    "https://aca-prod.accela.com/SANDIEGO/Cap/CapHome.aspx"
    "?module=DSD&TabName=DSD"
)

SAN_DIEGO_OPENDSD_URL = (
    "https://opendsd.sandiego.gov/web/approvals/"
)

SAN_DIEGO_PUBLIC_RECORDS_URL = (
    "https://sandiego.nextrequest.com/"
)

SAN_DIEGO_BUILDING_DIVISION_URL = (
    "https://www.sandiego.gov/development-services"
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


def get_san_diego_permit_history_data(
    apn: str | None,
    address: str | None = None
) -> dict:
    """
    Manual-review permit history result for City of San Diego.

    The Development Services Department (DSD) publishes permit records
    only as bulk CSV exports (data.sandiego.gov), not as a live per-address
    or per-APN query API, so Housing OS cannot automatically retrieve a
    parcel-specific permit history today. This mirrors the same
    manual-review shape used by get_la_mesa_permit_history_data() so
    downstream code (feasibility_summary, development_scenario) does not
    need special-casing per jurisdiction.
    """

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
            "The City of San Diego Development Services Department "
            "(DSD) publishes permit and approval records through the "
            "Accela Citizen Access and OpenDSD portals, and as bulk "
            "data downloads, but Housing OS does not currently have a "
            "verified live API that can retrieve complete parcel-level "
            "permit history automatically. Permit and planning history "
            "must therefore be confirmed through the City's portals "
            "and public-record channels."
        ),
        "manual_research_required": True,
        "citizen_access_url": SAN_DIEGO_ACCELA_URL,
        "public_records_url": (
            SAN_DIEGO_PUBLIC_RECORDS_URL
        ),
        "status": "manual_review_required",
        "source": (
            "City of San Diego Accela Citizen Access, OpenDSD "
            "Approval Search, Development Services Department, "
            "and Public Records Portal"
        ),
        "message": (
            "Housing OS identified the correct City of San Diego "
            f"permit-research sources for {identifier_text}. "
            "Automated record retrieval is not yet available. Accela "
            "Citizen Access and OpenDSD's Approval Search can be used "
            "to check permit status and activity by address, while "
            "older or otherwise unavailable records may require a "
            "City public-records request."
        ),
        "analysis_scope": (
            "jurisdiction_specific_manual_permit_screening"
        ),
        "jurisdiction": "City of San Diego",
        "lookup_apn": normalized_apn,
        "lookup_address": normalized_address,
        "permit_portal": {
            "name": "City of San Diego Accela Citizen Access",
            "url": SAN_DIEGO_ACCELA_URL,
            "automated_lookup_available": False,
            "supports_manual_status_lookup": True
        },
        "open_data_portal": {
            "name": "City of San Diego OpenDSD Approval Search",
            "url": SAN_DIEGO_OPENDSD_URL,
            "automated_lookup_available": False,
            "supports_manual_status_lookup": True
        },
        "building_division": {
            "name": "City of San Diego Development Services Department",
            "url": SAN_DIEGO_BUILDING_DIVISION_URL
        },
        "public_records_portal": {
            "name": "City of San Diego Public Records Portal (NextRequest)",
            "url": SAN_DIEGO_PUBLIC_RECORDS_URL
        }
    }