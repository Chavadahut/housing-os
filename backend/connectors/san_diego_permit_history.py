from datetime import datetime
from typing import Any

import requests


DISCRETIONARY_DATASET_ID = "afgf-rb36"
BUILDING_PERMITS_DATASET_ID = "dyzh-7eat"
BUILDING_INSPECTIONS_DATASET_ID = "fan4-6gvy"

SOCRATA_BASE_URL = "https://data.sandiegocounty.gov"

COUNTY_CITIZEN_ACCESS_URL = (
    "https://publicservices.sandiegocounty.gov/"
    "CitizenAccess/"
)

COUNTY_PUBLIC_RECORDS_URL = (
    "https://www.sandiegocounty.gov/content/"
    "sdc/pds/PRA.html"
)


def clean_text(value: Any) -> str | None:

    if value is None:
        return None

    cleaned = str(value).strip()

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


def normalize_apn(apn: str | None) -> str | None:

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


def create_apn_variants(apn: str) -> list[str]:

    normalized = normalize_apn(apn)

    if normalized is None:
        return []

    variants = [
        normalized,
        (
            f"{normalized[0:3]}-"
            f"{normalized[3:6]}-"
            f"{normalized[6:8]}-"
            f"{normalized[8:10]}"
        ),
        (
            f"{normalized[0:3]} "
            f"{normalized[3:6]} "
            f"{normalized[6:8]} "
            f"{normalized[8:10]}"
        ),
        (
            f"{normalized[0:3]}-"
            f"{normalized[3:6]}-"
            f"{normalized[6:10]}"
        ),
        (
            f"{normalized[0:3]} "
            f"{normalized[3:6]} "
            f"{normalized[6:10]}"
        )
    ]

    return list(dict.fromkeys(variants))


def metadata_url(dataset_id: str) -> str:

    return (
        f"{SOCRATA_BASE_URL}/api/views/"
        f"{dataset_id}"
    )


def resource_url(dataset_id: str) -> str:

    return (
        f"{SOCRATA_BASE_URL}/resource/"
        f"{dataset_id}.json"
    )


def empty_permit_history_result(
    status: str,
    message: str
) -> dict:

    return {
        "discretionary_application_found": None,
        "discretionary_application_count": 0,
        "discretionary_applications": [],
        "building_permit_history_checked": False,
        "building_permit_found": None,
        "building_permit_count": 0,
        "building_permit_records": [],
        "building_inspection_history_checked": False,
        "building_inspection_count": 0,
        "building_inspection_records": [],
        "code_compliance_history_checked": False,
        "code_compliance_records": [],
        "code_compliance_research_status": (
            "manual_official_research_required"
        ),
        "code_compliance_search_url": (
            "https://publicservices.sandiegocounty.gov/"
            "CitizenAccess/"
        ),
        "code_compliance_source": (
            "County of San Diego PDS Code Compliance "
            "and Accela Citizen Access"
        ),
        "code_compliance_message": (
            "The County directs property owners and buyers to "
            "research open Code Compliance cases through Accela "
            "Citizen Access. Housing OS did not identify a "
            "documented public parcel-level open-data API that "
            "can be queried reliably for complete Code "
            "Compliance case history, so an automated no-case "
            "result would not be reliable."
        ),
        "permit_history_level": "unknown",
        "constraint_level": "unknown",
        "development_warning": (
            "Automated permit-history screening was not "
            "completed."
        ),
        "manual_research_required": True,
        "citizen_access_url": COUNTY_CITIZEN_ACCESS_URL,
        "public_records_url": COUNTY_PUBLIC_RECORDS_URL,
        "status": status,
        "source": (
            "County of San Diego Open Data Portal and "
            "Planning & Development Services"
        ),
        "message": message,
        "analysis_scope": (
            "preliminary_public_record_screening"
        )
    }


