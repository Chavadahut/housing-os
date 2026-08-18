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
    "DPLU/DPLU_Map/MapServer/54/query"
)

MAX_WORKERS = 8
GIS_TIMEOUT_SECONDS = 15

to_2230 = Transformer.from_crs(
    "EPSG:4326",
    "EPSG:2230",
    always_xy=True,
)


def clean_text(value) -> str | None:
    if not isinstance(value, str):
        return None

    cleaned = value.strip()
    return cleaned or None


def clean_wetland_type(value) -> str | None:
    cleaned = clean_text(value)

    if cleaned is None:
        return None

    if cleaned.upper() in {
        "YES", "Y", "NO", "N", "TRUE", "FALSE",
        "T", "F", "1", "0", "-", "NONE",
        "NULL", "N/A", "NA",
    }:
        return None

    return cleaned


def interpret_boolean_indicator(value) -> bool | None:
    if value is None:
        return None

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return value > 0

    if isinstance(value, str):
        normalized = value.strip().upper()

        if normalized in {"YES", "Y", "TRUE", "T", "1"}:
            return True

        if normalized in {"NO", "N", "FALSE", "F", "0", ""}:
            return False

    return None


def attributes_have_positive_evidence(attributes: dict) -> bool:
    hydric_indicator = interpret_boolean_indicator(
        attributes.get("HYDRIC")
    )

    if hydric_indicator is None:
        hydric_indicator = interpret_boolean_indicator(
            attributes.get("HYDRIC_SOILS_")
        )

    return any(
        value is True
        for value in [
            interpret_boolean_indicator(
                attributes.get("WETLAND")
            ),
            interpret_boolean_indicator(
                attributes.get("VERNAL")
            ),
            hydric_indicator,
        ]
    )


def extract_wetland_type(attributes: dict) -> str | None:
    return (
        clean_wetland_type(attributes.get("DESCRIPTION"))
        or clean_wetland_type(attributes.get("TITLE"))
        or clean_wetland_type(attributes.get("WETLAND_"))
        or clean_wetland_type(attributes.get("HOLLAND95"))
    )


def empty_wetlands_result(status: str, message: str) -> dict:
    return {
        "mapped_wetland": None,
        "parcel_intersection_detected": None,
        "wetland_type": None,
        "wetland_types": [],
        "description": None,
        "holland_code": None,
        "wetland_indicator": None,
        "vernal_pool_indicator": None,
        "hydric_soils_indicator": None,
        "parcel_overlap_percent": None,
        "constrained_acres": None,
        "unconstrained_acres": None,
        "intersecting_feature_count": 0,
        "sample_count": 0,
        "successful_sample_count": 0,
        "constraint_level": None,
        "development_warning": None,
        "status": status,
        "source": "County of San Diego Wetlands RPO Layer",
        "message": message,
        "lookup_method": None,
        "search_distance_feet": None,
        "analysis_scope": "parcel_wide_polygon",
    }


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


