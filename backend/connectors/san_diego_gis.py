import math
import re
import time

import requests
from pyproj import Transformer

from address_parser import parse_address


ADDRESS_URL = (
    "https://gis-public.sandiegocounty.gov/arcgis/rest/services/"
    "sdep_warehouse/ADDRAPN/FeatureServer/0/query"
)

PARCEL_URL = (
    "https://gis-public.sandiegocounty.gov/arcgis/rest/services/"
    "HCD/HCD_Map/FeatureServer/0/query"
)

# San Diego County State Plane (EPSG:2230) to GPS (EPSG:4326)
transformer = Transformer.from_crs(
    "EPSG:2230",
    "EPSG:4326",
    always_xy=True
)

to_state_plane = Transformer.from_crs(
    "EPSG:4326",
    "EPSG:2230",
    always_xy=True
)

PARCEL_BOUNDARY_SIMPLIFY_TOLERANCE_FEET = 5


GIS_MAX_ATTEMPTS = 3
GIS_CONNECT_TIMEOUT_SECONDS = 8
GIS_READ_TIMEOUT_SECONDS = 35
GIS_RETRY_BACKOFF_SECONDS = 1.25

RETRYABLE_HTTP_STATUS_CODES = {
    429,
    500,
    502,
    503,
    504
}


class GISRequestTimeout(Exception):
    pass


class GISRequestError(Exception):
    pass


def request_arcgis_json(
    url: str,
    params: dict,
    service_name: str
) -> dict:
    """
    Request ArcGIS JSON with a small retry/backoff policy.

    Retries:
    - timeouts
    - connection errors
    - common temporary HTTP failures
    - ArcGIS JSON errors with server-side 5xx codes

    It intentionally does not retry ordinary client/query errors.
    """

    last_error: Exception | None = None
    timed_out = False

    for attempt in range(
        1,
        GIS_MAX_ATTEMPTS + 1
    ):

        try:

            response = requests.get(
                url,
                params=params,
                timeout=(
                    GIS_CONNECT_TIMEOUT_SECONDS,
                    GIS_READ_TIMEOUT_SECONDS
                )
            )

            if (
                response.status_code
                in RETRYABLE_HTTP_STATUS_CODES
            ):
                raise requests.HTTPError(
                    (
                        f"{service_name} returned temporary "
                        f"HTTP {response.status_code}."
                    ),
                    response=response
                )

            response.raise_for_status()

            data = response.json()

            arcgis_error = data.get(
                "error"
            )

            if arcgis_error:

                error_code = arcgis_error.get(
                    "code"
                )

                error_message = arcgis_error.get(
                    "message"
                ) or str(
                    arcgis_error
                )

                if (
                    isinstance(
                        error_code,
                        int
                    )
                    and error_code >= 500
                ):
                    raise GISRequestError(
                        (
                            f"{service_name} returned temporary "
                            f"ArcGIS error {error_code}: "
                            f"{error_message}"
                        )
                    )

                raise RuntimeError(
                    str(
                        arcgis_error
                    )
                )

            return data

        except requests.Timeout as error:

            timed_out = True
            last_error = error

        except requests.ConnectionError as error:

            last_error = error

        except requests.HTTPError as error:

            status_code = (
                error.response.status_code
                if error.response is not None
                else None
            )

            if (
                status_code
                not in RETRYABLE_HTTP_STATUS_CODES
            ):
                raise

            last_error = error

        except GISRequestError as error:

            last_error = error

        except ValueError:
            raise

        if attempt < GIS_MAX_ATTEMPTS:

            time.sleep(
                GIS_RETRY_BACKOFF_SECONDS
                * attempt
            )

    if timed_out:

        raise GISRequestTimeout(
            (
                f"{service_name} timed out after "
                f"{GIS_MAX_ATTEMPTS} attempts."
            )
        ) from last_error

    raise GISRequestError(
        (
            f"{service_name} failed after "
            f"{GIS_MAX_ATTEMPTS} attempts: "
            f"{last_error}"
        )
    ) from last_error


def clean_apn(
    apn: str | None
) -> str | None:

    if apn is None:
        return None

    digits = "".join(
        character
        for character in str(apn)
        if character.isdigit()
    )

    if len(digits) != 10:
        return None

    return digits


def escape_sql_text(
    value: str
) -> str:

    return value.replace(
        "'",
        "''"
    )