def get_dataset_columns(
    dataset_id: str
) -> list[dict]:

    response = requests.get(
        metadata_url(dataset_id),
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    return data.get("columns", [])


def find_column_field(
    columns: list[dict],
    candidate_keywords: list[str]
) -> str | None:

    for column in columns:

        field_name = clean_text(
            column.get("fieldName")
        )

        column_name = clean_text(
            column.get("name")
        )

        combined_name = " ".join(
            value.lower()
            for value in [
                field_name,
                column_name
            ]
            if value
        )

        if all(
            keyword.lower() in combined_name
            for keyword in candidate_keywords
        ):

            return field_name

    return None


def find_first_column_field(
    columns: list[dict],
    keyword_groups: list[list[str]]
) -> str | None:

    for keywords in keyword_groups:

        field_name = find_column_field(
            columns=columns,
            candidate_keywords=keywords
        )

        if field_name:
            return field_name

    return None


def escape_socrata_value(
    value: str
) -> str:

    return value.replace("'", "''")


def build_apn_where_clause(
    apn_field: str,
    apn_variants: list[str]
) -> str:

    quoted_values = ", ".join(
        (
            "'"
            + escape_socrata_value(value)
            + "'"
        )
        for value in apn_variants
    )

    return (
        f"upper({apn_field}) in "
        f"({quoted_values.upper()})"
    )


def query_records_by_apn(
    dataset_id: str,
    apn_field: str,
    apn_variants: list[str],
    limit: int = 250
) -> list[dict]:

    params = {
        "$where": build_apn_where_clause(
            apn_field=apn_field,
            apn_variants=apn_variants
        ),
        "$limit": limit,
        "$order": ":id DESC"
    }

    response = requests.get(
        resource_url(dataset_id),
        params=params,
        timeout=30
    )

    response.raise_for_status()

    return response.json()


def get_record_value(
    record: dict,
    field_name: str | None
):

    if not field_name:
        return None

    return record.get(field_name)


def parse_date(
    value: Any
) -> str | None:

    cleaned = clean_text(value)

    if cleaned is None:
        return None

    normalized = cleaned.replace("Z", "")

    date_formats = [
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m/%d/%Y %I:%M:%S %p"
    ]

    for date_format in date_formats:

        try:

            parsed_date = datetime.strptime(
                normalized,
                date_format
            )

            return parsed_date.date().isoformat()

        except ValueError:
            continue

    return cleaned


def format_discretionary_record(
    record: dict,
    columns: list[dict],
    apn_field: str
) -> dict:

    record_number_field = find_first_column_field(
        columns,
        [
            ["record", "number"],
            ["project", "number"],
            ["permit", "number"],
            ["case", "number"]
        ]
    )

    record_type_field = find_first_column_field(
        columns,
        [
            ["record", "type"],
            ["application", "type"],
            ["project", "type"],
            ["permit", "type"]
        ]
    )

    status_field = find_first_column_field(
        columns,
        [
            ["record", "status"],
            ["application", "status"],
            ["project", "status"],
            ["status"]
        ]
    )

    description_field = find_first_column_field(
        columns,
        [
            ["project", "description"],
            ["record", "description"],
            ["description"],
            ["scope"]
        ]
    )

    project_name_field = find_first_column_field(
        columns,
        [
            ["project", "name"],
            ["record", "name"],
            ["application", "name"],
            ["name"]
        ]
    )

    address_field = find_first_column_field(
        columns,
        [
            ["site", "address"],
            ["project", "address"],
            ["street", "address"],
            ["address"]
        ]
    )

    opened_date_field = find_first_column_field(
        columns,
        [
            ["opened", "date"],
            ["application", "date"],
            ["created", "date"],
            ["filed", "date"],
            ["start", "date"]
        ]
    )

    completed_date_field = find_first_column_field(
        columns,
        [
            ["completed", "date"],
            ["closed", "date"],
            ["final", "date"],
            ["decision", "date"]
        ]
    )

    applicant_field = find_first_column_field(
        columns,
        [
            ["applicant", "name"],
            ["applicant"],
            ["customer", "name"]
        ]
    )

    planner_field = find_first_column_field(
        columns,
        [
            ["project", "manager"],
            ["assigned", "staff"],
            ["planner"]
        ]
    )

    return {
        "record_number": clean_text(
            get_record_value(
                record,
                record_number_field
            )
        ),
        "record_type": clean_text(
            get_record_value(
                record,
                record_type_field
            )
        ),
        "status": clean_text(
            get_record_value(
                record,
                status_field
            )
        ),
        "project_name": clean_text(
            get_record_value(
                record,
                project_name_field
            )
        ),
        "description": clean_text(
            get_record_value(
                record,
                description_field
            )
        ),
        "address": clean_text(
            get_record_value(
                record,
                address_field
            )
        ),
        "apn": clean_text(
            get_record_value(
                record,
                apn_field
            )
        ),
        "opened_date": parse_date(
            get_record_value(
                record,
                opened_date_field
            )
        ),
        "completed_date": parse_date(
            get_record_value(
                record,
                completed_date_field
            )
        ),
        "applicant": clean_text(
            get_record_value(
                record,
                applicant_field
            )
        ),
        "assigned_staff": clean_text(
            get_record_value(
                record,
                planner_field
            )
        )
    }


def format_building_permit_record(
    record: dict,
    columns: list[dict],
    apn_field: str
) -> dict:

    permit_number_field = find_first_column_field(
        columns,
        [
            ["permit", "num"],
            ["record", "id"],
            ["record", "number"]
        ]
    )

    description_field = find_first_column_field(
        columns,
        [
            ["description"],
            ["work", "description"],
            ["scope"]
        ]
    )

    status_field = find_first_column_field(
        columns,
        [
            ["status", "current"],
            ["status"]
        ]
    )

    permit_class_field = find_first_column_field(
        columns,
        [
            ["permit", "class", "mapped"],
            ["permit", "class"]
        ]
    )

    work_class_field = find_first_column_field(
        columns,
        [
            ["work", "class"]
        ]
    )

    address_field = find_first_column_field(
        columns,
        [
            ["full", "address"],
            ["original", "address"],
            ["street", "address"],
            ["address"]
        ]
    )

    applied_date_field = find_first_column_field(
        columns,
        [
            ["applied", "date"],
            ["open", "date"]
        ]
    )

    issued_date_field = find_first_column_field(
        columns,
        [
            ["issued", "date"]
        ]
    )

    completed_date_field = find_first_column_field(
        columns,
        [
            ["completed", "date"],
            ["final", "date"]
        ]
    )

    return {
        "permit_number": clean_text(
            get_record_value(
                record,
                permit_number_field
            )
        ),
        "status": clean_text(
            get_record_value(
                record,
                status_field
            )
        ),
        "permit_class": clean_text(
            get_record_value(
                record,
                permit_class_field
            )
        ),
        "work_class": clean_text(
            get_record_value(
                record,
                work_class_field
            )
        ),
        "description": clean_text(
            get_record_value(
                record,
                description_field
            )
        ),
        "address": clean_text(
            get_record_value(
                record,
                address_field
            )
        ),
        "apn": clean_text(
            get_record_value(
                record,
                apn_field
            )
        ),
        "applied_date": parse_date(
            get_record_value(
                record,
                applied_date_field
            )
        ),
        "issued_date": parse_date(
            get_record_value(
                record,
                issued_date_field
            )
        ),
        "completed_date": parse_date(
            get_record_value(
                record,
                completed_date_field
            )
        )
    }


def query_records_by_permit_numbers(
    dataset_id: str,
    permit_field: str,
    permit_numbers: list[str],
    limit: int = 1000
) -> list[dict]:

    cleaned_numbers = [
        clean_text(value)
        for value in permit_numbers
        if clean_text(value)
    ]

    if not cleaned_numbers:
        return []

    quoted_values = ", ".join(
        (
            "'"
            + escape_socrata_value(value)
            + "'"
        )
        for value in cleaned_numbers
    )

    params = {
        "$where": (
            f"upper({permit_field}) in "
            f"({quoted_values.upper()})"
        ),
        "$limit": limit,
        "$order": ":id DESC"
    }

    response = requests.get(
        resource_url(dataset_id),
        params=params,
        timeout=30
    )

    response.raise_for_status()

    return response.json()


def format_building_inspection_record(
    record: dict,
    columns: list[dict],
    permit_field: str
) -> dict:

    inspection_type_field = find_first_column_field(
        columns,
        [
            ["inspection", "type"],
            ["inspection", "name"],
            ["type"]
        ]
    )

    inspection_status_field = find_first_column_field(
        columns,
        [
            ["inspection", "status"],
            ["result"],
            ["status"]
        ]
    )

    inspection_date_field = find_first_column_field(
        columns,
        [
            ["inspection", "date"],
            ["completed", "date"],
            ["scheduled", "date"],
            ["date"]
        ]
    )

    inspector_field = find_first_column_field(
        columns,
        [
            ["inspector", "name"],
            ["inspector"]
        ]
    )

    comments_field = find_first_column_field(
        columns,
        [
            ["inspection", "comment"],
            ["comments"],
            ["comment"],
            ["notes"]
        ]
    )

    address_field = find_first_column_field(
        columns,
        [
            ["full", "address"],
            ["street", "address"],
            ["address"]
        ]
    )

    return {
        "permit_number": clean_text(
            get_record_value(
                record,
                permit_field
            )
        ),
        "inspection_type": clean_text(
            get_record_value(
                record,
                inspection_type_field
            )
        ),
        "status": clean_text(
            get_record_value(
                record,
                inspection_status_field
            )
        ),
        "inspection_date": parse_date(
            get_record_value(
                record,
                inspection_date_field
            )
        ),
        "inspector": clean_text(
            get_record_value(
                record,
                inspector_field
            )
        ),
        "comments": clean_text(
            get_record_value(
                record,
                comments_field
            )
        ),
        "address": clean_text(
            get_record_value(
                record,
                address_field
            )
        )
    }


def determine_permit_history_level(
    discretionary_records: list[dict],
    building_permit_records: list[dict]
) -> dict:

    active_status_terms = {
        "active",
        "open",
        "in review",
        "pending",
        "submitted",
        "processing",
        "corrections",
        "issued"
    }

    active_discretionary = []

    for record in discretionary_records:

        status = clean_text(
            record.get("status")
        )

        if not status:
            continue

        normalized_status = status.lower()

        if any(
            term in normalized_status
            for term in active_status_terms
        ):
            active_discretionary.append(record)

    active_building = []

    for record in building_permit_records:

        status = clean_text(
            record.get("status")
        )

        if not status:
            continue

        normalized_status = status.lower()

        if any(
            term in normalized_status
            for term in {
                "active",
                "open",
                "in review",
                "pending",
                "submitted",
                "processing",
                "corrections"
            }
        ):
            active_building.append(record)

    if active_discretionary or active_building:

        return {
            "permit_history_level": (
                "active_permit_or_planning_history_found"
            ),
            "constraint_level": "moderate",
            "development_warning": (
                "One or more building-permit or discretionary "
                "planning records appear active or unresolved. "
                "The record details and their effect on future "
                "development should be reviewed directly with "
                "the County."
            )
        }

    if discretionary_records or building_permit_records:

        return {
            "permit_history_level": (
                "permit_history_found"
            ),
            "constraint_level": "review",
            "development_warning": (
                "County building-permit or discretionary "
                "planning history was identified. Prior permits, "
                "approvals, final status, conditions, expiration "
                "dates, and archived documents should be reviewed "
                "before relying on the property for a new "
                "development proposal."
            )
        }

    return {
        "permit_history_level": (
            "no_open_data_permit_records_found"
        ),
        "constraint_level": "unknown",
        "development_warning": (
            "No matching building permit or discretionary "
            "planning application was found in the County open "
            "datasets checked by Housing OS. This does not "
            "establish that the property has no older permits, "
            "archived records, inspections, code cases, or other "
            "development history."
        )
    }


def get_permit_history_data(
    apn: str | None
) -> dict:

    normalized_apn = normalize_apn(apn)

    if normalized_apn is None:

        return empty_permit_history_result(
            status="invalid_apn",
            message=(
                "A valid ten-digit APN was not available "
                "for permit-history screening."
            )
        )

    apn_variants = create_apn_variants(
        normalized_apn
    )

    try:

        discretionary_columns = get_dataset_columns(
            DISCRETIONARY_DATASET_ID
        )

        discretionary_apn_field = (
            find_first_column_field(
                discretionary_columns,
                [
                    ["assessor", "parcel"],
                    ["parcel", "number"],
                    ["apn"]
                ]
            )
        )

        if discretionary_apn_field is None:

            return empty_permit_history_result(
                status="schema_error",
                message=(
                    "The County discretionary-planning "
                    "dataset did not expose a recognizable "
                    "APN field."
                )
            )

        discretionary_raw_records = (
            query_records_by_apn(
                dataset_id=(
                    DISCRETIONARY_DATASET_ID
                ),
                apn_field=(
                    discretionary_apn_field
                ),
                apn_variants=apn_variants
            )
        )

        discretionary_records = [
            format_discretionary_record(
                record=record,
                columns=discretionary_columns,
                apn_field=(
                    discretionary_apn_field
                )
            )
            for record in discretionary_raw_records
        ]

        building_permit_history_checked = False
        building_permit_records = []
        building_permit_error = None

        building_inspection_history_checked = False
        building_inspection_records = []
        building_inspection_error = None

        try:

            building_columns = get_dataset_columns(
                BUILDING_PERMITS_DATASET_ID
            )

            building_apn_field = (
                find_first_column_field(
                    building_columns,
                    [
                        ["parcel", "number"],
                        ["assessor", "parcel"],
                        ["apn"]
                    ]
                )
            )

            if building_apn_field is None:

                building_permit_error = (
                    "The County Building Permits "
                    "dataset did not expose a "
                    "recognizable parcel-number field."
                )

            else:

                building_raw_records = (
                    query_records_by_apn(
                        dataset_id=(
                            BUILDING_PERMITS_DATASET_ID
                        ),
                        apn_field=(
                            building_apn_field
                        ),
                        apn_variants=apn_variants
                    )
                )

                building_permit_records = [
                    format_building_permit_record(
                        record=record,
                        columns=building_columns,
                        apn_field=(
                            building_apn_field
                        )
                    )
                    for record in building_raw_records
                ]

                building_permit_history_checked = True

        except requests.Timeout:

            building_permit_error = (
                "The County Building Permits "
                "dataset timed out."
            )

        except requests.RequestException as error:

            building_permit_error = (
                "The County Building Permits "
                f"dataset returned an error: {error}"
            )

        except ValueError as error:

            building_permit_error = (
                "The County Building Permits "
                "dataset returned an unreadable "
                f"response: {error}"
            )

        if building_permit_history_checked:

            permit_numbers = [
                record.get("permit_number")
                for record in building_permit_records
                if record.get("permit_number")
            ]

            if permit_numbers:

                try:

                    inspection_columns = get_dataset_columns(
                        BUILDING_INSPECTIONS_DATASET_ID
                    )

                    inspection_permit_field = (
                        find_first_column_field(
                            inspection_columns,
                            [
                                ["permit", "num"],
                                ["record", "id"],
                                ["record", "number"],
                                ["permit"]
                            ]
                        )
                    )

                    if inspection_permit_field is None:

                        building_inspection_error = (
                            "The County Building Inspections "
                            "dataset did not expose a recognizable "
                            "permit-number field."
                        )

                    else:

                        inspection_raw_records = (
                            query_records_by_permit_numbers(
                                dataset_id=(
                                    BUILDING_INSPECTIONS_DATASET_ID
                                ),
                                permit_field=(
                                    inspection_permit_field
                                ),
                                permit_numbers=permit_numbers
                            )
                        )

                        building_inspection_records = [
                            format_building_inspection_record(
                                record=record,
                                columns=inspection_columns,
                                permit_field=(
                                    inspection_permit_field
                                )
                            )
                            for record in inspection_raw_records
                        ]

                        building_inspection_history_checked = True

                except requests.Timeout:

                    building_inspection_error = (
                        "The County Building Inspections "
                        "dataset timed out."
                    )

                except requests.RequestException as error:

                    building_inspection_error = (
                        "The County Building Inspections "
                        f"dataset returned an error: {error}"
                    )

                except ValueError as error:

                    building_inspection_error = (
                        "The County Building Inspections "
                        "dataset returned an unreadable "
                        f"response: {error}"
                    )

        interpretation = (
            determine_permit_history_level(
                discretionary_records=(
                    discretionary_records
                ),
                building_permit_records=(
                    building_permit_records
                )
            )
        )

        message_parts = [
            (
                "Housing OS checked the County's "
                "open discretionary-planning dataset "
                "by APN."
            )
        ]

        if building_permit_history_checked:

            message_parts.append(
                (
                    "Housing OS also checked the "
                    "County Building Permits open "
                    "dataset by parcel number. That "
                    "dataset covers building permits "
                    "issued by Planning & Development "
                    "Services since 2005."
                )
            )

        elif building_permit_error:

            message_parts.append(
                building_permit_error
            )

        if building_inspection_history_checked:

            message_parts.append(
                (
                    "Housing OS also checked the County "
                    "Building Inspections open dataset for "
                    "the permit numbers found on this parcel."
                )
            )

        elif building_inspection_error:

            message_parts.append(
                building_inspection_error
            )

        message_parts.append(
            (
                "Complete inspection history, code "
                "compliance history, archived or "
                "pre-digital records, and records "
                "outside the open datasets still "
                "require Citizen Access, the PDS "
                "Document Library, or County records "
                "research."
            )
        )

        return {
            "discretionary_application_found": bool(
                discretionary_records
            ),
            "discretionary_application_count": len(
                discretionary_records
            ),
            "discretionary_applications": (
                discretionary_records
            ),
            "building_permit_history_checked": (
                building_permit_history_checked
            ),
            "building_permit_found": (
                bool(building_permit_records)
                if building_permit_history_checked
                else None
            ),
            "building_permit_count": len(
                building_permit_records
            ),
            "building_permit_records": (
                building_permit_records
            ),
            "building_inspection_history_checked": (
                building_inspection_history_checked
            ),
            "building_inspection_count": len(
                building_inspection_records
            ),
            "building_inspection_records": (
                building_inspection_records
            ),
            "code_compliance_history_checked": False,
            "code_compliance_records": [],
            "code_compliance_research_status": (
                "manual_official_research_required"
            ),
            "code_compliance_search_url": (
                COUNTY_CITIZEN_ACCESS_URL
            ),
            "code_compliance_source": (
                "County of San Diego PDS Code Compliance "
                "and Accela Citizen Access"
            ),
            "code_compliance_message": (
                "The County Code Compliance FAQ directs "
                "property owners and prospective buyers to "
                "research open Code Compliance cases through "
                "Accela Citizen Access. Housing OS did not "
                "identify a documented public parcel-level "
                "open-data API that can be queried reliably "
                "for complete Code Compliance case history. "
                "The public County performance datasets report "
                "aggregate case counts rather than parcel-level "
                "case records, so Housing OS leaves this item "
                "unverified instead of reporting a false "
                "negative."
            ),
            "permit_history_level": interpretation[
                "permit_history_level"
            ],
            "constraint_level": interpretation[
                "constraint_level"
            ],
            "development_warning": interpretation[
                "development_warning"
            ],
            "manual_research_required": True,
            "citizen_access_url": (
                COUNTY_CITIZEN_ACCESS_URL
            ),
            "public_records_url": (
                COUNTY_PUBLIC_RECORDS_URL
            ),
            "status": "found",
            "source": (
                "County of San Diego Building Permits "
                "and Discretionary Planning Applications "
                "Open Datasets"
            ),
            "message": " ".join(message_parts),
            "analysis_scope": (
                "preliminary_public_record_screening"
            )
        }

    except requests.Timeout:

        return empty_permit_history_result(
            status="timeout",
            message=(
                "The County permit-history service took "
                "too long to respond. Please try again."
            )
        )

    except requests.RequestException as error:

        return empty_permit_history_result(
            status="error",
            message=str(error)
        )

    except ValueError as error:

        return empty_permit_history_result(
            status="error",
            message=(
                "The County permit-history service returned "
                f"an unreadable response: {error}"
            )
        )