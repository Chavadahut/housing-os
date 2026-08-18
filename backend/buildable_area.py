import math
from typing import Any

from pyproj import Transformer
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry


SQUARE_FEET_PER_ACRE = 43560

transformer = Transformer.from_crs(
    "EPSG:4326",
    "EPSG:2230",
    always_xy=True
)

to_wgs84 = Transformer.from_crs(
    "EPSG:2230",
    "EPSG:4326",
    always_xy=True
)

PARCEL_BOUNDARY_SIMPLIFY_TOLERANCE_FEET = 5


SETBACK_SCHEDULE = {
    "A": {
        "front_centerline_feet": 100,
        "interior_side_feet": 15,
        "exterior_side_centerline_feet": 35,
        "rear_feet": 50
    },
    "B": {
        "front_centerline_feet": 60,
        "interior_side_feet": 15,
        "exterior_side_centerline_feet": 35,
        "rear_feet": 50
    },
    "C": {
        "front_centerline_feet": 60,
        "interior_side_feet": 15,
        "exterior_side_centerline_feet": 35,
        "rear_feet": 25
    },
    "D": {
        "front_centerline_feet": 60,
        "interior_side_feet": 15,
        "exterior_side_centerline_feet": 35,
        "rear_feet": 25
    },
    "E": {
        "front_centerline_feet": 60,
        "interior_side_feet": 0,
        "exterior_side_centerline_feet": 35,
        "rear_feet": 15
    },
    "G": {
        "front_centerline_feet": 50,
        "interior_side_feet": 10,
        "exterior_side_centerline_feet": 35,
        "rear_feet": 40
    },
    "H": {
        "front_centerline_feet": 50,
        "interior_side_feet": 10,
        "exterior_side_centerline_feet": 35,
        "rear_feet": 25
    },
    "I": {
        "front_centerline_feet": 50,
        "interior_side_feet": 7.5,
        "exterior_side_centerline_feet": 35,
        "rear_feet": 25
    },
    "J": {
        "front_centerline_feet": 50,
        "interior_side_feet": 5,
        "exterior_side_centerline_feet": 35,
        "rear_feet": 25
    },
    "M": {
        "front_centerline_feet": 50,
        "interior_side_feet": 5,
        "exterior_side_centerline_feet": 35,
        "rear_feet": 25
    },
    "N": {
        "front_centerline_feet": 50,
        "interior_side_feet": 5,
        "exterior_side_centerline_feet": 35,
        "rear_feet": 25
    },
    "Q": {
        "front_centerline_feet": 50,
        "interior_side_feet": 0,
        "exterior_side_centerline_feet": 35,
        "rear_feet": 15
    },
    "T": {
        "front_centerline_feet": 30,
        "interior_side_feet": 0,
        "exterior_side_centerline_feet": 35,
        "rear_feet": 15
    },
    "W": {
        "front_centerline_feet": 60,
        "interior_side_feet": 25,
        "exterior_side_centerline_feet": 35,
        "rear_feet": 25
    }
}


def clean_number(
    value: Any
) -> float | None:

    try:
        return float(value)

    except (TypeError, ValueError):
        return None


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


def projected_primary_ring(
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
            transformer.transform(
                longitude,
                latitude
            )
        )

    if len(points) >= 2 and points[0] == points[-1]:
        points = points[:-1]

    if len(points) < 3:
        return []

    return simplify_closed_ring(
        points=points,
        tolerance_feet=(
            PARCEL_BOUNDARY_SIMPLIFY_TOLERANCE_FEET
        )
    )


def signed_polygon_area(
    points: list[tuple[float, float]]
) -> float:

    area = 0.0

    for index in range(len(points)):

        x1, y1 = points[index]
        x2, y2 = points[
            (index + 1) % len(points)
        ]

        area += (
            x1 * y2
            - x2 * y1
        )

    return area / 2