def query_wetlands_polygon(
    parcel_boundary: dict | None,
) -> list[dict]:
    parcel_polygon = _parcel_polygon_2230(parcel_boundary)

    if parcel_polygon is None:
        return []

    rings = []

    if parcel_polygon.geom_type == "Polygon":
        rings.append([
            [float(x), float(y)]
            for x, y in parcel_polygon.exterior.coords
        ])
    else:
        for polygon in parcel_polygon.geoms:
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
        "outFields": (
            "WETLAND,HOLLAND95,VERNAL,"
            "HYDRIC,HYDRIC_SOILS_,"
            "WETLAND_,TITLE,CODE_,DESCRIPTION"
        ),
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

    positive_features = []
    positive_geometries = []

    for feature in features:
        attributes = feature.get("attributes") or {}

        if not attributes_have_positive_evidence(attributes):
            continue

        feature_geometry = _arcgis_geometry_to_shapely(
            feature.get("geometry")
        )

        if feature_geometry is None:
            continue

        intersection = parcel_polygon.intersection(
            feature_geometry
        )

        if intersection.is_empty or intersection.area <= 0:
            continue

        positive_features.append(attributes)
        positive_geometries.append(intersection)

    if positive_geometries:
        constrained_geometry = unary_union(
            positive_geometries
        )

        constrained_area = float(
            constrained_geometry.area
        )

        parcel_overlap_percent = round(
            min(
                100.0,
                constrained_area
                / parcel_polygon.area
                * 100,
            ),
            2,
        )
    else:
        constrained_area = 0.0
        parcel_overlap_percent = 0.0

    constrained_acres = (
        round(
            parcel_acres
            * parcel_overlap_percent
            / 100,
            3,
        )
        if parcel_acres is not None
        else round(
            constrained_area / 43560,
            3,
        )
    )

    unconstrained_percent = round(
        max(0.0, 100 - parcel_overlap_percent),
        2,
    )

    unconstrained_acres = (
        round(
            parcel_acres
            * unconstrained_percent
            / 100,
            3,
        )
        if parcel_acres is not None
        else None
    )

    wetland_types = sorted({
        wetland_type
        for wetland_type in [
            extract_wetland_type(attributes)
            for attributes in positive_features
        ]
        if wetland_type
    })

    representative = (
        positive_features[0]
        if positive_features
        else {}
    )

    wetland_indicator = interpret_boolean_indicator(
        representative.get("WETLAND")
    )

    vernal_indicator = interpret_boolean_indicator(
        representative.get("VERNAL")
    )

    hydric_indicator = interpret_boolean_indicator(
        representative.get("HYDRIC")
    )

    if hydric_indicator is None:
        hydric_indicator = interpret_boolean_indicator(
            representative.get("HYDRIC_SOILS_")
        )

    related_feature_intersection = bool(positive_features)
    mapped_wetland = wetland_indicator is True

    if related_feature_intersection:
        constraint_level = (
            "major"
            if parcel_overlap_percent >= 10
            else "moderate"
        )

        warning = (
            "Mapped wetland-related, vernal-pool, or hydric-soil indicators "
            "intersect the parcel. Delineation, buffers, avoidance, "
            "drainage review, mitigation, or agency permits may be "
            "required."
        )

        status = "found"
    else:
        constraint_level = "not_mapped"

        warning = (
            "No positive mapped wetland, vernal-pool, or hydric-soil "
            "polygon intersected the parcel. Unmapped streams, drainage "
            "features, or jurisdictional waters may still be present."
        )

        status = "not_found"

    return {
        "mapped_wetland": mapped_wetland,
        "parcel_intersection_detected": related_feature_intersection,
        "wetland_type": (
            wetland_types[0]
            if wetland_types
            else None
        ),
        "wetland_types": wetland_types,
        "description": clean_wetland_type(
            representative.get("DESCRIPTION")
        ),
        "holland_code": clean_wetland_type(
            representative.get("HOLLAND95")
        ),
        "wetland_indicator": wetland_indicator,
        "vernal_pool_indicator": vernal_indicator,
        "hydric_soils_indicator": hydric_indicator,
        "parcel_overlap_percent": parcel_overlap_percent,
        "constrained_acres": constrained_acres,
        "unconstrained_acres": unconstrained_acres,
        "intersecting_feature_count": len(positive_features),
        "sample_count": 0,
        "successful_sample_count": 0,
        "constraint_level": constraint_level,
        "development_warning": warning,
        "status": status,
        "source": "County of San Diego Wetlands RPO Layer",
        "message": (
            "Housing OS calculated preliminary mapped overlap from "
            "wetland-related polygons intersecting the parcel. This "
            "does not replace a wetland delineation, drainage study, "
            "biological survey, or agency determination."
        ),
        "lookup_method": "parcel_polygon_intersection",
        "search_distance_feet": 0,
        "analysis_scope": "parcel_wide_polygon",
    }


# ---------------- Sampling fallback ----------------

def query_wetlands_point(
    latitude: float,
    longitude: float,
) -> list[dict]:
    x, y = to_2230.transform(longitude, latitude)

    params = {
        "where": "1=1",
        "geometry": f"{x},{y}",
        "geometryType": "esriGeometryPoint",
        "inSR": "2230",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": (
            "WETLAND,HOLLAND95,VERNAL,"
            "HYDRIC,HYDRIC_SOILS_,"
            "WETLAND_,TITLE,CODE_,DESCRIPTION"
        ),
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

    return [
        feature.get("attributes", {})
        for feature in data.get("features", [])
    ]