def perpendicular_distance(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float]
) -> float:

    if start == end:

        return math.hypot(
            point[0] - start[0],
            point[1] - start[1]
        )

    numerator = abs(
        (
            end[1] - start[1]
        ) * point[0]
        - (
            end[0] - start[0]
        ) * point[1]
        + end[0] * start[1]
        - end[1] * start[0]
    )

    denominator = math.hypot(
        end[1] - start[1],
        end[0] - start[0]
    )

    return numerator / denominator


def simplify_open_line(
    points: list[tuple[float, float]],
    tolerance_feet: float
) -> list[tuple[float, float]]:

    if len(points) <= 2:
        return points

    maximum_distance = 0.0
    maximum_index = 0

    start = points[0]
    end = points[-1]

    for index in range(
        1,
        len(points) - 1
    ):

        distance = perpendicular_distance(
            point=points[index],
            start=start,
            end=end
        )

        if distance > maximum_distance:

            maximum_distance = distance
            maximum_index = index

    if maximum_distance <= tolerance_feet:

        return [
            start,
            end
        ]

    first_half = simplify_open_line(
        points=points[
            :maximum_index + 1
        ],
        tolerance_feet=tolerance_feet
    )

    second_half = simplify_open_line(
        points=points[
            maximum_index:
        ],
        tolerance_feet=tolerance_feet
    )

    return (
        first_half[:-1]
        + second_half
    )


def simplify_closed_ring(
    points: list[tuple[float, float]],
    tolerance_feet: float
) -> list[tuple[float, float]]:

    if len(points) <= 4:
        return points

    first_point = points[0]

    split_index = max(
        range(
            1,
            len(points)
        ),
        key=lambda index: math.hypot(
            points[index][0] - first_point[0],
            points[index][1] - first_point[1]
        )
    )

    first_chain = points[
        :split_index + 1
    ]

    second_chain = (
        points[
            split_index:
        ]
        + [
            first_point
        ]
    )

    simplified_first = simplify_open_line(
        points=first_chain,
        tolerance_feet=tolerance_feet
    )

    simplified_second = simplify_open_line(
        points=second_chain,
        tolerance_feet=tolerance_feet
    )

    simplified = (
        simplified_first[:-1]
        + simplified_second[:-1]
    )

    cleaned = []

    for point in simplified:

        if (
            not cleaned
            or math.hypot(
                point[0] - cleaned[-1][0],
                point[1] - cleaned[-1][1]
            ) >= 1
        ):

            cleaned.append(
                point
            )

    if len(cleaned) < 3:
        return points

    return cleaned


def get_primary_wgs84_ring(
    parcel_boundary: dict | None
) -> list[list[float]]:

    if not isinstance(parcel_boundary, dict):
        return []

    rings = parcel_boundary.get(
        "rings",
        []
    )

    if not rings:
        return []

    primary_ring = max(
        rings,
        key=len
    )

    cleaned = []

    for point in primary_ring:

        try:
            longitude = float(point[0])
            latitude = float(point[1])

        except (
            TypeError,
            ValueError,
            IndexError
        ):
            continue

        cleaned.append(
            [
                longitude,
                latitude
            ]
        )

    if len(cleaned) < 3:
        return []

    if cleaned[0] != cleaned[-1]:
        cleaned.append(
            cleaned[0]
        )

    return cleaned


def get_simplified_wgs84_ring(
    parcel_boundary: dict | None
) -> list[list[float]]:

    raw_ring = get_primary_wgs84_ring(
        parcel_boundary
    )

    if len(raw_ring) < 4:
        return []

    open_ring = raw_ring[:-1]

    projected_points = [
        to_state_plane.transform(
            point[0],
            point[1]
        )
        for point in open_ring
    ]

    simplified_projected = simplify_closed_ring(
        points=projected_points,
        tolerance_feet=(
            PARCEL_BOUNDARY_SIMPLIFY_TOLERANCE_FEET
        )
    )

    simplified_wgs84 = [
        list(
            transformer.transform(
                point[0],
                point[1]
            )
        )
        for point in simplified_projected
    ]

    if (
        simplified_wgs84
        and simplified_wgs84[0] != simplified_wgs84[-1]
    ):
        simplified_wgs84.append(
            simplified_wgs84[0]
        )

    return simplified_wgs84


