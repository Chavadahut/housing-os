import math
from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed
)
from typing import Any

import requests
from pyproj import Transformer
from shapely.geometry import (
    MultiPoint,
    Point,
    Polygon,
    mapping
)
from shapely.ops import voronoi_diagram


URL = "https://epqs.nationalmap.gov/v1/json"

LOCAL_SAMPLE_DISTANCE_FEET = 100
FEET_PER_LATITUDE_DEGREE = 364000

MAX_PARCEL_SAMPLE_POINTS = 13
GRID_DIVISIONS = 5
MAX_WORKERS = 6
SLOPE_ZONE_SIMPLIFICATION_FEET = 2

TO_LOCAL = Transformer.from_crs(
    "EPSG:4326",
    "EPSG:2230",
    always_xy=True
)

TO_WGS84 = Transformer.from_crs(
    "EPSG:2230",
    "EPSG:4326",
    always_xy=True
)


def empty_terrain_result(
    status: str,
    message: str,
    analysis_scope: str = "local_point_sample"
) -> dict:

    return {
        "center_elevation_feet": None,
        "minimum_sample_elevation_feet": None,
        "maximum_sample_elevation_feet": None,
        "elevation_change_feet": None,
        "estimated_slope_percent": None,
        "estimated_slope_degrees": None,
        "terrain_class": None,
        "development_warning": None,
        "sample_distance_feet": (
            LOCAL_SAMPLE_DISTANCE_FEET
            if analysis_scope == "local_point_sample"
            else None
        ),
        "analysis_scope": analysis_scope,
        "slope_sample_count": 0,
        "slope_sample_geojson": None,
        "slope_zone_count": 0,
        "slope_zone_geojson": None,
        "status": status,
        "source": (
            "USGS 3DEP Elevation Point Query Service"
        ),
        "message": message
    }


def clean_number(
    value: Any
) -> float | None:

    if value is None:
        return None

    try:

        number = float(
            value
        )

        if number <= -9999:
            return None

        return number

    except (TypeError, ValueError):
        return None


def get_elevation(
    latitude: float,
    longitude: float
) -> float | None:

    params = {
        "x": longitude,
        "y": latitude,
        "wkid": 4326,
        "units": "Feet",
        "includeDate": "false"
    }

    response = requests.get(
        URL,
        params=params,
        # Terrain samples run concurrently. Bound a degraded USGS service so
        # this optional screening layer cannot stall the whole experience.
        timeout=(3.05, 8)
    )

    response.raise_for_status()

    data = response.json()

    value = (
        data.get("value")
        or data.get(
            "USGS_Elevation_Point_Query_Service",
            {}
        )
        .get(
            "Elevation_Query",
            {}
        )
        .get("Elevation")
    )

    return clean_number(
        value
    )


def classify_terrain(
    slope_percent: float,
    analysis_scope: str
) -> dict:

    scope_label = (
        "parcel-wide sample"
        if analysis_scope == "parcel_wide_sample"
        else "sampled location"
    )

    if slope_percent < 5:

        return {
            "terrain_class": "mostly_flat",
            "development_warning": (
                f"The {scope_label} appears mostly flat. "
                "A licensed topographic survey and grading "
                "review are still required."
            )
        }

    if slope_percent < 15:

        return {
            "terrain_class": "gentle_slope",
            "development_warning": (
                f"The {scope_label} has a gentle slope. "
                "Some grading, drainage, or foundation "
                "adjustments may apply."
            )
        }

    if slope_percent < 25:

        return {
            "terrain_class": "moderate_slope",
            "development_warning": (
                f"The {scope_label} has a moderate slope. "
                "Grading costs, drainage, access, septic "
                "placement, and usable building area may "
                "be affected."
            )
        }

    if slope_percent < 50:

        return {
            "terrain_class": "steep",
            "development_warning": (
                f"The {scope_label} appears steep. Detailed "
                "topographic, geotechnical, grading, access, "
                "and environmental review may be required."
            )
        }

    return {
        "terrain_class": "very_steep",
        "development_warning": (
            f"The {scope_label} appears very steep. "
            "Development may face significant grading, "
            "access, foundation, drainage, and "
            "environmental constraints."
        )
    }


