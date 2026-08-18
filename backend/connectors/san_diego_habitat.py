from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import json

import requests
from pyproj import Transformer
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union

from connectors.parcel_sampling import (
    build_parcel_sample_points,
    estimate_acres,
    percent_of_samples,
)


URL = (
    "https://gis-public.sandiegocounty.gov/arcgis/rest/services/"
    "BCMS_DPLU_Overlay_Map/MapServer/13/query"
)

MAX_WORKERS = 8
GIS_TIMEOUT_SECONDS = 15

to_2230 = Transformer.from_crs(
    "EPSG:4326",
    "EPSG:2230",
    always_xy=True,
)

to_4326 = Transformer.from_crs(
    "EPSG:2230",
    "EPSG:4326",
    always_xy=True,
)


def empty_habitat_result(status: str, message: str) -> dict:
    return {
        "habitat_value": None,
        "dominant_habitat_value": None,
        "grid_code": None,
        "habitat_id": None,
        "habitat_breakdown": [],
        "parcel_overlap_percent": None,
        "constrained_acres": None,
        "unconstrained_acres": None,
        "intersecting_feature_count": 0,
        "sample_count": 0,
        "successful_sample_count": 0,
        "constraint_level": None,
        "development_warning": None,
        "status": status,
        "source": "County of San Diego Habitat Evaluation Model",
        "message": message,
        "lookup_method": None,
        "search_distance_feet": None,
        "analysis_scope": "parcel_wide_polygon",
    }


def normalize_habitat_value(habitat_value: str | None) -> str:
    if not isinstance(habitat_value, str):
        return "Unknown"

    cleaned = habitat_value.strip()
    return cleaned.title() if cleaned else "Unknown"


def habitat_constraint_level(habitat_value: str | None) -> str:
    normalized_value = (
        habitat_value.strip().upper()
        if isinstance(habitat_value, str)
        else ""
    )

    if normalized_value in {"VERY HIGH", "HIGH"}:
        return "major"

    if normalized_value == "MODERATE":
        return "moderate"

    if normalized_value == "AGRICULTURE":
        return "agricultural"

    if normalized_value == "LOW":
        return "low"

    if normalized_value == "DEVELOPED":
        return "developed"

    return "unknown"


def _parcel_polygon_2230(parcel_boundary: dict | None):
    if not isinstance(parcel_boundary, dict):
        return None

    rings = parcel_boundary.get("rings") or []

    if not rings:
        return None

    polygons = []

    for ring in rings:
        if not isinstance(ring, list) or len(ring) < 4:
            continue

        projected = [
            to_2230.transform(float(lon), float(lat))
            for lon, lat in ring
        ]

        polygon = Polygon(projected)

        if not polygon.is_valid:
            polygon = polygon.buffer(0)

        if not polygon.is_empty:
            polygons.append(polygon)

    if not polygons:
        return None

    merged = unary_union(polygons)

    if not merged.is_valid:
        merged = merged.buffer(0)

    return merged


def _arcgis_geometry_to_shapely(geometry: dict | None):
    if not isinstance(geometry, dict):
        return None

    rings = geometry.get("rings") or []

    if not rings:
        return None

    polygons = []

    for ring in rings:
        if not isinstance(ring, list) or len(ring) < 4:
            continue

        polygon = Polygon(
            [(float(x), float(y)) for x, y in ring]
        )

        if not polygon.is_valid:
            polygon = polygon.buffer(0)

        if not polygon.is_empty:
            polygons.append(polygon)

    if not polygons:
        return None

    result = unary_union(polygons)

    if not result.is_valid:
        result = result.buffer(0)

    return result