def line_feature_from_edge(
    ring: list[list[float]],
    edge_index: int | None,
    properties: dict
) -> dict | None:

    if edge_index is None:
        return None

    if len(ring) < 4:
        return None

    open_ring = ring[:-1]

    if not open_ring:
        return None

    if (
        edge_index < 0
        or edge_index >= len(open_ring)
    ):
        return None

    start = open_ring[
        edge_index
    ]

    end = open_ring[
        (edge_index + 1) % len(open_ring)
    ]

    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {
            "type": "LineString",
            "coordinates": [
                start,
                end
            ]
        }
    }


def build_map_geometry(
    parcel_boundary: dict | None,
    latitude: float,
    longitude: float,
    road_access: dict | None,
    buildable_area: dict | None = None,
    terrain: dict | None = None
) -> dict:

    raw_ring = get_primary_wgs84_ring(
        parcel_boundary
    )

    simplified_ring = get_simplified_wgs84_ring(
        parcel_boundary
    )

    if not raw_ring:

        return {
            "simplified_parcel_boundary": None,
            "parcel_center": {
                "type": "Feature",
                "properties": {
                    "role": "parcel_lookup_point"
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [
                        longitude,
                        latitude
                    ]
                }
            },
            "frontage_edge": None,
            "rear_edge": None,
            "setback_envelope": None,
            "slope_samples": None,
            "slope_zones": None,
            "bounds": None,
            "status": "not_available",
            "source": (
                "County of San Diego Assessor Parcels "
                "and Housing OS frontage screening"
            ),
            "message": (
                "A usable parcel polygon was not available "
                "for map geometry."
            ),
            "disclaimer": (
                "Map geometry is preliminary screening data "
                "and is not a boundary or land survey."
            )
        }

    longitudes = [
        point[0]
        for point in raw_ring
    ]

    latitudes = [
        point[1]
        for point in raw_ring
    ]

    road_access = road_access or {}

    frontage_edge = line_feature_from_edge(
        ring=simplified_ring,
        edge_index=road_access.get(
            "frontage_edge_index"
        ),
        properties={
            "role": "probable_frontage_edge",
            "road_name": road_access.get(
                "frontage_road_name"
            ),
            "confidence": road_access.get(
                "frontage_confidence"
            ),
            "legal_frontage_confirmed": False
        }
    )

    rear_edge = line_feature_from_edge(
        ring=simplified_ring,
        edge_index=road_access.get(
            "rear_edge_index"
        ),
        properties={
            "role": "probable_rear_edge",
            "confidence": road_access.get(
                "frontage_confidence"
            )
        }
    )

    buildable_area = buildable_area or {}
    terrain = terrain or {}

    setback_envelope = buildable_area.get(
        "setback_envelope_geojson"
    )

    slope_samples = terrain.get(
        "slope_sample_geojson"
    )

    slope_zones = terrain.get(
        "slope_zone_geojson"
    )

    return {
        "simplified_parcel_boundary": {
            "type": "Feature",
            "properties": {
                "role": "simplified_analysis_boundary",
                "simplification_tolerance_feet": (
                    PARCEL_BOUNDARY_SIMPLIFY_TOLERANCE_FEET
                )
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    simplified_ring
                ]
            }
        },
        "parcel_center": {
            "type": "Feature",
            "properties": {
                "role": "parcel_lookup_point"
            },
            "geometry": {
                "type": "Point",
                "coordinates": [
                    longitude,
                    latitude
                ]
            }
        },
        "frontage_edge": frontage_edge,
        "rear_edge": rear_edge,
        "setback_envelope": setback_envelope,
        "slope_samples": slope_samples,
        "slope_zones": slope_zones,
        "bounds": [
            min(longitudes),
            min(latitudes),
            max(longitudes),
            max(latitudes)
        ],
        "status": "found",
        "source": (
            "County of San Diego Assessor Parcels "
            "and Housing OS frontage screening"
        ),
        "message": (
            "Simplified parcel, setback, terrain-sample, "
            "and preliminary slope-zone GeoJSON generated "
            "for map visualization."
        ),
        "disclaimer": (
            "Simplified parcel, frontage, rear-edge, "
            "setback-envelope, terrain-sample, and "
            "slope-zone geometry is "
            "preliminary screening data. It is not a legal "
            "boundary survey, title determination, or legal "
            "frontage opinion."
        )
    }