def clip_polygon_to_offset_edge(
    polygon: list[tuple[float, float]],
    edge_start: tuple[float, float],
    edge_end: tuple[float, float],
    inward_normal: tuple[float, float],
    setback_feet: float
) -> list[tuple[float, float]]:

    if not polygon:
        return []

    def signed_distance(
        point: tuple[float, float]
    ) -> float:

        return (
            (
                point[0] - edge_start[0]
            ) * inward_normal[0]
            + (
                point[1] - edge_start[1]
            ) * inward_normal[1]
            - setback_feet
        )

    output = []

    previous = polygon[-1]
    previous_distance = signed_distance(
        previous
    )
    previous_inside = previous_distance >= -1e-7

    for current in polygon:

        current_distance = signed_distance(
            current
        )
        current_inside = current_distance >= -1e-7

        if current_inside != previous_inside:

            denominator = (
                previous_distance
                - current_distance
            )

            if abs(denominator) > 1e-12:

                ratio = (
                    previous_distance
                    / denominator
                )

                intersection = (
                    previous[0]
                    + ratio
                    * (
                        current[0]
                        - previous[0]
                    ),
                    previous[1]
                    + ratio
                    * (
                        current[1]
                        - previous[1]
                    )
                )

                output.append(
                    intersection
                )

        if current_inside:

            output.append(
                current
            )

        previous = current
        previous_distance = current_distance
        previous_inside = current_inside

    return output


def polygon_from_projected_points(
    points: list[tuple[float, float]]
) -> Polygon | None:

    if len(points) < 3:
        return None

    polygon = Polygon(points)

    if not polygon.is_valid:
        polygon = polygon.buffer(0)

    if polygon.is_empty:
        return None

    if polygon.geom_type == "MultiPolygon":
        polygon = max(
            polygon.geoms,
            key=lambda geometry: geometry.area
        )

    if polygon.geom_type != "Polygon":
        return None

    return polygon


def edge_inward_normal(
    points: list[tuple[float, float]],
    edge_index: int
) -> tuple[
    tuple[float, float],
    tuple[float, float],
    tuple[float, float]
] | None:

    if edge_index < 0 or edge_index >= len(points):
        return None

    start = points[edge_index]
    end = points[(edge_index + 1) % len(points)]

    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.hypot(dx, dy)

    if length < 1:
        return None

    tangent = (dx / length, dy / length)
    orientation = signed_polygon_area(points)

    if orientation > 0:
        inward_normal = (-tangent[1], tangent[0])
    else:
        inward_normal = (tangent[1], -tangent[0])

    return start, tangent, inward_normal


def inward_half_plane(
    points: list[tuple[float, float]],
    edge_index: int,
    setback_feet: float,
    extent_feet: float
) -> Polygon | None:

    edge = edge_inward_normal(
        points=points,
        edge_index=edge_index
    )

    if edge is None:
        return None

    start, tangent, inward_normal = edge

    offset_origin = (
        start[0] + inward_normal[0] * setback_feet,
        start[1] + inward_normal[1] * setback_feet
    )

    left = (
        offset_origin[0] - tangent[0] * extent_feet,
        offset_origin[1] - tangent[1] * extent_feet
    )

    right = (
        offset_origin[0] + tangent[0] * extent_feet,
        offset_origin[1] + tangent[1] * extent_feet
    )

    far_right = (
        right[0] + inward_normal[0] * extent_feet,
        right[1] + inward_normal[1] * extent_feet
    )

    far_left = (
        left[0] + inward_normal[0] * extent_feet,
        left[1] + inward_normal[1] * extent_feet
    )

    return Polygon([left, right, far_right, far_left])


def largest_polygon(
    geometry: BaseGeometry
) -> Polygon | None:

    if geometry.is_empty:
        return None

    if geometry.geom_type == "Polygon":
        return geometry

    if geometry.geom_type == "MultiPolygon":
        return max(
            geometry.geoms,
            key=lambda candidate: candidate.area
        )

    return None