def fetch_wetland_samples(
    sample_points: list[tuple[float, float]],
) -> tuple[list[list[dict]], int]:
    results = []
    successful_count = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [
            executor.submit(
                query_wetlands_point,
                latitude,
                longitude,
            )
            for latitude, longitude in sample_points
        ]

        for future in as_completed(futures):
            try:
                attributes_list = future.result()
            except (requests.RequestException, ValueError):
                continue

            successful_count += 1
            results.append(attributes_list)

    return results, successful_count


def build_sampling_result(
    sample_results: list[list[dict]],
    successful_count: int,
    sample_points: list[tuple[float, float]],
    parcel_acres: float | None,
    parcel_wide: bool,
) -> dict:
    positive_sample_count = 0
    positive_attributes = []

    for attributes_list in sample_results:
        matching_attributes = [
            attributes
            for attributes in attributes_list
            if attributes_have_positive_evidence(attributes)
        ]

        if matching_attributes:
            positive_sample_count += 1
            positive_attributes.extend(matching_attributes)

    mapped_wetland = bool(positive_attributes)

    parcel_overlap_percent = percent_of_samples(
        matching_count=positive_sample_count,
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

    wetland_types = sorted({
        wetland_type
        for wetland_type in [
            extract_wetland_type(attributes)
            for attributes in positive_attributes
        ]
        if wetland_type
    })

    representative = (
        positive_attributes[0]
        if positive_attributes
        else {}
    )

    if mapped_wetland:
        constraint_level = (
            "major"
            if (
                parcel_overlap_percent is not None
                and parcel_overlap_percent >= 10
            )
            else "moderate"
        )
        status = "found"
    else:
        constraint_level = "not_mapped"
        status = "not_found"

    return {
        "mapped_wetland": mapped_wetland,
        "parcel_intersection_detected": None,
        "wetland_type": (
            wetland_types[0]
            if wetland_types
            else None
        ),
        "wetland_types": wetland_types,
        "description": clean_wetland_type(
            representative.get("DESCRIPTION")
        ),
        "holland_code": clean_wetland_type(
            representative.get("HOLLAND95")
        ),
        "wetland_indicator": interpret_boolean_indicator(
            representative.get("WETLAND")
        ),
        "vernal_pool_indicator": interpret_boolean_indicator(
            representative.get("VERNAL")
        ),
        "hydric_soils_indicator": (
            interpret_boolean_indicator(
                representative.get("HYDRIC")
            )
            if interpret_boolean_indicator(
                representative.get("HYDRIC")
            ) is not None
            else interpret_boolean_indicator(
                representative.get("HYDRIC_SOILS_")
            )
        ),
        "parcel_overlap_percent": parcel_overlap_percent,
        "constrained_acres": constrained_acres,
        "unconstrained_acres": unconstrained_acres,
        "intersecting_feature_count": 0,
        "sample_count": len(sample_points),
        "successful_sample_count": successful_count,
        "constraint_level": constraint_level,
        "development_warning": (
            "Housing OS used its parcel-grid fallback because usable "
            "wetland polygon geometry was not available. A formal "
            "wetland review may still be required."
        ),
        "status": status,
        "source": "County of San Diego Wetlands RPO Layer",
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


def get_wetlands_data(
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
            polygon_features = query_wetlands_polygon(
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
                "[Housing OS wetlands] Polygon intersection "
                f"unavailable; using sample fallback: {error}"
            )

    sample_points = build_parcel_sample_points(
        parcel_boundary=parcel_boundary,
        fallback_latitude=latitude,
        fallback_longitude=longitude,
    )

    try:
        sample_results, successful_count = fetch_wetland_samples(
            sample_points=sample_points
        )
    except requests.Timeout:
        return empty_wetlands_result(
            status="timeout",
            message=(
                "The wetlands GIS server took too long to respond."
            ),
        )
    except requests.RequestException as error:
        return empty_wetlands_result(
            status="error",
            message=str(error),
        )

    return build_sampling_result(
        sample_results=sample_results,
        successful_count=successful_count,
        sample_points=sample_points,
        parcel_acres=parcel_acres,
        parcel_wide=parcel_wide,
    )
