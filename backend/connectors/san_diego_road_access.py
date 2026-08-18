import json
import math

import requests
from pyproj import Transformer


ALL_ROADS_URL = (
    "https://gis-public.sandiegocounty.gov/arcgis/rest/services/"
    "sdep_warehouse/ROADS_ALL/FeatureServer/0/query"
)

COUNTY_MAINTAINED_ROADS_URL = (
    "https://gis-public.sandiegocounty.gov/arcgis/rest/services/"
    "DPLU/DPLU_Map/MapServer/23/query"
)


to_state_plane = Transformer.from_crs(
    "EPSG:4326",
    "EPSG:2230",
    always_xy=True
)


ROAD_QUERY_TIMEOUT_SECONDS = 12
ROAD_QUERY_ATTEMPTS = 2
MAINTAINED_ROAD_TIMEOUT_SECONDS = 5
FRONTAGE_SEARCH_DISTANCE_FEET = 150
FRONTAGE_EDGE_DISTANCE_LIMIT_FEET = 100
MAINTAINED_ROAD_SEARCH_DISTANCE_FEET = 500
PARCEL_BOUNDARY_SIMPLIFY_TOLERANCE_FEET = 5


SEGMENT_STATUS_VALUES = {
    "A": "Approved",
    "C": "Constructed",
    "M": "Maintained",
    "P": "Proposed",
    "U": "Unknown"
}


DEDICATION_STATUS_VALUES = {
    "A": "Abandoned",
    "D": "Dedicated",
    "O": "Offer for dedication",
    "P": "Private",
    "R": "Rejected",
    "U": "Unknown"
}


def clean_text(
    value
) -> str | None:

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


def normalize_road_name(
    value
) -> str | None:

    cleaned = clean_text(value)

    if cleaned is None:
        return None

    return " ".join(
        cleaned.upper().split()
    )


def interpret_yes_no(
    value
) -> bool | None:

    if value is None:
        return None

    if isinstance(value, bool):
        return value

    normalized = str(value).strip().upper()

    if normalized in {
        "Y",
        "YES",
        "TRUE",
        "T",
        "1"
    }:
        return True

    if normalized in {
        "N",
        "NO",
        "FALSE",
        "F",
        "0"
    }:
        return False

    return None


def interpret_segment_status(
    value
) -> str | None:

    cleaned = clean_text(value)

    if cleaned is None:
        return None

    return SEGMENT_STATUS_VALUES.get(
        cleaned.upper(),
        cleaned
    )


def interpret_dedication_status(
    value
) -> str | None:

    cleaned = clean_text(value)

    if cleaned is None:
        return None

    return DEDICATION_STATUS_VALUES.get(
        cleaned.upper(),
        cleaned
    )


def determine_road_type(
    dedication_status: str | None,
    road_name: str | None
) -> str | None:

    if dedication_status == "Private":
        return "private"

    normalized_name = normalize_road_name(
        road_name
    )

    if normalized_name == "PRIVATE RD":
        return "private"

    if dedication_status in {
        "Dedicated",
        "Offer for dedication"
    }:
        return "public_or_offered"

    if road_name:
        return "mapped_road"

    return None


def empty_frontage_result() -> dict:

    return {
        "frontage_edge_found": False,
        "frontage_road_name": None,
        "frontage_length_feet": None,
        "frontage_centerline_distance_feet": None,
        "frontage_confidence": None,
        "frontage_detection_method": None,
        "frontage_edge_index": None,
        "rear_edge_index": None,
        "rear_edge_length_feet": None
    }


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


def projected_boundary_points(
    parcel_boundary: dict | None
) -> list[tuple[float, float]]:

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

    points = []

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

        points.append(
            to_state_plane.transform(
                longitude,
                latitude
            )
        )

    if len(points) >= 2 and points[0] == points[-1]:
        points = points[:-1]

    return simplify_closed_ring(
        points=points,
        tolerance_feet=(
            PARCEL_BOUNDARY_SIMPLIFY_TOLERANCE_FEET
        )
    )


