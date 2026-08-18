import json
from datetime import datetime, timezone
from typing import Any

import requests


OPEN_SPACE_EASEMENT_URL = (
    "https://gis-public.sandiegocounty.gov/arcgis/rest/services/"
    "sdep_warehouse/ESMT_OPEN_SPACE/FeatureServer/0/query"
)

WASTEWATER_EASEMENT_URL = (
    "https://gis-public.sandiegocounty.gov/arcgis/rest/services/"
    "DPW/WASTEWATER/FeatureServer/36/query"
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


def parse_arcgis_date(value: Any) -> str | None:

    if value is None:
        return None

    if isinstance(value, (int, float)):

        try:

            return datetime.fromtimestamp(
                value / 1000,
                tz=timezone.utc
            ).date().isoformat()

        except (
            OverflowError,
            OSError,
            ValueError
        ):

            return str(value)

    return clean_text(value)


def get_first_coordinate(
    rings: list
) -> tuple[float, float] | None:

    try:

        for ring in rings:

            for coordinate in ring:

                if (
                    isinstance(coordinate, list)
                    and len(coordinate) >= 2
                ):

                    x_value = float(
                        coordinate[0]
                    )

                    y_value = float(
                        coordinate[1]
                    )

                    return (
                        x_value,
                        y_value
                    )

    except (
        TypeError,
        ValueError
    ):

        return None

    return None


def detect_parcel_wkid(
    parcel_boundary: dict | None
) -> int | None:

    if not isinstance(
        parcel_boundary,
        dict
    ):

        return None

    spatial_reference = (
        parcel_boundary.get(
            "spatialReference"
        )
        or {}
    )

    explicit_wkid = (
        spatial_reference.get(
            "latestWkid"
        )
        or spatial_reference.get(
            "wkid"
        )
    )

    if explicit_wkid:

        try:

            return int(
                explicit_wkid
            )

        except (
            TypeError,
            ValueError
        ):

            pass

    rings = parcel_boundary.get(
        "rings"
    )

    if not rings:

        return None

    first_coordinate = (
        get_first_coordinate(
            rings
        )
    )

    if first_coordinate is None:

        return None

    x_value, y_value = (
        first_coordinate
    )

    if (
        abs(x_value) <= 180
        and abs(y_value) <= 90
    ):

        return 4326

    return 2230


def parcel_geometry(
    parcel_boundary: dict | None
) -> tuple[dict, int] | None:

    if not isinstance(
        parcel_boundary,
        dict
    ):

        return None

    rings = parcel_boundary.get(
        "rings"
    )

    if not rings:

        return None

    wkid = detect_parcel_wkid(
        parcel_boundary
    )

    if wkid is None:

        return None

    return (
        {
            "rings": rings,
            "spatialReference": {
                "wkid": wkid
            }
        },
        wkid
    )


def execute_arcgis_query(
    url: str,
    params: dict,
    use_post: bool = True
) -> list[dict]:

    if use_post:

        response = requests.post(
            url,
            data=params,
            timeout=30
        )

    else:

        response = requests.get(
            url,
            params=params,
            timeout=30
        )

    response.raise_for_status()

    data = response.json()

    if data.get("error"):

        raise requests.RequestException(
            str(
                data.get(
                    "error"
                )
            )
        )

    return [
        feature.get(
            "attributes",
            {}
        )
        for feature in data.get(
            "features",
            []
        )
    ]


def query_polygon_layer(
    url: str,
    parcel_boundary: dict | None,
    out_fields: str
) -> list[dict]:

    geometry_result = parcel_geometry(
        parcel_boundary
    )

    if geometry_result is None:

        return []

    geometry, wkid = geometry_result

    params = {
        "where": "1=1",
        "geometry": json.dumps(
            geometry
        ),
        "geometryType": (
            "esriGeometryPolygon"
        ),
        "inSR": str(
            wkid
        ),
        "spatialRel": (
            "esriSpatialRelIntersects"
        ),
        "outFields": out_fields,
        "returnGeometry": "false",
        "f": "json"
    }

    return execute_arcgis_query(
        url=url,
        params=params,
        use_post=True
    )


def query_point_layer(
    url: str,
    latitude: float,
    longitude: float,
    out_fields: str
) -> list[dict]:

    params = {
        "where": "1=1",
        "geometry": (
            f"{longitude},{latitude}"
        ),
        "geometryType": (
            "esriGeometryPoint"
        ),
        "inSR": "4326",
        "spatialRel": (
            "esriSpatialRelIntersects"
        ),
        "outFields": out_fields,
        "returnGeometry": "false",
        "f": "json"
    }

    return execute_arcgis_query(
        url=url,
        params=params,
        use_post=False
    )


def query_layer_with_fallback(
    url: str,
    latitude: float,
    longitude: float,
    parcel_boundary: dict | None,
    out_fields: str
) -> tuple[
    list[dict],
    str,
    str | None
]:

    parcel_wide = (
        isinstance(
            parcel_boundary,
            dict
        )
        and bool(
            parcel_boundary.get(
                "rings"
            )
        )
    )

    polygon_error = None

    if parcel_wide:

        try:

            records = (
                query_polygon_layer(
                    url=url,
                    parcel_boundary=(
                        parcel_boundary
                    ),
                    out_fields=out_fields
                )
            )

            return (
                records,
                "parcel_polygon_intersection",
                None
            )

        except (
            requests.Timeout,
            requests.RequestException,
            ValueError
        ) as error:

            polygon_error = str(
                error
            )

    try:

        records = query_point_layer(
            url=url,
            latitude=latitude,
            longitude=longitude,
            out_fields=out_fields
        )

        return (
            records,
            "parcel_point_fallback",
            polygon_error
        )

    except requests.Timeout:

        return (
            [],
            "failed",
            (
                "The GIS service timed out."
                if polygon_error is None
                else (
                    "Parcel-polygon query failed "
                    f"({polygon_error}); point fallback "
                    "also timed out."
                )
            )
        )

    except (
        requests.RequestException,
        ValueError
    ) as error:

        return (
            [],
            "failed",
            (
                f"The GIS service returned an error: {error}"
                if polygon_error is None
                else (
                    "Parcel-polygon query failed "
                    f"({polygon_error}); point fallback "
                    f"also failed ({error})."
                )
            )
        )


def format_open_space_easement(
    attributes: dict
) -> dict:

    document_year = clean_text(
        attributes.get(
            "DOCYR"
        )
    )

    document_number = clean_text(
        attributes.get(
            "DOCNO"
        )
    )

    recorded_document = None

    if (
        document_year
        and document_number
    ):

        recorded_document = (
            f"{document_year}-"
            f"{document_number}"
        )

    elif document_number:

        recorded_document = (
            document_number
        )

    return {
        "easement_id": attributes.get(
            "EASEID"
        ),
        "recorded_document": (
            recorded_document
        ),
        "recorded_date": clean_text(
            attributes.get(
                "RECDATE"
            )
        ),
        "posting_id": clean_text(
            attributes.get(
                "POSTID"
            )
        ),
        "subdivision_id": (
            attributes.get(
                "SUBDIVID"
            )
        ),
        "subtype_code": (
            attributes.get(
                "SUB_TYPE"
            )
        ),
        "drawing": clean_text(
            attributes.get(
                "DRAWING"
            )
        ),
        "pending": clean_text(
            attributes.get(
                "PENDING"
            )
        )
    }


def format_wastewater_easement(
    attributes: dict
) -> dict:

    return {
        "document_number": clean_text(
            attributes.get(
                "DOCUMENT_NUMBER"
            )
        ),
        "recorded_date": (
            parse_arcgis_date(
                attributes.get(
                    "DATE_RECORDED"
                )
            )
        ),
        "asbuilt_file": clean_text(
            attributes.get(
                "ASBUILT_FILE"
            )
        )
    }


def empty_easement_result(
    status: str,
    message: str
) -> dict:

    return {
        "open_space_easement_screened": False,
        "open_space_easement_found": None,
        "open_space_easement_count": 0,
        "open_space_easements": [],
        "open_space_lookup_method": "failed",
        "wastewater_easement_screened": False,
        "wastewater_easement_found": None,
        "wastewater_easement_count": 0,
        "wastewater_easements": [],
        "wastewater_lookup_method": "failed",
        "access_easement_screened": False,
        "access_easement_found": None,
        "legal_access_confirmed": False,
        "title_review_required": True,
        "constraint_level": "unknown",
        "status": status,
        "source": (
            "County of San Diego and SanGIS "
            "recorded-easement GIS layers"
        ),
        "message": message,
        "analysis_scope": (
            "partial_recorded_easement_gis_screening"
        )
    }


def get_easement_screening_data(
    latitude: float,
    longitude: float,
    parcel_boundary: dict | None = None
) -> dict:

    (
        open_space_attributes,
        open_space_lookup_method,
        open_space_error
    ) = query_layer_with_fallback(
        url=OPEN_SPACE_EASEMENT_URL,
        latitude=latitude,
        longitude=longitude,
        parcel_boundary=parcel_boundary,
        out_fields=(
            "POSTID,POSTDATE,EASEID,"
            "JURISDIC,SUBDIVID,DOCYR,"
            "DOCNO,RECDATE,SUB_TYPE,"
            "PENDING,DRAWING"
        )
    )

    (
        wastewater_attributes,
        wastewater_lookup_method,
        wastewater_error
    ) = query_layer_with_fallback(
        url=WASTEWATER_EASEMENT_URL,
        latitude=latitude,
        longitude=longitude,
        parcel_boundary=parcel_boundary,
        out_fields=(
            "DOCUMENT_NUMBER,"
            "DATE_RECORDED,"
            "ASBUILT_FILE"
        )
    )

    open_space_easements = [
        format_open_space_easement(
            attributes
        )
        for attributes in (
            open_space_attributes
        )
    ]

    wastewater_easements = [
        format_wastewater_easement(
            attributes
        )
        for attributes in (
            wastewater_attributes
        )
    ]

    open_space_screened = (
        open_space_lookup_method
        != "failed"
    )

    wastewater_screened = (
        wastewater_lookup_method
        != "failed"
    )

    if (
        not open_space_screened
        and not wastewater_screened
    ):

        return empty_easement_result(
            status="error",
            message=" ".join(
                value
                for value in [
                    open_space_error,
                    wastewater_error
                ]
                if value
            )
        )

    messages = []

    if open_space_screened:

        if open_space_easements:

            messages.append(
                (
                    f"{len(open_space_easements)} mapped "
                    "recorded open-space or conservation-type "
                    "easement feature(s) were identified."
                )
            )

        else:

            messages.append(
                (
                    "No mapped recorded open-space, "
                    "conservation, biological, recreational, "
                    "agricultural-conservation, pedestrian, "
                    "or equestrian easement feature was "
                    "identified."
                )
            )

        if (
            open_space_lookup_method
            == "parcel_point_fallback"
        ):

            messages.append(
                (
                    "The open-space easement parcel-polygon "
                    "query failed, so Housing OS used the parcel "
                    "lookup point as a fallback. This fallback "
                    "can miss an easement that crosses another "
                    "part of the parcel."
                )
            )

    elif open_space_error:

        messages.append(
            open_space_error
        )

    if wastewater_screened:

        if wastewater_easements:

            messages.append(
                (
                    f"{len(wastewater_easements)} mapped "
                    "County wastewater easement feature(s) "
                    "were identified."
                )
            )

        else:

            messages.append(
                (
                    "No mapped County wastewater easement "
                    "feature was identified."
                )
            )

        if (
            wastewater_lookup_method
            == "parcel_point_fallback"
        ):

            messages.append(
                (
                    "The wastewater easement parcel-polygon "
                    "query failed, so Housing OS used the parcel "
                    "lookup point as a fallback. This fallback "
                    "can miss an easement that crosses another "
                    "part of the parcel."
                )
            )

    elif wastewater_error:

        messages.append(
            wastewater_error
        )

    messages.append(
        (
            "These GIS layers do not provide a complete "
            "title-level inventory of access, road, utility, "
            "private, or other recorded easements. The SanGIS "
            "open-space easement layer is explicitly incomplete. "
            "A title report and recorded documents are still "
            "required to determine legal access and all "
            "easement rights or burdens."
        )
    )

    constraint_level = "unknown"

    if (
        open_space_easements
        or wastewater_easements
    ):

        constraint_level = "review"

    return {
        "open_space_easement_screened": (
            open_space_screened
        ),
        "open_space_easement_found": (
            bool(
                open_space_easements
            )
            if open_space_screened
            else None
        ),
        "open_space_easement_count": len(
            open_space_easements
        ),
        "open_space_easements": (
            open_space_easements
        ),
        "open_space_lookup_method": (
            open_space_lookup_method
        ),
        "wastewater_easement_screened": (
            wastewater_screened
        ),
        "wastewater_easement_found": (
            bool(
                wastewater_easements
            )
            if wastewater_screened
            else None
        ),
        "wastewater_easement_count": len(
            wastewater_easements
        ),
        "wastewater_easements": (
            wastewater_easements
        ),
        "wastewater_lookup_method": (
            wastewater_lookup_method
        ),
        "access_easement_screened": False,
        "access_easement_found": None,
        "legal_access_confirmed": False,
        "title_review_required": True,
        "constraint_level": (
            constraint_level
        ),
        "status": "found",
        "source": (
            "SanGIS Recorded Open Space Easements "
            "and County of San Diego Wastewater "
            "Easement GIS"
        ),
        "message": " ".join(
            messages
        ),
        "analysis_scope": (
            "partial_recorded_easement_gis_screening"
        )
    }