def get_parcel_boundary(
    apn: str | None
) -> dict:

    normalized_apn = clean_apn(
        apn
    )

    if normalized_apn is None:

        return {
            "rings": [],
            "spatial_reference": 4326,
            "status": "invalid_apn",
            "source": (
                "County of San Diego Assessor Parcels"
            ),
            "message": (
                "A valid ten-digit APN was not available "
                "for parcel-boundary lookup."
            )
        }

    params = {
        "where": (
            "APN = "
            f"'{escape_sql_text(normalized_apn)}'"
        ),
        "outFields": "APN",
        "returnGeometry": "true",
        "outSR": 4326,
        "geometryPrecision": 7,
        "f": "json"
    }

    try:

        data = request_arcgis_json(
            url=PARCEL_URL,
            params=params,
            service_name=(
                "County parcel-boundary service"
            )
        )

    except GISRequestTimeout:

        return {
            "rings": [],
            "spatial_reference": 4326,
            "status": "timeout",
            "source": (
                "County of San Diego Assessor Parcels"
            ),
            "message": (
                "The parcel-boundary service timed out after "
                "multiple attempts. Housing OS will continue "
                "without parcel-wide geometry where possible."
            )
        }

    except (
        requests.RequestException,
        GISRequestError,
        RuntimeError
    ) as error:

        return {
            "rings": [],
            "spatial_reference": 4326,
            "status": "error",
            "source": (
                "County of San Diego Assessor Parcels"
            ),
            "message": str(error)
        }

    except ValueError:

        return {
            "rings": [],
            "spatial_reference": 4326,
            "status": "error",
            "source": (
                "County of San Diego Assessor Parcels"
            ),
            "message": (
                "The parcel-boundary service returned "
                "an invalid response."
            )
        }

    features = data.get(
        "features",
        []
    )

    if not features:

        return {
            "rings": [],
            "spatial_reference": 4326,
            "status": "not_found",
            "source": (
                "County of San Diego Assessor Parcels"
            ),
            "message": (
                "No parcel polygon was found for the APN."
            )
        }

    geometry = features[0].get(
        "geometry",
        {}
    )

    rings = geometry.get(
        "rings",
        []
    )

    if not rings:

        return {
            "rings": [],
            "spatial_reference": 4326,
            "status": "not_found",
            "source": (
                "County of San Diego Assessor Parcels"
            ),
            "message": (
                "The parcel record did not include a usable "
                "polygon boundary."
            )
        }

    return {
        "rings": rings,
        "spatial_reference": 4326,
        "status": "found",
        "source": (
            "County of San Diego Assessor Parcels"
        ),
        "message": (
            "Parcel polygon retrieved for preliminary "
            "parcel-wide sampling."
        )
    }