def parcel_search_envelope(
    parcel_boundary: dict | None
) -> dict | None:

    points = projected_boundary_points(
        parcel_boundary
    )

    if len(points) < 3:
        return None

    x_values = [
        point[0]
        for point in points
    ]

    y_values = [
        point[1]
        for point in points
    ]

    return {
        "xmin": min(x_values) - FRONTAGE_SEARCH_DISTANCE_FEET,
        "ymin": min(y_values) - FRONTAGE_SEARCH_DISTANCE_FEET,
        "xmax": max(x_values) + FRONTAGE_SEARCH_DISTANCE_FEET,
        "ymax": max(y_values) + FRONTAGE_SEARCH_DISTANCE_FEET,
        "spatialReference": {
            "wkid": 2230
        }
    }


def request_nearby_road_geometries(
    parcel_boundary: dict | None
) -> list[dict]:

    envelope = parcel_search_envelope(
        parcel_boundary
    )

    if envelope is None:
        return []

    params = {
        "where": "1=1",
        "geometry": json.dumps(
            envelope
        ),
        "geometryType": "esriGeometryEnvelope",
        "inSR": "2230",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": (
            "ROADSEGID,RD30FULL,RD20FULL,"
            "SEGSTAT,DEDSTAT,FIREDRIV"
        ),
        "returnGeometry": "true",
        "outSR": "2230",
        "resultRecordCount": 100,
        "f": "json"
    }

    last_error = None

    for attempt in range(
        ROAD_QUERY_ATTEMPTS
    ):

        try:

            response = requests.get(
                ALL_ROADS_URL,
                params=params,
                timeout=ROAD_QUERY_TIMEOUT_SECONDS
            )

            response.raise_for_status()

            try:
                data = response.json()

            except ValueError as error:

                raise requests.RequestException(
                    "The road GIS service returned a non-JSON response."
                ) from error

            if data.get("error"):

                error_data = data.get(
                    "error",
                    {}
                )

                message = error_data.get(
                    "message",
                    "The road GIS service returned an error."
                )

                details = error_data.get(
                    "details",
                    []
                )

                if details:

                    message = (
                        f"{message} "
                        f"{' '.join(str(item) for item in details)}"
                    )

                raise requests.RequestException(
                    message
                )

            return data.get(
                "features",
                []
            )

        except (
            requests.Timeout,
            requests.RequestException
        ) as error:

            last_error = error

            if attempt == (
                ROAD_QUERY_ATTEMPTS - 1
            ):
                raise

    if last_error is not None:
        raise last_error

    return []

def request_maintained_road(
    latitude: float,
    longitude: float
) -> tuple[dict | None, int | None]:

    x, y = to_state_plane.transform(
        longitude,
        latitude
    )

    params = {
        "where": "1=1",
        "geometry": f"{x},{y}",
        "geometryType": "esriGeometryPoint",
        "inSR": "2230",
        "spatialRel": "esriSpatialRelIntersects",
        "distance": MAINTAINED_ROAD_SEARCH_DISTANCE_FEET,
        "units": "esriSRUnit_Foot",
        "outFields": (
            "ROAD_NAME,JURISDICTION,"
            "ASSET_STATUS,ADOPT_ROAD_STATUS,"
            "FROM_STREET,TO_STREET,"
            "PAVEMENT_CONDITION_INDEX"
        ),
        "returnGeometry": "false",
        "resultRecordCount": 10,
        "f": "json"
    }

    response = requests.get(
        COUNTY_MAINTAINED_ROADS_URL,
        params=params,
        timeout=MAINTAINED_ROAD_TIMEOUT_SECONDS
    )

    response.raise_for_status()

    try:
        data = response.json()

    except ValueError as error:

        raise requests.RequestException(
            "The maintained-road GIS service returned "
            "a non-JSON response."
        ) from error

    if data.get("error"):

        raise requests.RequestException(
            str(data["error"])
        )

    features = data.get(
        "features",
        []
    )

    if not features:
        return None, None

    return (
        features[0].get(
            "attributes",
            {}
        ),
        MAINTAINED_ROAD_SEARCH_DISTANCE_FEET
    )