def point_in_ring(
    longitude: float,
    latitude: float,
    ring: list
) -> bool:

    inside = False
    point_count = len(
        ring
    )

    if point_count < 3:
        return False

    previous_index = (
        point_count - 1
    )

    for current_index in range(
        point_count
    ):

        current_point = ring[
            current_index
        ]

        previous_point = ring[
            previous_index
        ]

        current_x = float(
            current_point[0]
        )

        current_y = float(
            current_point[1]
        )

        previous_x = float(
            previous_point[0]
        )

        previous_y = float(
            previous_point[1]
        )

        intersects = (
            (current_y > latitude)
            != (previous_y > latitude)
        )

        if intersects:

            denominator = (
                previous_y
                - current_y
            )

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

            if len(point) < 2:
                continue

            try:

                longitude = float(
                    point[0]
                )

                latitude = float(
                    point[1]
                )

            except (
                TypeError,
                ValueError
            ):
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

    step = (
        len(points)
        / maximum_points
    )

    for index in range(
        maximum_points
    ):

        selected_index = min(
            int(index * step),
            len(points) - 1
        )

        selected.append(
            points[selected_index]
        )

    return selected


def build_parcel_sample_points(
    latitude: float,
    longitude: float,
    parcel_boundary: dict
) -> list[tuple[float, float]]:

    rings = parcel_boundary.get(
        "rings",
        []
    )

    vertices = flatten_vertices(
        rings
    )

    if not vertices:
        return []

    latitudes = [
        point[0]
        for point in vertices
    ]

    longitudes = [
        point[1]
        for point in vertices
    ]

    minimum_latitude = min(
        latitudes
    )

    maximum_latitude = max(
        latitudes
    )

    minimum_longitude = min(
        longitudes
    )

    maximum_longitude = max(
        longitudes
    )

    candidate_points = []

    lookup_point_inside = point_in_polygon(
        longitude=longitude,
        latitude=latitude,
        rings=rings
    )

    if lookup_point_inside:

        candidate_points.append(
            (
                latitude,
                longitude
            )
        )

    latitude_step = (
        maximum_latitude
        - minimum_latitude
    ) / GRID_DIVISIONS

    longitude_step = (
        maximum_longitude
        - minimum_longitude
    ) / GRID_DIVISIONS

    for row in range(
        GRID_DIVISIONS
    ):

        sample_latitude = (
            minimum_latitude
            + latitude_step
            * (row + 0.5)
        )

        for column in range(
            GRID_DIVISIONS
        ):

            sample_longitude = (
                minimum_longitude
                + longitude_step
                * (column + 0.5)
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

    if len(candidate_points) < 5:

        vertex_candidates = (
            select_evenly_spaced_points(
                points=vertices,
                maximum_points=8
            )
        )

        candidate_points.extend(
            vertex_candidates
        )

    unique_points = []
    seen = set()

    for point in candidate_points:

        key = (
            round(point[0], 7),
            round(point[1], 7)
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        unique_points.append(
            point
        )

    return select_evenly_spaced_points(
        points=unique_points,
        maximum_points=MAX_PARCEL_SAMPLE_POINTS
    )


def build_local_sample_points(
    latitude: float,
    longitude: float
) -> list[tuple[float, float]]:

    latitude_offset = (
        LOCAL_SAMPLE_DISTANCE_FEET
        / FEET_PER_LATITUDE_DEGREE
    )

    longitude_feet_per_degree = (
        FEET_PER_LATITUDE_DEGREE
        * math.cos(
            math.radians(
                latitude
            )
        )
    )

    if longitude_feet_per_degree == 0:
        return []

    longitude_offset = (
        LOCAL_SAMPLE_DISTANCE_FEET
        / longitude_feet_per_degree
    )

    return [
        (
            latitude,
            longitude
        ),
        (
            latitude + latitude_offset,
            longitude
        ),
        (
            latitude - latitude_offset,
            longitude
        ),
        (
            latitude,
            longitude + longitude_offset
        ),
        (
            latitude,
            longitude - longitude_offset
        )
    ]


def distance_feet(
    point_a: tuple[float, float],
    point_b: tuple[float, float]
) -> float:

    latitude_a = point_a[0]
    longitude_a = point_a[1]

    latitude_b = point_b[0]
    longitude_b = point_b[1]

    average_latitude = (
        latitude_a
        + latitude_b
    ) / 2

    latitude_difference_feet = (
        latitude_b
        - latitude_a
    ) * FEET_PER_LATITUDE_DEGREE

    longitude_difference_feet = (
        longitude_b
        - longitude_a
    ) * (
        FEET_PER_LATITUDE_DEGREE
        * math.cos(
            math.radians(
                average_latitude
            )
        )
    )

    return math.hypot(
        latitude_difference_feet,
        longitude_difference_feet
    )


def fetch_elevations(
    sample_points: list[tuple[float, float]]
) -> list[dict]:

    results = []

    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        future_map = {
            executor.submit(
                get_elevation,
                latitude,
                longitude
            ): (
                latitude,
                longitude
            )
            for latitude, longitude in sample_points
        }

        for future in as_completed(
            future_map
        ):

            latitude, longitude = future_map[
                future
            ]

            try:

                elevation = future.result()

            except (
                requests.RequestException,
                ValueError
            ):
                continue

            if elevation is None:
                continue

            results.append({
                "point": (
                    latitude,
                    longitude
                ),
                "elevation": elevation
            })

    return results


def calculate_maximum_sampled_slope(
    elevation_results: list[dict]
) -> tuple[float | None, float | None]:

    maximum_slope = None
    representative_distance = None

    for first_index in range(
        len(elevation_results)
    ):

        first_result = elevation_results[
            first_index
        ]

        for second_index in range(
            first_index + 1,
            len(elevation_results)
        ):

            second_result = elevation_results[
                second_index
            ]

            horizontal_distance = distance_feet(
                first_result["point"],
                second_result["point"]
            )

            if horizontal_distance < 25:
                continue

            elevation_difference = abs(
                first_result["elevation"]
                - second_result["elevation"]
            )

            slope_percent = (
                elevation_difference
                / horizontal_distance
                * 100
            )

            if (
                maximum_slope is None
                or slope_percent > maximum_slope
            ):

                maximum_slope = slope_percent
                representative_distance = (
                    horizontal_distance
                )

    return (
        maximum_slope,
        representative_distance
    )


def classify_sample_slope(
    slope_percent: float
) -> str:

    if slope_percent < 5:
        return "mostly_flat"

    if slope_percent < 15:
        return "gentle_slope"

    if slope_percent < 25:
        return "moderate_slope"

    if slope_percent < 50:
        return "steep"

    return "very_steep"


def calculate_local_sample_slopes(
    elevation_results: list[dict]
) -> list[dict]:

    local_results = []

    for current_index, current_result in enumerate(
        elevation_results
    ):

        nearest_neighbors = []

        for other_index, other_result in enumerate(
            elevation_results
        ):

            if current_index == other_index:
                continue

            horizontal_distance = distance_feet(
                current_result["point"],
                other_result["point"]
            )

            if horizontal_distance < 25:
                continue

            nearest_neighbors.append(
                (
                    horizontal_distance,
                    other_result
                )
            )

        nearest_neighbors.sort(
            key=lambda item: item[0]
        )

        selected_neighbors = nearest_neighbors[:4]

        local_slope = 0.0
        representative_distance = None

        for (
            horizontal_distance,
            neighbor_result
        ) in selected_neighbors:

            elevation_difference = abs(
                current_result["elevation"]
                - neighbor_result["elevation"]
            )

            slope_percent = (
                elevation_difference
                / horizontal_distance
                * 100
            )

            if slope_percent > local_slope:

                local_slope = slope_percent
                representative_distance = (
                    horizontal_distance
                )

        local_results.append({
            "point": current_result["point"],
            "elevation": current_result["elevation"],
            "local_slope_percent": local_slope,
            "terrain_class": classify_sample_slope(
                local_slope
            ),
            "representative_distance_feet": (
                representative_distance
            )
        })

    return local_results


def build_slope_sample_geojson(
    elevation_results: list[dict]
) -> dict | None:

    local_results = calculate_local_sample_slopes(
        elevation_results
    )

    if not local_results:
        return None

    features = []

    for sample_index, result in enumerate(
        local_results,
        start=1
    ):

        latitude, longitude = result[
            "point"
        ]

        representative_distance = result.get(
            "representative_distance_feet"
        )

        features.append({
            "type": "Feature",
            "properties": {
                "role": "terrain_slope_sample",
                "sample_number": sample_index,
                "elevation_feet": round(
                    result["elevation"],
                    2
                ),
                "local_slope_percent": round(
                    result["local_slope_percent"],
                    2
                ),
                "terrain_class": result[
                    "terrain_class"
                ],
                "representative_distance_feet": (
                    round(
                        representative_distance
                    )
                    if representative_distance
                    else None
                ),
                "survey_grade": False
            },
            "geometry": {
                "type": "Point",
                "coordinates": [
                    longitude,
                    latitude
                ]
            }
        })

    return {
        "type": "FeatureCollection",
        "features": features
    }


def primary_boundary_ring(
    parcel_boundary: dict
) -> list[list[float]]:

    rings = parcel_boundary.get(
        "rings",
        []
    )

    valid_rings = [
        ring
        for ring in rings
        if isinstance(ring, list)
        and len(ring) >= 4
    ]

    if not valid_rings:
        return []

    return max(
        valid_rings,
        key=len
    )


def projected_parcel_polygon(
    parcel_boundary: dict
) -> Polygon | None:

    ring = primary_boundary_ring(
        parcel_boundary
    )

    if not ring:
        return None

    projected_coordinates = []

    for point in ring:

        try:

            longitude = float(
                point[0]
            )

            latitude = float(
                point[1]
            )

        except (
            TypeError,
            ValueError,
            IndexError
        ):
            continue

        x, y = TO_LOCAL.transform(
            longitude,
            latitude
        )

        projected_coordinates.append(
            (
                x,
                y
            )
        )

    if len(projected_coordinates) < 4:
        return None

    polygon = Polygon(
        projected_coordinates
    )

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


def classify_zone_constraint(
    terrain_class: str
) -> str:

    if terrain_class in {
        "steep",
        "very_steep"
    }:
        return "major"

    if terrain_class == "moderate_slope":
        return "moderate"

    return "low"


def transform_geometry_to_wgs84(
    geometry
):

    geometry_mapping = mapping(
        geometry
    )

    geometry_type = geometry_mapping.get(
        "type"
    )

    coordinates = geometry_mapping.get(
        "coordinates"
    )

    def transform_coordinate_pair(
        coordinate_pair
    ):

        longitude, latitude = TO_WGS84.transform(
            coordinate_pair[0],
            coordinate_pair[1]
        )

        return [
            longitude,
            latitude
        ]

    if geometry_type == "Polygon":

        return {
            "type": "Polygon",
            "coordinates": [
                [
                    transform_coordinate_pair(
                        coordinate_pair
                    )
                    for coordinate_pair in ring
                ]
                for ring in coordinates
            ]
        }

    if geometry_type == "MultiPolygon":

        return {
            "type": "MultiPolygon",
            "coordinates": [
                [
                    [
                        transform_coordinate_pair(
                            coordinate_pair
                        )
                        for coordinate_pair in ring
                    ]
                    for ring in polygon
                ]
                for polygon in coordinates
            ]
        }

    return geometry_mapping


def build_slope_zone_geojson(
    elevation_results: list[dict],
    parcel_boundary: dict | None
) -> dict | None:

    if not isinstance(
        parcel_boundary,
        dict
    ):
        return None

    parcel_polygon = projected_parcel_polygon(
        parcel_boundary
    )

    if parcel_polygon is None:
        return None

    local_results = calculate_local_sample_slopes(
        elevation_results
    )

    if len(local_results) < 2:
        return None

    projected_samples = []

    for result in local_results:

        latitude, longitude = result[
            "point"
        ]

        x, y = TO_LOCAL.transform(
            longitude,
            latitude
        )

        projected_samples.append({
            "geometry": Point(
                x,
                y
            ),
            "result": result
        })

    sample_points = MultiPoint(
        [
            item["geometry"]
            for item in projected_samples
        ]
    )

    try:

        cells = voronoi_diagram(
            sample_points,
            envelope=parcel_polygon.envelope.buffer(
                100
            ),
            edges=False
        )

    except Exception:
        return None

    features = []

    for cell in cells.geoms:

        clipped_cell = cell.intersection(
            parcel_polygon
        )

        if clipped_cell.is_empty:
            continue

        simplified_cell = clipped_cell.simplify(
            SLOPE_ZONE_SIMPLIFICATION_FEET,
            preserve_topology=True
        )

        if simplified_cell.is_empty:
            continue

        if simplified_cell.geom_type == "GeometryCollection":

            polygon_parts = [
                geometry
                for geometry in simplified_cell.geoms
                if geometry.geom_type in {
                    "Polygon",
                    "MultiPolygon"
                }
                and not geometry.is_empty
            ]

            if not polygon_parts:
                continue

            simplified_cell = max(
                polygon_parts,
                key=lambda geometry: geometry.area
            )

        representative_point = simplified_cell.representative_point()

        nearest_sample = min(
            projected_samples,
            key=lambda item: representative_point.distance(
                item["geometry"]
            )
        )

        result = nearest_sample[
            "result"
        ]

        local_slope_percent = result[
            "local_slope_percent"
        ]

        terrain_class = result[
            "terrain_class"
        ]

        features.append({
            "type": "Feature",
            "properties": {
                "role": "preliminary_slope_zone",
                "local_slope_percent": round(
                    local_slope_percent,
                    2
                ),
                "terrain_class": terrain_class,
                "elevation_feet": round(
                    result["elevation"],
                    2
                ),
                "constraint_level": (
                    classify_zone_constraint(
                        terrain_class
                    )
                ),
                "analysis_method": (
                    "sample_voronoi_interpolation"
                ),
                "geometry_simplification_feet": (
                    SLOPE_ZONE_SIMPLIFICATION_FEET
                ),
                "survey_grade": False
            },
            "geometry": (
                transform_geometry_to_wgs84(
                    simplified_cell
                )
            )
        })

    if not features:
        return None

    return {
        "type": "FeatureCollection",
        "features": features
    }


def get_terrain_data(
    latitude: float,
    longitude: float,
    parcel_boundary: dict | None = None
) -> dict:

    boundary_available = (
        isinstance(
            parcel_boundary,
            dict
        )
        and parcel_boundary.get("status") == "found"
        and bool(
            parcel_boundary.get("rings")
        )
    )

    if boundary_available:

        sample_points = build_parcel_sample_points(
            latitude=latitude,
            longitude=longitude,
            parcel_boundary=parcel_boundary
        )

        analysis_scope = (
            "parcel_wide_sample"
        )

    else:

        sample_points = build_local_sample_points(
            latitude=latitude,
            longitude=longitude
        )

        analysis_scope = (
            "local_point_sample"
        )

    if not sample_points:

        return empty_terrain_result(
            status="not_found",
            message=(
                "Housing OS could not create usable "
                "terrain sample points."
            ),
            analysis_scope=analysis_scope
        )

    elevation_results = fetch_elevations(
        sample_points=sample_points
    )

    minimum_required_samples = (
        4
        if analysis_scope == "parcel_wide_sample"
        else 3
    )

    if (
        len(elevation_results)
        < minimum_required_samples
    ):

        return empty_terrain_result(
            status="not_found",
            message=(
                "The USGS elevation service did not return "
                "enough usable samples for terrain analysis."
            ),
            analysis_scope=analysis_scope
        )

    center_elevation = None
    center_distance = None

    center_point = (
        latitude,
        longitude
    )

    for result in elevation_results:

        current_distance = distance_feet(
            center_point,
            result["point"]
        )

        if (
            center_distance is None
            or current_distance < center_distance
        ):

            center_distance = current_distance
            center_elevation = result[
                "elevation"
            ]

    elevations = [
        result["elevation"]
        for result in elevation_results
    ]

    minimum_elevation = min(
        elevations
    )

    maximum_elevation = max(
        elevations
    )

    elevation_change = (
        maximum_elevation
        - minimum_elevation
    )

    (
        estimated_slope_percent,
        representative_distance
    ) = calculate_maximum_sampled_slope(
        elevation_results=elevation_results
    )

    if estimated_slope_percent is None:

        return empty_terrain_result(
            status="not_found",
            message=(
                "Housing OS retrieved elevations but could "
                "not calculate a usable sampled slope."
            ),
            analysis_scope=analysis_scope
        )

    estimated_slope_degrees = math.degrees(
        math.atan(
            estimated_slope_percent
            / 100
        )
    )

    interpretation = classify_terrain(
        slope_percent=estimated_slope_percent,
        analysis_scope=analysis_scope
    )

    if analysis_scope == "parcel_wide_sample":

        message = (
            "This is a preliminary parcel-wide terrain "
            f"screening based on {len(elevation_results)} "
            "elevation samples placed within the mapped "
            "parcel polygon. It is not a topographic survey "
            "and may miss localized steep areas."
        )

    else:

        message = (
            "The parcel polygon was unavailable, so Housing "
            "OS used a preliminary local terrain estimate "
            f"based on {len(elevation_results)} elevation "
            "samples near the lookup point."
        )

    slope_sample_geojson = build_slope_sample_geojson(
        elevation_results=elevation_results
    )

    slope_zone_geojson = build_slope_zone_geojson(
        elevation_results=elevation_results,
        parcel_boundary=parcel_boundary
    )

    slope_zone_count = (
        len(
            slope_zone_geojson.get(
                "features",
                []
            )
        )
        if slope_zone_geojson
        else 0
    )

    return {
        "center_elevation_feet": round(
            center_elevation,
            2
        ),
        "minimum_sample_elevation_feet": round(
            minimum_elevation,
            2
        ),
        "maximum_sample_elevation_feet": round(
            maximum_elevation,
            2
        ),
        "elevation_change_feet": round(
            elevation_change,
            2
        ),
        "estimated_slope_percent": round(
            estimated_slope_percent,
            2
        ),
        "estimated_slope_degrees": round(
            estimated_slope_degrees,
            2
        ),
        "terrain_class": interpretation[
            "terrain_class"
        ],
        "development_warning": interpretation[
            "development_warning"
        ],
        "sample_distance_feet": (
            round(
                representative_distance
            )
            if representative_distance
            else None
        ),
        "analysis_scope": analysis_scope,
        "slope_sample_count": len(
            elevation_results
        ),
        "slope_sample_geojson": (
            slope_sample_geojson
        ),
        "slope_zone_count": slope_zone_count,
        "slope_zone_geojson": slope_zone_geojson,
        "status": "found",
        "source": (
            "USGS 3DEP Elevation Point Query Service "
            "and County of San Diego Assessor Parcels"
        ),
        "message": message
    }