def query_habitat_polygon(parcel_boundary: dict | None) -> list[dict]:
    parcel_polygon = _parcel_polygon_2230(parcel_boundary)

    if parcel_polygon is None:
        return []

    if isinstance(parcel_polygon, MultiPolygon):
        query_polygon = unary_union(parcel_polygon)
    else:
        query_polygon = parcel_polygon

    rings = []

    if query_polygon.geom_type == "Polygon":
        rings.append([
            [float(x), float(y)]
            for x, y in query_polygon.exterior.coords
        ])
    else:
        for polygon in query_polygon.geoms:
            rings.append([
                [float(x), float(y)]
                for x, y in polygon.exterior.coords
            ])

    params = {
        "where": "1=1",
        "geometry": json.dumps({
            "rings": rings,
            "spatialReference": {"wkid": 2230},
        }),
        "geometryType": "esriGeometryPolygon",
        "inSR": "2230",
        "outSR": "2230",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "ID,GRIDCODE,DESC_",
        "returnGeometry": "true",
        "f": "json",
    }

    response = requests.post(
        URL,
        data=params,
        timeout=GIS_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    data = response.json()

    if data.get("error"):
        raise requests.RequestException(str(data["error"]))

    return data.get("features") or []


def build_polygon_result(
    features: list[dict],
    parcel_boundary: dict | None,
    parcel_acres: float | None,
) -> dict | None:
    parcel_polygon = _parcel_polygon_2230(parcel_boundary)

    if parcel_polygon is None or parcel_polygon.area <= 0:
        return None

    area_by_value = {}
    representative_by_value = {}
    feature_ids = set()
    total_intersection_area = 0.0

    for feature in features:
        attributes = feature.get("attributes") or {}
        feature_geometry = _arcgis_geometry_to_shapely(
            feature.get("geometry")
        )

        if feature_geometry is None:
            continue

        intersection = parcel_polygon.intersection(feature_geometry)

        if intersection.is_empty:
            continue

        overlap_area = float(intersection.area)

        if overlap_area <= 0:
            continue

        habitat_value = normalize_habitat_value(
            attributes.get("DESC_")
        )

        area_by_value[habitat_value] = (
            area_by_value.get(habitat_value, 0.0)
            + overlap_area
        )

        representative_by_value.setdefault(
            habitat_value,
            attributes,
        )

        habitat_id = attributes.get("ID")

        if habitat_id is not None:
            feature_ids.add(str(habitat_id))

        total_intersection_area += overlap_area

    if not area_by_value:
        return None

    breakdown = []
    constrained_area = 0.0

    for habitat_value, overlap_area in sorted(
        area_by_value.items(),
        key=lambda item: item[1],
        reverse=True,
    ):
        parcel_percent = round(
            (overlap_area / parcel_polygon.area) * 100,
            2,
        )

        constraint_level = habitat_constraint_level(
            habitat_value
        )

        estimated_overlap_acres = (
            round(parcel_acres * parcel_percent / 100, 3)
            if parcel_acres is not None
            else round(overlap_area / 43560, 3)
        )

        if constraint_level in {
            "major",
            "moderate",
            "agricultural",
        }:
            constrained_area += overlap_area

        breakdown.append({
            "habitat_value": habitat_value,
            "sample_count": 0,
            "parcel_percent": parcel_percent,
            "estimated_acres": estimated_overlap_acres,
            "constraint_level": constraint_level,
        })

    dominant_habitat_value = max(
        area_by_value,
        key=area_by_value.get,
    )

    constrained_percent = round(
        min(100.0, constrained_area / parcel_polygon.area * 100),
        2,
    )

    constrained_acres = (
        round(parcel_acres * constrained_percent / 100, 3)
        if parcel_acres is not None
        else round(constrained_area / 43560, 3)
    )

    unconstrained_percent = round(
        max(0.0, 100 - constrained_percent),
        2,
    )

    unconstrained_acres = (
        round(parcel_acres * unconstrained_percent / 100, 3)
        if parcel_acres is not None
        else None
    )

    major_percent = sum(
        item["parcel_percent"] or 0
        for item in breakdown
        if item["constraint_level"] == "major"
    )

    if major_percent >= 25:
        overall_constraint = "major"
    elif constrained_percent > 0:
        overall_constraint = "moderate"
    else:
        overall_constraint = habitat_constraint_level(
            dominant_habitat_value
        )

    representative = representative_by_value.get(
        dominant_habitat_value,
        {},
    )

    if overall_constraint == "major":
        warning = (
            "A substantial mapped portion of the parcel intersects "
            "High or Very High habitat value. Biological surveys, "
            "avoidance, mitigation, reduced development area, "
            "open-space preservation, or agency consultation may "
            "be required."
        )
    elif overall_constraint == "moderate":
        warning = (
            "Mapped habitat conditions intersect part of the parcel "
            "and may affect usable development area. Parcel-wide "
            "biological review is recommended."
        )
    else:
        warning = (
            "The mapped parcel intersection did not show a major "
            "habitat constraint, but site-specific biological review "
            "may still be required."
        )

    return {
        "habitat_value": dominant_habitat_value,
        "dominant_habitat_value": dominant_habitat_value,
        "grid_code": representative.get("GRIDCODE"),
        "habitat_id": representative.get("ID"),
        "habitat_breakdown": breakdown,
        "parcel_overlap_percent": constrained_percent,
        "constrained_acres": constrained_acres,
        "unconstrained_acres": unconstrained_acres,
        "intersecting_feature_count": len(feature_ids),
        "sample_count": 0,
        "successful_sample_count": 0,
        "constraint_level": overall_constraint,
        "development_warning": warning,
        "status": "found",
        "source": "County of San Diego Habitat Evaluation Model",
        "message": (
            "Housing OS calculated preliminary parcel overlap from "
            "mapped habitat polygons intersecting the parcel. This is "
            "more direct than grid sampling but still does not replace "
            "a biological survey or agency determination."
        ),
        "lookup_method": "parcel_polygon_intersection",
        "search_distance_feet": 0,
        "analysis_scope": "parcel_wide_polygon",
    }


# ---------------- Sampling fallback ----------------

def query_habitat_point(
    latitude: float,
    longitude: float,
) -> dict | None:
    x, y = to_2230.transform(longitude, latitude)

    params = {
        "where": "1=1",
        "geometry": f"{x},{y}",
        "geometryType": "esriGeometryPoint",
        "inSR": "2230",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "ID,GRIDCODE,DESC_",
        "returnGeometry": "false",
        "f": "json",
    }

    response = requests.get(
        URL,
        params=params,
        timeout=GIS_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    data = response.json()

    if data.get("error"):
        raise requests.RequestException(str(data["error"]))

    features = data.get("features", [])

    if not features:
        return None

    return features[0].get("attributes", {})


def fetch_habitat_samples(
    sample_points: list[tuple[float, float]],
) -> list[dict]:
    results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {
            executor.submit(
                query_habitat_point,
                latitude,
                longitude,
            ): (latitude, longitude)
            for latitude, longitude in sample_points
        }

        for future in as_completed(future_map):
            try:
                attributes = future.result()
            except (requests.RequestException, ValueError):
                continue

            if attributes is not None:
                results.append(attributes)

    return results


def build_sampling_result(
    sample_results: list[dict],
    sample_points: list[tuple[float, float]],
    parcel_wide: bool,
    parcel_acres: float | None,
) -> dict:
    if not sample_results:
        result = empty_habitat_result(
            status="not_found",
            message=(
                "No usable Habitat Evaluation Model polygon or "
                "sample results were returned for the parcel."
            ),
        )
        result["sample_count"] = len(sample_points)
        return result

    value_counts = Counter()
    feature_ids = set()
    representative_by_value = {}

    for attributes in sample_results:
        habitat_value = normalize_habitat_value(
            attributes.get("DESC_")
        )

        value_counts[habitat_value] += 1

        habitat_id = attributes.get("ID")

        if habitat_id is not None:
            feature_ids.add(str(habitat_id))

        representative_by_value.setdefault(
            habitat_value,
            attributes,
        )

    successful_count = len(sample_results)
    dominant_habitat_value = value_counts.most_common(1)[0][0]

    breakdown = []
    constrained_sample_count = 0

    for habitat_value, count in value_counts.most_common():
        parcel_percent = percent_of_samples(
            matching_count=count,
            successful_count=successful_count,
        )

        constraint_level = habitat_constraint_level(
            habitat_value
        )

        if constraint_level in {
            "major",
            "moderate",
            "agricultural",
        }:
            constrained_sample_count += count

        breakdown.append({
            "habitat_value": habitat_value,
            "sample_count": count,
            "parcel_percent": parcel_percent,
            "estimated_acres": estimate_acres(
                parcel_acres=parcel_acres,
                percent=parcel_percent,
            ),
            "constraint_level": constraint_level,
        })

    parcel_overlap_percent = percent_of_samples(
        matching_count=constrained_sample_count,
        successful_count=successful_count,
    )

    constrained_acres = estimate_acres(
        parcel_acres=parcel_acres,
        percent=parcel_overlap_percent,
    )

    unconstrained_percent = (
        round(100 - parcel_overlap_percent, 2)
        if parcel_overlap_percent is not None
        else None
    )

    unconstrained_acres = estimate_acres(
        parcel_acres=parcel_acres,
        percent=unconstrained_percent,
    )

    major_percent = sum(
        item["parcel_percent"] or 0
        for item in breakdown
        if item["constraint_level"] == "major"
    )

    if major_percent >= 25:
        overall_constraint = "major"
    elif parcel_overlap_percent:
        overall_constraint = "moderate"
    else:
        overall_constraint = habitat_constraint_level(
            dominant_habitat_value
        )

    representative = representative_by_value.get(
        dominant_habitat_value,
        {},
    )

    return {
        "habitat_value": dominant_habitat_value,
        "dominant_habitat_value": dominant_habitat_value,
        "grid_code": representative.get("GRIDCODE"),
        "habitat_id": representative.get("ID"),
        "habitat_breakdown": breakdown,
        "parcel_overlap_percent": parcel_overlap_percent,
        "constrained_acres": constrained_acres,
        "unconstrained_acres": unconstrained_acres,
        "intersecting_feature_count": len(feature_ids),
        "sample_count": len(sample_points),
        "successful_sample_count": successful_count,
        "constraint_level": overall_constraint,
        "development_warning": (
            "Housing OS used its parcel-grid fallback because usable "
            "habitat polygon geometry was not available. Biological "
            "review may still be required."
        ),
        "status": "found",
        "source": "County of San Diego Habitat Evaluation Model",
        "message": (
            "Polygon intersection was unavailable, so Housing OS "
            f"used {successful_count} successful GIS samples as a "
            "fallback. Percentages and acreage are approximate."
        ),
        "lookup_method": (
            "parcel_grid_sample_fallback"
            if parcel_wide
            else "exact_point"
        ),
        "search_distance_feet": 0,
        "analysis_scope": (
            "parcel_wide_sample"
            if parcel_wide
            else "point_based_screening"
        ),
    }


def get_habitat_data(
    latitude: float,
    longitude: float,
    parcel_boundary: dict | None = None,
    parcel_acres: float | None = None,
) -> dict:
    parcel_wide = (
        isinstance(parcel_boundary, dict)
        and parcel_boundary.get("status") == "found"
        and bool(parcel_boundary.get("rings"))
    )

    if parcel_wide:
        try:
            polygon_features = query_habitat_polygon(
                parcel_boundary=parcel_boundary
            )

            polygon_result = build_polygon_result(
                features=polygon_features,
                parcel_boundary=parcel_boundary,
                parcel_acres=parcel_acres,
            )

            if polygon_result is not None:
                return polygon_result

        except (requests.RequestException, ValueError, TypeError) as error:
            print(
                "[Housing OS habitat] Polygon intersection "
                f"unavailable; using sample fallback: {error}"
            )

    sample_points = build_parcel_sample_points(
        parcel_boundary=parcel_boundary,
        fallback_latitude=latitude,
        fallback_longitude=longitude,
    )

    try:
        sample_results = fetch_habitat_samples(
            sample_points=sample_points
        )
    except requests.Timeout:
        return empty_habitat_result(
            status="timeout",
            message=(
                "The habitat GIS server took too long to respond."
            ),
        )
    except requests.RequestException as error:
        return empty_habitat_result(
            status="error",
            message=str(error),
        )

    return build_sampling_result(
        sample_results=sample_results,
        sample_points=sample_points,
        parcel_wide=parcel_wide,
        parcel_acres=parcel_acres,
    )