def request_maintained_road_geometries(
    parcel_boundary: dict | None
) -> list[dict]:

    envelope = parcel_search_envelope(
        parcel_boundary
    )

    if envelope is None:
        return []

    params = {
        "where": "1=1",
        "geometry": json.dumps(
            envelope
        ),
        "geometryType": "esriGeometryEnvelope",
        "inSR": "2230",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": (
            "ROAD_NAME,JURISDICTION,"
            "ASSET_STATUS,ADOPT_ROAD_STATUS"
        ),
        "returnGeometry": "true",
        "outSR": "2230",
        "resultRecordCount": 100,
        "f": "json"
    }

    response = requests.get(
        COUNTY_MAINTAINED_ROADS_URL,
        params=params,
        timeout=MAINTAINED_ROAD_TIMEOUT_SECONDS
    )

    response.raise_for_status()

    try:
        data = response.json()

    except ValueError as error:

        raise requests.RequestException(
            "The maintained-road geometry service returned "
            "a non-JSON response."
        ) from error

    if data.get("error"):

        raise requests.RequestException(
            str(data["error"])
        )

    return data.get(
        "features",
        []
    )

def projected_parcel_edges(
    parcel_boundary: dict | None
) -> list[dict]:

    points = projected_boundary_points(
        parcel_boundary
    )

    if len(points) < 3:
        return []

    edges = []

    for index in range(len(points)):

        start = points[index]
        end = points[
            (index + 1) % len(points)
        ]

        length = math.hypot(
            end[0] - start[0],
            end[1] - start[1]
        )

        if length < 1:
            continue

        edges.append({
            "index": index,
            "start": start,
            "end": end,
            "midpoint": (
                (start[0] + end[0]) / 2,
                (start[1] + end[1]) / 2
            ),
            "length_feet": length
        })

    return edges


def geometry_segments(
    feature: dict
) -> list[
    tuple[
        tuple[float, float],
        tuple[float, float]
    ]
]:

    geometry = feature.get(
        "geometry",
        {}
    )

    segments = []

    for path in geometry.get(
        "paths",
        []
    ):

        for index in range(
            len(path) - 1
        ):

            try:
                start = (
                    float(path[index][0]),
                    float(path[index][1])
                )

                end = (
                    float(path[index + 1][0]),
                    float(path[index + 1][1])
                )

            except (
                TypeError,
                ValueError,
                IndexError
            ):
                continue

            segments.append(
                (
                    start,
                    end
                )
            )

    return segments


def point_to_segment_distance(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float]
) -> float:

    segment_x = end[0] - start[0]
    segment_y = end[1] - start[1]

    length_squared = (
        segment_x ** 2
        + segment_y ** 2
    )

    if length_squared == 0:

        return math.hypot(
            point[0] - start[0],
            point[1] - start[1]
        )

    projection = (
        (
            point[0] - start[0]
        ) * segment_x
        + (
            point[1] - start[1]
        ) * segment_y
    ) / length_squared

    projection = max(
        0,
        min(
            1,
            projection
        )
    )

    closest_x = (
        start[0]
        + projection * segment_x
    )

    closest_y = (
        start[1]
        + projection * segment_y
    )

    return math.hypot(
        point[0] - closest_x,
        point[1] - closest_y
    )


def point_to_feature_distance(
    point: tuple[float, float],
    feature: dict
) -> float | None:

    segments = geometry_segments(
        feature
    )

    if not segments:
        return None

    return min(
        point_to_segment_distance(
            point=point,
            start=start,
            end=end
        )
        for start, end in segments
    )


def edge_to_feature_distance(
    edge: dict,
    feature: dict
) -> float | None:

    segments = geometry_segments(
        feature
    )

    if not segments:
        return None

    sample_points = [
        edge["start"],
        edge["midpoint"],
        edge["end"]
    ]

    return min(
        point_to_segment_distance(
            point=point,
            start=start,
            end=end
        )
        for point in sample_points
        for start, end in segments
    )


def parcel_center(
    parcel_boundary: dict | None
) -> tuple[float, float] | None:

    points = projected_boundary_points(
        parcel_boundary
    )

    if not points:
        return None

    return (
        sum(point[0] for point in points) / len(points),
        sum(point[1] for point in points) / len(points)
    )


def road_name_from_feature(
    feature: dict
) -> str | None:

    attributes = feature.get(
        "attributes",
        {}
    )

    return (
        clean_text(
            attributes.get("RD30FULL")
        )
        or clean_text(
            attributes.get("RD20FULL")
        )
        or clean_text(
            attributes.get("ROAD_NAME")
        )
    )