def get_parcel_data(
    address: str
):

    parsed = parse_address(
        address
    )

    if parsed is None:

        return {
            "address": address,
            "parcel_count": 0,
            "parcels": [],
            "source": "San Diego GIS",
            "status": "invalid_address",
            "message": (
                "The address could not be understood."
            )
        }

    def normalize_text(
        value
    ) -> str:

        if value is None:
            return ""

        normalized = str(
            value
        ).upper().strip()

        normalized = re.sub(
            r"[^A-Z0-9]+",
            " ",
            normalized
        )

        normalized = re.sub(
            r"\s+",
            " ",
            normalized
        ).strip()

        return normalized

    def request_features(
        where_clause: str
    ):

        params = {
            "where": where_clause,
            "outFields": "*",
            "returnGeometry": "true",
            "f": "json"
        }

        data = request_arcgis_json(
            url=ADDRESS_URL,
            params=params,
            service_name=(
                "San Diego County address-to-parcel service"
            )
        )

        return data.get(
            "features",
            []
        )

    street_name = escape_sql_text(
        parsed["street"]
    )

    street_suffix = escape_sql_text(
        parsed.get(
            "suffix",
            ""
        )
    )

    exact_where = (
        f"ADDRNMBR = {parsed['number']} "
        f"AND UPPER(ADDRNAME) = '{street_name}'"
    )

    if street_suffix:

        exact_where += (
            f" AND UPPER(ADDRSFX) = '{street_suffix}'"
        )

    try:

        features = request_features(
            exact_where
        )

        if not features:

            number_only_where = (
                f"ADDRNMBR = {parsed['number']}"
            )

            candidate_features = request_features(
                number_only_where
            )

            target_street = normalize_text(
                parsed["street"]
            )

            target_suffix = normalize_text(
                parsed.get(
                    "suffix",
                    ""
                )
            )

            if target_suffix:

                target_full = normalize_text(
                    f"{target_street} {target_suffix}"
                )

            else:

                target_full = target_street

            matched_features = []

            for feature in candidate_features:

                attrs = feature.get(
                    "attributes",
                    {}
                )

                candidate_name = normalize_text(
                    attrs.get(
                        "ADDRNAME"
                    )
                )

                candidate_suffix = normalize_text(
                    attrs.get(
                        "ADDRSFX"
                    )
                )

                candidate_full = normalize_text(
                    " ".join(
                        value
                        for value in [
                            candidate_name,
                            candidate_suffix
                        ]
                        if value
                    )
                )

                if (
                    candidate_name == target_street
                    or candidate_full == target_full
                    or (
                        not target_suffix
                        and candidate_full == target_street
                    )
                ):

                    matched_features.append(
                        feature
                    )

            features = matched_features

    except GISRequestTimeout:

        return {
            "address": address,
            "parcel_count": 0,
            "parcels": [],
            "source": "San Diego GIS",
            "status": "timeout",
            "message": (
                "The San Diego County GIS server did not "
                "respond after multiple attempts. Please try "
                "again in a moment."
            )
        }

    except (
        requests.RequestException,
        GISRequestError
    ) as error:

        return {
            "address": address,
            "parcel_count": 0,
            "parcels": [],
            "source": "San Diego GIS",
            "status": "service_error",
            "message": (
                "The San Diego County GIS service is "
                f"temporarily unavailable: {error}"
            )
        }

    except ValueError:

        return {
            "address": address,
            "parcel_count": 0,
            "parcels": [],
            "source": "San Diego GIS",
            "status": "invalid_response",
            "message": (
                "The GIS server returned an invalid response."
            )
        }

    except RuntimeError as error:

        return {
            "address": address,
            "parcel_count": 0,
            "parcels": [],
            "source": "San Diego GIS",
            "status": "query_error",
            "message": str(error)
        }

    parcels = []
    seen_parcels = set()

    for feature in features:

        attrs = feature.get(
            "attributes",
            {}
        )

        geometry = feature.get(
            "geometry"
        )

        if not geometry:
            continue

        try:

            longitude, latitude = transformer.transform(
                geometry["x"],
                geometry["y"]
            )

        except (
            KeyError,
            TypeError,
            ValueError
        ):
            continue

        address_number = attrs.get(
            "ADDRNMBR"
        )

        feature_street_name = attrs.get(
            "ADDRNAME"
        )

        feature_street_suffix = attrs.get(
            "ADDRSFX"
        )

        if address_number is not None:

            try:
                address_number = int(
                    address_number
                )

            except (TypeError, ValueError):
                pass

        parcel_address = " ".join(
            str(value)
            for value in [
                address_number,
                feature_street_name,
                feature_street_suffix
            ]
            if value not in [
                None,
                ""
            ]
        )

        apn = attrs.get(
            "APN"
        )

        parcel_key = (
            str(apn),
            round(
                longitude,
                7
            ),
            round(
                latitude,
                7
            )
        )

        if parcel_key in seen_parcels:
            continue

        seen_parcels.add(
            parcel_key
        )

        parcel_boundary = get_parcel_boundary(
            apn=apn
        )

        parcels.append({
            "apn": apn,
            "address": parcel_address,
            "zip": attrs.get("ADDRZIP"),
            "community": attrs.get("COMMUNITY"),
            "latitude": latitude,
            "longitude": longitude,
            "_parcel_boundary": parcel_boundary
        })

    if not parcels:

        return {
            "address": address,
            "parcel_count": 0,
            "parcels": [],
            "source": "San Diego GIS",
            "status": "not_found",
            "message": (
                "No matching parcel was found for this address. "
                "Housing OS understood the address, but the County "
                "GIS address layer did not return a matching parcel."
            )
        }

    return {
        "address": address,
        "parcel_count": len(parcels),
        "parcels": parcels,
        "source": "San Diego GIS",
        "status": "found",
        "message": None
    }