def build_directional_setback_envelope(
    parcel_boundary: dict | None,
    frontage_edge_index: int | None,
    rear_edge_index: int | None,
    front_setback_feet: float | None,
    rear_setback_feet: float | None,
    side_setback_feet: float | None
) -> dict:

    points = projected_primary_ring(parcel_boundary)

    if len(points) < 3:
        return {
            "feature": None,
            "area_square_feet": None,
            "status": "parcel_geometry_unavailable",
            "message": (
                "A usable parcel polygon was not available "
                "for setback-envelope geometry."
            )
        }

    if (
        frontage_edge_index is None
        or rear_edge_index is None
        or front_setback_feet is None
        or rear_setback_feet is None
        or side_setback_feet is None
    ):
        return {
            "feature": None,
            "area_square_feet": None,
            "status": "setback_inputs_unavailable",
            "message": (
                "Frontage, rear-edge, or setback inputs were "
                "not available."
            )
        }

    parcel_polygon = polygon_from_projected_points(points)

    if parcel_polygon is None:
        return {
            "feature": None,
            "area_square_feet": None,
            "status": "invalid_geometry",
            "message": (
                "The parcel polygon could not be converted "
                "into a valid Shapely polygon."
            )
        }

    side_envelope = parcel_polygon.buffer(
        -side_setback_feet,
        join_style="mitre"
    )

    envelope = largest_polygon(side_envelope)

    if envelope is None:
        return {
            "feature": None,
            "area_square_feet": 0,
            "status": "no_remaining_envelope",
            "message": (
                "The side setbacks removed the entire "
                "simplified parcel polygon."
            )
        }

    minimum_x, minimum_y, maximum_x, maximum_y = parcel_polygon.bounds
    parcel_span = max(
        maximum_x - minimum_x,
        maximum_y - minimum_y,
        1000
    )
    extent_feet = parcel_span * 20

    if front_setback_feet > side_setback_feet:
        front_half_plane = inward_half_plane(
            points=points,
            edge_index=frontage_edge_index,
            setback_feet=front_setback_feet,
            extent_feet=extent_feet
        )

        if front_half_plane is not None:
            envelope = largest_polygon(
                envelope.intersection(front_half_plane)
            )

    if envelope is None:
        return {
            "feature": None,
            "area_square_feet": 0,
            "status": "no_remaining_envelope",
            "message": (
                "The front setback removed the entire "
                "preliminary side-setback envelope."
            )
        }

    if rear_setback_feet > side_setback_feet:
        rear_half_plane = inward_half_plane(
            points=points,
            edge_index=rear_edge_index,
            setback_feet=rear_setback_feet,
            extent_feet=extent_feet
        )

        if rear_half_plane is not None:
            envelope = largest_polygon(
                envelope.intersection(rear_half_plane)
            )

    if envelope is None:
        return {
            "feature": None,
            "area_square_feet": 0,
            "status": "no_remaining_envelope",
            "message": (
                "The rear setback removed the entire "
                "preliminary envelope."
            )
        }

    coordinates = [
        list(to_wgs84.transform(x, y))
        for x, y in envelope.exterior.coords
    ]

    return {
        "feature": {
            "type": "Feature",
            "properties": {
                "role": (
                    "preliminary_directional_setback_envelope"
                ),
                "front_setback_feet": front_setback_feet,
                "rear_setback_feet": rear_setback_feet,
                "side_setback_feet": side_setback_feet,
                "geometry_method": (
                    "shapely_polygon_buffer_and_half_planes"
                ),
                "legal_building_envelope_confirmed": False
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [coordinates]
            }
        },
        "area_square_feet": envelope.area,
        "status": "found",
        "message": (
            "A preliminary directional setback-envelope "
            "polygon was generated with Shapely using a "
            "uniform side-yard buffer plus directional front "
            "and rear setback clipping."
        )
    }


def polygon_area_and_perimeter(
    rings: list
) -> tuple[float | None, float | None]:

    total_signed_area = 0.0
    total_perimeter = 0.0
    usable_ring_found = False

    for ring in rings:

        projected_points = []

        for point in ring:

            try:
                longitude = float(point[0])
                latitude = float(point[1])

            except (
                TypeError,
                ValueError,
                IndexError
            ):
                continue

            x, y = transformer.transform(
                longitude,
                latitude
            )

            projected_points.append(
                (
                    x,
                    y
                )
            )

        if len(projected_points) < 3:
            continue

        usable_ring_found = True

        if projected_points[0] != projected_points[-1]:
            projected_points.append(
                projected_points[0]
            )

        ring_signed_area = 0.0
        ring_perimeter = 0.0

        for index in range(
            len(projected_points) - 1
        ):

            x1, y1 = projected_points[index]
            x2, y2 = projected_points[index + 1]

            ring_signed_area += (
                x1 * y2
                - x2 * y1
            )

            ring_perimeter += math.hypot(
                x2 - x1,
                y2 - y1
            )

        total_signed_area += (
            ring_signed_area / 2
        )

        total_perimeter += ring_perimeter

    if not usable_ring_found:
        return None, None

    return (
        abs(total_signed_area),
        total_perimeter
    )


def estimate_uniform_interior_envelope(
    parcel_area_square_feet: float,
    parcel_perimeter_feet: float,
    setback_feet: float
) -> float:

    estimated_area = (
        parcel_area_square_feet
        - parcel_perimeter_feet * setback_feet
        + math.pi * setback_feet ** 2
    )

    return max(
        estimated_area,
        0
    )