def nearest_road_feature(
    parcel_boundary: dict | None,
    road_features: list[dict]
) -> tuple[dict | None, float | None]:

    center = parcel_center(
        parcel_boundary
    )

    if center is None:
        return None, None

    candidates = []

    for feature in road_features:

        distance = point_to_feature_distance(
            point=center,
            feature=feature
        )

        if distance is None:
            continue

        candidates.append(
            (
                feature,
                distance
            )
        )

    if not candidates:
        return None, None

    return min(
        candidates,
        key=lambda item: item[1]
    )


def detect_frontage(
    parcel_boundary: dict | None,
    road_features: list[dict]
) -> dict:

    edges = projected_parcel_edges(
        parcel_boundary
    )

    if not edges or not road_features:
        return empty_frontage_result()

    candidates = []

    for feature in road_features:

        for edge in edges:

            distance = edge_to_feature_distance(
                edge=edge,
                feature=feature
            )

            if distance is None:
                continue

            candidates.append({
                "edge": edge,
                "distance": distance,
                "road_name": road_name_from_feature(
                    feature
                )
            })

    if not candidates:
        return empty_frontage_result()

    best = min(
        candidates,
        key=lambda item: item["distance"]
    )

    if best["distance"] > (
        FRONTAGE_EDGE_DISTANCE_LIMIT_FEET
    ):

        result = empty_frontage_result()

        result.update({
            "frontage_road_name": best["road_name"],
            "frontage_centerline_distance_feet": round(
                best["distance"],
                1
            ),
            "frontage_confidence": "low",
            "frontage_detection_method": (
                "simplified_parcel_edge_to_road_centerline_envelope"
            )
        })

        return result

    center = parcel_center(
        parcel_boundary
    )

    if center is None:
        return empty_frontage_result()

    frontage_midpoint = best[
        "edge"
    ]["midpoint"]

    frontage_vector = (
        frontage_midpoint[0] - center[0],
        frontage_midpoint[1] - center[1]
    )

    rear_edge = min(
        edges,
        key=lambda edge: (
            (
                edge["midpoint"][0]
                - center[0]
            ) * frontage_vector[0]
            + (
                edge["midpoint"][1]
                - center[1]
            ) * frontage_vector[1]
        )
    )

    if best["distance"] <= 40:
        confidence = "high"

    elif best["distance"] <= 70:
        confidence = "medium"

    else:
        confidence = "low"

    return {
        "frontage_edge_found": True,
        "frontage_road_name": best["road_name"],
        "frontage_length_feet": round(
            best["edge"]["length_feet"],
            1
        ),
        "frontage_centerline_distance_feet": round(
            best["distance"],
            1
        ),
        "frontage_confidence": confidence,
        "frontage_detection_method": (
            "simplified_parcel_edge_to_road_centerline_envelope"
        ),
        "frontage_edge_index": best[
            "edge"
        ]["index"],
        "rear_edge_index": rear_edge[
            "index"
        ],
        "rear_edge_length_feet": round(
            rear_edge["length_feet"],
            1
        )
    }


def roads_appear_to_match(
    nearest_road_name: str | None,
    maintained_road_name: str | None
) -> bool:

    nearest_name = normalize_road_name(
        nearest_road_name
    )

    maintained_name = normalize_road_name(
        maintained_road_name
    )

    return bool(
        nearest_name
        and maintained_name
        and nearest_name == maintained_name
    )


