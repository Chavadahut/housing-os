import math
from typing import Any


DEFAULT_GRID_DIVISIONS = 7
MAX_SAMPLE_POINTS = 49


def point_in_ring(
    longitude: float,
    latitude: float,
    ring: list
) -> bool:

    inside = False

    if len(ring) < 3:
        return False

    previous_index = len(ring) - 1

    for current_index in range(len(ring)):

        current_point = ring[current_index]
        previous_point = ring[previous_index]

        try:
            current_x = float(current_point[0])
            current_y = float(current_point[1])
            previous_x = float(previous_point[0])
            previous_y = float(previous_point[1])

        except (TypeError, ValueError, IndexError):
            previous_index = current_index
            continue

        intersects = (
            (current_y > latitude)
            != (previous_y > latitude)
        )

        if intersects:

            denominator = previous_y - current_y

            if denominator != 0:

                crossing_x = (
                    (previous_x - current_x)
                    * (latitude - current_y)
                    / denominator
                    + current_x
                )

                if longitude < crossing_x:
                    inside = not inside

        previous_index = current_index

    return inside


def point_in_polygon(
    longitude: float,
    latitude: float,
    rings: list
) -> bool:

    inside = False

    for ring in rings:

        if point_in_ring(
            longitude=longitude,
            latitude=latitude,
            ring=ring
        ):
            inside = not inside

    return inside


def flatten_vertices(
    rings: list
) -> list[tuple[float, float]]:

    vertices = []

    for ring in rings:

        for point in ring:

            try:
                longitude = float(point[0])
                latitude = float(point[1])

            except (TypeError, ValueError, IndexError):
                continue

            vertices.append(
                (
                    latitude,
                    longitude
                )
            )

    return vertices


def select_evenly_spaced_points(
    points: list[tuple[float, float]],
    maximum_points: int
) -> list[tuple[float, float]]:

    if len(points) <= maximum_points:
        return points

    selected = []
    step = len(points) / maximum_points

    for index in range(maximum_points):

        selected_index = min(
            int(index * step),
            len(points) - 1
        )

        selected.append(
            points[selected_index]
        )

    return selected


def build_parcel_sample_points(
    parcel_boundary: dict | None,
    fallback_latitude: float,
    fallback_longitude: float,
    grid_divisions: int = DEFAULT_GRID_DIVISIONS,
    maximum_points: int = MAX_SAMPLE_POINTS
) -> list[tuple[float, float]]:

    if not isinstance(parcel_boundary, dict):

        return [
            (
                fallback_latitude,
                fallback_longitude
            )
        ]

    rings = parcel_boundary.get(
        "rings",
        []
    )

    if not rings:

        return [
            (
                fallback_latitude,
                fallback_longitude
            )
        ]

    vertices = flatten_vertices(
        rings
    )

    if not vertices:

        return [
            (
                fallback_latitude,
                fallback_longitude
            )
        ]

    latitudes = [
        point[0]
        for point in vertices
    ]

    longitudes = [
        point[1]
        for point in vertices
    ]

    minimum_latitude = min(latitudes)
    maximum_latitude = max(latitudes)
    minimum_longitude = min(longitudes)
    maximum_longitude = max(longitudes)

    latitude_step = (
        maximum_latitude
        - minimum_latitude
    ) / grid_divisions

    longitude_step = (
        maximum_longitude
        - minimum_longitude
    ) / grid_divisions

    candidate_points = []

    if point_in_polygon(
        longitude=fallback_longitude,
        latitude=fallback_latitude,
        rings=rings
    ):

        candidate_points.append(
            (
                fallback_latitude,
                fallback_longitude
            )
        )

    for row in range(grid_divisions):

        sample_latitude = (
            minimum_latitude
            + latitude_step * (row + 0.5)
        )

        for column in range(grid_divisions):

            sample_longitude = (
                minimum_longitude
                + longitude_step * (column + 0.5)
            )

            if point_in_polygon(
                longitude=sample_longitude,
                latitude=sample_latitude,
                rings=rings
            ):

                candidate_points.append(
                    (
                        sample_latitude,
                        sample_longitude
                    )
                )

    if len(candidate_points) < 9:

        candidate_points.extend(
            select_evenly_spaced_points(
                points=vertices,
                maximum_points=12
            )
        )

    unique_points = []
    seen = set()

    for latitude, longitude in candidate_points:

        key = (
            round(latitude, 7),
            round(longitude, 7)
        )

        if key in seen:
            continue

        seen.add(key)

        unique_points.append(
            (
                latitude,
                longitude
            )
        )

    return select_evenly_spaced_points(
        points=unique_points,
        maximum_points=maximum_points
    )


def estimate_acres(
    parcel_acres: Any,
    percent: float | None
) -> float | None:

    try:
        acreage = float(parcel_acres)

    except (TypeError, ValueError):
        return None

    if percent is None:
        return None

    return round(
        acreage * percent / 100,
        3
    )


def percent_of_samples(
    matching_count: int,
    successful_count: int
) -> float | None:

    if successful_count <= 0:
        return None

    return round(
        matching_count
        / successful_count
        * 100,
        2
    )