def setback_information(
    designator: str | None
) -> dict:

    normalized = (
        designator.strip().upper()
        if isinstance(designator, str)
        else None
    )

    schedule = SETBACK_SCHEDULE.get(
        normalized
    )

    if schedule is None:

        return {
            "setback_designator": normalized,
            "front_setback_centerline_feet": None,
            "interior_side_setback_feet": None,
            "exterior_side_centerline_feet": None,
            "rear_setback_feet": None,
            "status": "unsupported_designator"
        }

    return {
        "setback_designator": normalized,
        "front_setback_centerline_feet": schedule[
            "front_centerline_feet"
        ],
        "interior_side_setback_feet": schedule[
            "interior_side_feet"
        ],
        "exterior_side_centerline_feet": schedule[
            "exterior_side_centerline_feet"
        ],
        "rear_setback_feet": schedule[
            "rear_feet"
        ],
        "status": "decoded"
    }


def get_buildable_area_data(
    parcel_boundary: dict | None,
    parcel_acres: float | None,
    zoning: dict,
    habitat: dict,
    wetlands: dict,
    terrain: dict,
    road_access: dict
) -> dict:

    zoning_jurisdiction = zoning.get(
        "jurisdiction"
    )

    is_san_diego_county_zoning = (
        zoning_jurisdiction
        == "Unincorporated San Diego County"
    )

    setback_designator_value = zoning.get(
        "setback"
    )

    setback = setback_information(
        setback_designator_value
    )

    boundary_available = (
        isinstance(parcel_boundary, dict)
        and parcel_boundary.get("status") == "found"
        and bool(parcel_boundary.get("rings"))
    )

    geometry_area_square_feet = None
    perimeter_feet = None
    geometry_acres = None

    if boundary_available:

        (
            geometry_area_square_feet,
            perimeter_feet
        ) = polygon_area_and_perimeter(
            parcel_boundary.get("rings", [])
        )

        if geometry_area_square_feet is not None:

            geometry_acres = (
                geometry_area_square_feet
                / SQUARE_FEET_PER_ACRE
            )

    interior_side_setback = clean_number(
        setback.get(
            "interior_side_setback_feet"
        )
    )

    minimum_setback_screened_acres = None
    minimum_setback_screened_percent = None
    screened_square_feet = None

    if (
        geometry_area_square_feet is not None
        and perimeter_feet is not None
        and interior_side_setback is not None
    ):

        screened_square_feet = (
            estimate_uniform_interior_envelope(
                parcel_area_square_feet=(
                    geometry_area_square_feet
                ),
                parcel_perimeter_feet=perimeter_feet,
                setback_feet=interior_side_setback
            )
        )

        minimum_setback_screened_acres = round(
            screened_square_feet
            / SQUARE_FEET_PER_ACRE,
            3
        )

        if geometry_area_square_feet > 0:

            minimum_setback_screened_percent = round(
                screened_square_feet
                / geometry_area_square_feet
                * 100,
                2
            )

    frontage_edge_found = (
        road_access.get(
            "frontage_edge_found"
        )
        is True
    )

    frontage_road_name = road_access.get(
        "frontage_road_name"
    )

    frontage_length_feet = clean_number(
        road_access.get(
            "frontage_length_feet"
        )
    )

    frontage_centerline_distance = clean_number(
        road_access.get(
            "parcel_edge_to_road_feet"
        )
        or road_access.get(
            "frontage_centerline_distance_feet"
        )
    )

    frontage_confidence = road_access.get(
        "frontage_confidence"
    )

    rear_edge_length_feet = clean_number(
        road_access.get(
            "rear_edge_length_feet"
        )
    )

    front_centerline_setback = clean_number(
        setback.get(
            "front_setback_centerline_feet"
        )
    )

    rear_setback = clean_number(
        setback.get(
            "rear_setback_feet"
        )
    )

    front_setback_applied_feet = None
    rear_setback_applied_feet = None
    directional_setback_screened_acres = None
    directional_setback_screened_percent = None

    if (
        frontage_edge_found
        and frontage_confidence in {
            "high",
            "medium"
        }
        and screened_square_feet is not None
        and frontage_length_feet is not None
        and frontage_centerline_distance is not None
        and front_centerline_setback is not None
        and rear_edge_length_feet is not None
        and rear_setback is not None
        and interior_side_setback is not None
    ):

        front_setback_applied_feet = max(
            front_centerline_setback
            - frontage_centerline_distance,
            interior_side_setback
        )

        rear_setback_applied_feet = max(
            rear_setback,
            interior_side_setback
        )

        additional_front_depth = max(
            front_setback_applied_feet
            - interior_side_setback,
            0
        )

        additional_rear_depth = max(
            rear_setback_applied_feet
            - interior_side_setback,
            0
        )

        directional_square_feet = max(
            screened_square_feet
            - (
                additional_front_depth
                * frontage_length_feet
            )
            - (
                additional_rear_depth
                * rear_edge_length_feet
            ),
            0
        )

        directional_setback_screened_acres = round(
            directional_square_feet
            / SQUARE_FEET_PER_ACRE,
            3
        )

        if geometry_area_square_feet:

            directional_setback_screened_percent = round(
                directional_square_feet
                / geometry_area_square_feet
                * 100,
                2
            )

    frontage_edge_index = road_access.get(
        "frontage_edge_index"
    )

    rear_edge_index = road_access.get(
        "rear_edge_index"
    )

    setback_envelope = (
        build_directional_setback_envelope(
            parcel_boundary=parcel_boundary,
            frontage_edge_index=frontage_edge_index,
            rear_edge_index=rear_edge_index,
            front_setback_feet=(
                front_setback_applied_feet
            ),
            rear_setback_feet=(
                rear_setback_applied_feet
            ),
            side_setback_feet=(
                interior_side_setback
            )
        )
    )

    setback_envelope_geojson = (
        setback_envelope.get(
            "feature"
        )
    )

    setback_envelope_status = (
        setback_envelope.get(
            "status"
        )
    )

    setback_envelope_message = (
        setback_envelope.get(
            "message"
        )
    )

    setback_envelope_square_feet = (
        setback_envelope.get(
            "area_square_feet"
        )
    )

    if (
        setback_envelope_status == "found"
        and setback_envelope_square_feet is not None
    ):

        directional_setback_screened_acres = round(
            setback_envelope_square_feet
            / SQUARE_FEET_PER_ACRE,
            3
        )

        if geometry_area_square_feet:

            directional_setback_screened_percent = round(
                setback_envelope_square_feet
                / geometry_area_square_feet
                * 100,
                2
            )

    habitat_review_acres = clean_number(
        habitat.get(
            "constrained_acres"
        )
    )

    wetland_indicator_acres = clean_number(
        wetlands.get(
            "constrained_acres"
        )
    )

    preliminary_buildable_acres = None
    buildable_percent = None

    if directional_setback_screened_acres is not None:

        # Retained as None intentionally: a setback envelope is not the same
        # as buildable land until environmental, access, fire, utility, and
        # wastewater exclusion geometry has been applied.
        preliminary_buildable_acres = None
        buildable_percent = None

    missing_reasons = []

    if not frontage_edge_found:

        missing_reasons.append(
            "a probable frontage edge was not identified"
        )

    elif frontage_confidence == "low":

        missing_reasons.append(
            "frontage confidence is low"
        )

    missing_reasons.extend([
        (
            "the detected frontage edge does not prove legal "
            "frontage or right-of-way width"
        ),
        (
            "environmental results are sample estimates rather "
            "than mapped legal exclusion boundaries"
        ),
        (
            "fire setbacks and emergency-access geometry are "
            "not mapped"
        ),
        (
            "septic layout and reserve area are not mapped"
        )
    ])

    exact_setback_envelope_available = False

    constraint_level = "unknown"

    if (
        habitat.get("constraint_level") == "major"
        or wetlands.get("constraint_level") == "major"
    ):

        constraint_level = "major"

    elif (
        habitat.get("constraint_level") == "moderate"
        or wetlands.get("constraint_level") == "moderate"
    ):

        constraint_level = "moderate"

    setback_status = setback.get(
        "status"
    )

    if directional_setback_screened_acres is not None:

        warning = (
            "Housing OS identified a probable parcel frontage "
            "edge and created a preliminary setback-based "
            "buildable-area estimate. This remains an "
            "approximation because the road centerline is not "
            "the legal right-of-way line, parcel-edge detection "
            "does not establish legal frontage, and environmental, "
            "fire-access, utility, and onsite-wastewater constraints "
            "have not been converted into final exclusion geometry."
        )

        status = "preliminary_frontage_estimate"

    elif setback_designator_value is None:

        warning = (
            "A zoning setback designator was not available, so "
            "Housing OS could not calculate a directional setback "
            "envelope for this parcel."
        )

        status = "setback_inputs_unavailable"

    elif setback_status != "decoded":

        warning = (
            "A zoning setback value was returned, but Housing OS "
            "does not have a verified setback schedule for that "
            "value and jurisdiction."
        )

        status = "setback_schedule_unavailable"

    else:

        warning = (
            "Housing OS decoded the zoning setback designator "
            "but could not create a directional front-and-rear "
            "setback estimate with adequate confidence."
        )

        status = "preliminary"

    if is_san_diego_county_zoning:

        source_description = (
            "County of San Diego zoning setback schedule, "
            "County parcel geometry, SanGIS road centerlines, "
            "and Housing OS constraint screenings"
        )

    else:

        source_description = (
            "County parcel geometry, SanGIS road centerlines, "
            "available jurisdiction-specific zoning data, and "
            "Housing OS constraint screenings"
        )

    if setback_designator_value is None:

        buildable_message = (
            "Housing OS could not calculate a directional setback "
            "acreage because a verified zoning setback input was "
            "not available for this parcel. Parcel geometry and "
            "probable frontage may still be shown, but no setback "
            "envelope should be treated as calculated."
        )

    else:

        buildable_message = (
            "The preliminary buildable acreage is currently the "
            "directional setback-envelope acreage only. It is an "
            "approximate zoning-and-frontage screen based on a "
            "probable frontage edge, the road centerline distance, "
            "the opposite parcel edge, and the zoning setback "
            "designator. It should not be treated as final usable "
            "or legally buildable acreage because "
            + "; ".join(missing_reasons)
            + "."
        )

    acreage_difference_percent = None
    acreage_consistency_status = "not_compared"
    acreage_warning = None

    if parcel_acres and geometry_acres is not None:
        acreage_difference_percent = round(
            abs(geometry_acres - parcel_acres) / parcel_acres * 100,
            2,
        )
        acreage_consistency_status = (
            "review" if acreage_difference_percent >= 5 else "consistent"
        )
        if acreage_consistency_status == "review":
            acreage_warning = (
                "Mapped parcel geometry and assessor acreage differ by "
                f"approximately {acreage_difference_percent:g}%. Confirm "
                "the legal parcel boundary and area before relying on "
                "area-based calculations."
            )

    return {
        "parcel_acres": parcel_acres,
        "parcel_geometry_acres": (
            round(
                geometry_acres,
                3
            )
            if geometry_acres is not None
            else None
        ),
        "acreage_difference_percent": acreage_difference_percent,
        "acreage_consistency_status": acreage_consistency_status,
        "acreage_warning": acreage_warning,
        "setback_designator": setback.get(
            "setback_designator"
        ),
        "front_setback_centerline_feet": setback.get(
            "front_setback_centerline_feet"
        ),
        "interior_side_setback_feet": setback.get(
            "interior_side_setback_feet"
        ),
        "exterior_side_setback_centerline_feet": setback.get(
            "exterior_side_centerline_feet"
        ),
        "rear_setback_feet": setback.get(
            "rear_setback_feet"
        ),
        "minimum_uniform_setback_feet": (
            interior_side_setback
        ),
        "minimum_setback_screened_acres": (
            minimum_setback_screened_acres
        ),
        "minimum_setback_screened_percent": (
            minimum_setback_screened_percent
        ),
        "frontage_identified": frontage_edge_found,
        "frontage_road_name": frontage_road_name,
        "frontage_length_feet": frontage_length_feet,
        "parcel_edge_to_road_feet": (
            frontage_centerline_distance
        ),
        "frontage_confidence": frontage_confidence,
        "front_setback_applied_feet": (
            front_setback_applied_feet
        ),
        "rear_setback_applied_feet": (
            rear_setback_applied_feet
        ),
        "directional_setback_screened_acres": (
            directional_setback_screened_acres
        ),
        "directional_setback_screened_percent": (
            directional_setback_screened_percent
        ),
        "setback_envelope_geojson": (
            setback_envelope_geojson
        ),
        "setback_envelope_status": (
            setback_envelope_status
        ),
        "setback_envelope_message": (
            setback_envelope_message
        ),
        "habitat_review_acres": habitat_review_acres,
        "wetland_indicator_acres": (
            wetland_indicator_acres
        ),
        "preliminary_buildable_acres": (
            preliminary_buildable_acres
        ),
        "buildable_percent": buildable_percent,
        "exact_setback_envelope_available": (
            exact_setback_envelope_available
        ),
        "constraint_level": constraint_level,
        "development_warning": warning,
        "status": status,
        "source": source_description,
        "message": buildable_message,
        "analysis_scope": (
            "preliminary_buildable_area_screening"
        )
    }