def determine_access_screening(
    mapped_road_found: bool,
    nearest_road_type: str | None,
    county_maintained_road_found: bool,
    nearest_road_is_county_maintained: bool,
    frontage_edge_found: bool,
    frontage_confidence: str | None
) -> dict:

    if not mapped_road_found:

        if county_maintained_road_found:

            return {
                "preliminary_access_level": (
                    "county_road_nearby_frontage_unknown"
                ),
                "constraint_level": "moderate",
                "development_warning": (
                    "A County-maintained road was identified within "
                    "500 feet, but the general road-centerline "
                    "screening was unavailable or found no matching "
                    "road. Direct frontage and legal access remain "
                    "unconfirmed."
                )
            }

        return {
            "preliminary_access_level": "poor_or_unknown",
            "constraint_level": "major",
            "development_warning": (
                "No usable mapped road-centerline result was "
                "available near the parcel. Legal and physical "
                "access require direct review."
            )
        }

    if (
        frontage_edge_found
        and frontage_confidence in {
            "high",
            "medium"
        }
    ):

        if nearest_road_type == "private":

            return {
                "preliminary_access_level": (
                    "probable_private_road_frontage"
                ),
                "constraint_level": "moderate",
                "development_warning": (
                    "A parcel edge appears to face a mapped private "
                    "road. This does not establish legal access, "
                    "recorded easements, maintenance rights, driveway "
                    "approval, or emergency-access compliance."
                )
            }

        if nearest_road_is_county_maintained:

            return {
                "preliminary_access_level": (
                    "probable_county_road_frontage"
                ),
                "constraint_level": "low",
                "development_warning": (
                    "A parcel edge appears to face a mapped road "
                    "whose name matches a nearby County-maintained "
                    "road. Legal frontage, right-of-way width, and "
                    "driveway approval remain unconfirmed."
                )
            }

        return {
            "preliminary_access_level": (
                "probable_mapped_road_frontage"
            ),
            "constraint_level": "unknown",
            "development_warning": (
                "A parcel edge appears to face a mapped road. "
                "Legal frontage, right-of-way width, driveway "
                "approval, and recorded access rights remain "
                "unconfirmed."
            )
        }

    if nearest_road_type == "private":

        return {
            "preliminary_access_level": (
                "private_road_nearby"
            ),
            "constraint_level": "moderate",
            "development_warning": (
                "The nearest mapped road appears to be private. "
                "Parcel frontage, easements, maintenance rights, "
                "driveway access, and emergency access remain "
                "unconfirmed."
            )
        }

    if nearest_road_is_county_maintained:

        return {
            "preliminary_access_level": (
                "county_maintained_road_nearby"
            ),
            "constraint_level": "low",
            "development_warning": (
                "The nearest mapped road name matches a nearby "
                "County-maintained road, but direct legal frontage "
                "and driveway approval remain unconfirmed."
            )
        }

    return {
        "preliminary_access_level": (
            "mapped_road_nearby"
        ),
        "constraint_level": "unknown",
        "development_warning": (
            "A mapped road was identified near the parcel, but "
            "direct frontage, legal access, road standards, and "
            "driveway approval remain unconfirmed."
        )
    }


def get_road_access_data(
    latitude: float,
    longitude: float,
    parcel_boundary: dict | None = None
) -> dict:

    road_features = []
    maintained_features = []
    maintained_attributes = None
    maintained_distance = None

    nearest_road_lookup_status = "not_run"
    maintained_road_lookup_status = "not_run"
    frontage_lookup_status = "not_run"

    lookup_messages = []

    try:

        road_features = request_nearby_road_geometries(
            parcel_boundary=parcel_boundary
        )

        nearest_road_lookup_status = (
            "found"
            if road_features
            else "not_found"
        )

    except requests.Timeout:

        nearest_road_lookup_status = "timeout"

        lookup_messages.append(
            "The general road-centerline lookup timed out "
            "after retrying."
        )

    except requests.RequestException as error:

        nearest_road_lookup_status = "error"

        lookup_messages.append(
            f"General road lookup error: {error}"
        )

    try:

        maintained_features = (
            request_maintained_road_geometries(
                parcel_boundary=parcel_boundary
            )
        )

        maintained_road_lookup_status = (
            "found"
            if maintained_features
            else "not_found"
        )

    except requests.Timeout:

        maintained_road_lookup_status = "timeout"

        lookup_messages.append(
            "The County-maintained-road geometry lookup timed out."
        )

    except requests.RequestException as error:

        maintained_road_lookup_status = "error"

        lookup_messages.append(
            f"County-maintained-road geometry error: {error}"
        )

    if maintained_features:

        # Pick the maintained-road feature nearest the parcel center
        # instead of blindly taking the first feature returned.
        maintained_feature, maintained_feature_distance = (
            nearest_road_feature(
                parcel_boundary=parcel_boundary,
                road_features=maintained_features
            )
        )

        if maintained_feature:

            maintained_attributes = maintained_feature.get(
                "attributes",
                {}
            )

            maintained_distance = (
                round(
                    maintained_feature_distance
                )
                if maintained_feature_distance is not None
                else MAINTAINED_ROAD_SEARCH_DISTANCE_FEET
            )

    elif maintained_road_lookup_status in {
        "not_found",
        "timeout",
        "error"
    }:

        try:

            (
                maintained_attributes,
                maintained_distance
            ) = request_maintained_road(
                latitude=latitude,
                longitude=longitude
            )

            if maintained_attributes is not None:
                maintained_road_lookup_status = "found"

        except requests.Timeout:

            if maintained_road_lookup_status != "found":

                maintained_road_lookup_status = "timeout"

            lookup_messages.append(
                "The fallback County-maintained-road lookup timed out."
            )

        except requests.RequestException as error:

            if maintained_road_lookup_status != "found":

                maintained_road_lookup_status = "error"

            lookup_messages.append(
                f"Fallback maintained-road lookup error: {error}"
            )

    # IMPORTANT:
    # Only the general SanGIS road layer is allowed to establish the
    # nearest mapped road and probable frontage. The County-maintained
    # road layer is used only to corroborate maintenance status.
    #
    # This prevents the result from changing from PRIVATE RD to PENN ST
    # merely because the general road service timed out.
    frontage_features = road_features

    if road_features:

        frontage_lookup_status = "found"

    elif nearest_road_lookup_status == "timeout":

        frontage_lookup_status = "unavailable"

    elif nearest_road_lookup_status == "error":

        frontage_lookup_status = "unavailable"

    else:

        frontage_lookup_status = "not_found"

    nearest_feature, nearest_distance = (
        nearest_road_feature(
            parcel_boundary=parcel_boundary,
            road_features=road_features
        )
    )

    frontage = detect_frontage(
        parcel_boundary=parcel_boundary,
        road_features=road_features
    )

    nearest_road_name = None
    road_segment_status = None
    road_dedication_status = None
    fire_drivable = None

    if nearest_feature:

        attributes = nearest_feature.get(
            "attributes",
            {}
        )

        nearest_road_name = road_name_from_feature(
            nearest_feature
        )

        road_segment_status = interpret_segment_status(
            attributes.get("SEGSTAT")
        )

        road_dedication_status = (
            interpret_dedication_status(
                attributes.get("DEDSTAT")
            )
        )

        fire_drivable = interpret_yes_no(
            attributes.get("FIREDRIV")
        )

    frontage_road_name = frontage.get(
        "frontage_road_name"
    )

    if frontage_road_name:
        nearest_road_name = frontage_road_name

    nearest_road_type = determine_road_type(
        dedication_status=road_dedication_status,
        road_name=nearest_road_name
    )

    county_maintained_road_name = None
    county_road_jurisdiction = None
    county_road_asset_status = None

    if maintained_attributes:

        county_maintained_road_name = clean_text(
            maintained_attributes.get(
                "ROAD_NAME"
            )
        )

        county_road_jurisdiction = clean_text(
            maintained_attributes.get(
                "JURISDICTION"
            )
        )

        county_road_asset_status = clean_text(
            maintained_attributes.get(
                "ASSET_STATUS"
            )
        )

    nearest_road_is_county_maintained = (
        roads_appear_to_match(
            nearest_road_name=nearest_road_name,
            maintained_road_name=(
                county_maintained_road_name
            )
        )
    )

    mapped_road_found = bool(
        road_features
    )

    county_maintained_road_found = (
        maintained_attributes is not None
        or bool(maintained_features)
    )

    interpretation = determine_access_screening(
        mapped_road_found=mapped_road_found,
        nearest_road_type=nearest_road_type,
        county_maintained_road_found=(
            county_maintained_road_found
        ),
        nearest_road_is_county_maintained=(
            nearest_road_is_county_maintained
        ),
        frontage_edge_found=frontage.get(
            "frontage_edge_found",
            False
        ),
        frontage_confidence=frontage.get(
            "frontage_confidence"
        )
    )

    # If the authoritative general road layer did not return usable
    # geometry, do not downgrade or upgrade access based on the
    # maintained-road fallback. Treat access as incomplete instead.
    if nearest_road_lookup_status in {
        "timeout",
        "error"
    }:

        interpretation = {
            "preliminary_access_level": (
                "road_centerline_temporarily_unavailable"
            ),
            "constraint_level": "unknown",
            "development_warning": (
                "The general road-centerline service was unavailable, "
                "so Housing OS did not substitute a different road "
                "dataset for frontage or nearest-road analysis. "
                "County-maintained-road information may still be "
                "shown as supporting evidence, but frontage and legal "
                "access require confirmation."
            )
        }

    lookup_statuses = {
        nearest_road_lookup_status,
        maintained_road_lookup_status,
        frontage_lookup_status
    }

    partial_results = (
        nearest_road_lookup_status in {
            "timeout",
            "error"
        }
        and county_maintained_road_found
    ) or (
        bool(
            {
                "found",
                "not_found"
            }
            & lookup_statuses
        )
        and bool(
            {
                "timeout",
                "error",
                "unavailable"
            }
            & lookup_statuses
        )
    )

    if nearest_road_lookup_status in {
        "timeout",
        "error"
    }:

        overall_status = (
            "partial"
            if county_maintained_road_found
            else "unavailable"
        )

    elif {
        "timeout",
        "error"
    } & lookup_statuses:

        overall_status = (
            "partial"
            if partial_results
            else "unavailable"
        )

    else:

        overall_status = "found"

    base_message = (
        "This is a simplified parcel-envelope road and frontage screening. "
        "The general SanGIS road layer is the only dataset used to "
        "identify the nearest mapped road and probable frontage. "
        "The County-maintained-road layer is used only to corroborate "
        "maintenance status and is never substituted as frontage when "
        "the general road layer is unavailable. "
        "The parcel-center and parcel-edge distances measure different "
        "things. A detected frontage edge is geometric evidence only "
        "and does not confirm legal frontage, recorded access, road "
        "right-of-way width, driveway permits, road condition, or "
        "fire-code compliance."
    )

    if lookup_messages:

        message = (
            base_message
            + " "
            + " ".join(lookup_messages)
            + " Available road results were preserved."
        )

    else:

        message = base_message

    return {
        "nearest_road_name": nearest_road_name,
        "nearest_road_type": nearest_road_type,
        "road_segment_status": road_segment_status,
        "road_dedication_status": (
            road_dedication_status
        ),
        "fire_drivable": fire_drivable,
        "nearest_road_distance_feet": (
            round(
                nearest_distance
            )
            if nearest_distance is not None
            else None
        ),
        "parcel_center_to_road_feet": (
            round(
                nearest_distance
            )
            if nearest_distance is not None
            else None
        ),
        "parcel_edge_to_road_feet": frontage.get(
            "frontage_centerline_distance_feet"
        ),
        "mapped_road_found": mapped_road_found,
        "county_maintained_road_found": (
            county_maintained_road_found
        ),
        "county_maintained_road_name": (
            county_maintained_road_name
        ),
        "county_road_jurisdiction": (
            county_road_jurisdiction
        ),
        "county_road_asset_status": (
            county_road_asset_status
        ),
        "county_road_distance_feet": (
            maintained_distance
        ),
        "nearest_road_is_county_maintained": (
            nearest_road_is_county_maintained
        ),
        "direct_frontage_confirmed": False,
        **frontage,
        "nearest_road_lookup_status": (
            nearest_road_lookup_status
        ),
        "maintained_road_lookup_status": (
            maintained_road_lookup_status
        ),
        "frontage_lookup_status": (
            frontage_lookup_status
        ),
        "partial_results": partial_results,
        "preliminary_access_level": interpretation[
            "preliminary_access_level"
        ],
        "constraint_level": interpretation[
            "constraint_level"
        ],
        "development_warning": interpretation[
            "development_warning"
        ],
        "legal_access_confirmed": False,
        "easement_review_status": "not_reviewed",
        "status": overall_status,
        "source": (
            "SanGIS Roads and County of San Diego "
            "Maintained Road System"
        ),
        "message": message,
        "analysis_scope": "parcel_frontage_screening"
    }