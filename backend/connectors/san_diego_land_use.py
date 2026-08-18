import requests

from pyproj import Transformer
from shapely.geometry import Polygon, shape
from shapely.ops import transform, unary_union


URL = (
    "https://gis-public.sandiegocounty.gov/arcgis/rest/services/"
    "HCD/HCD_Map/FeatureServer/7/query"
)

transformer_to_2230 = Transformer.from_crs(
    "EPSG:4326",
    "EPSG:2230",
    always_xy=True,
)


LAND_USE_CATEGORIES = {
    1000: "Spaced Rural Residential",
    1090: "Spaced Rural Residential",
    1100: "Residential",
    1110: "Residential",
    1120: "Residential",
    1190: "Residential",
    1200: "Residential",
    1280: "Residential",
    1290: "Residential",
    1300: "Residential",
    1401: "Institution",
    1402: "Institution",
    1403: "Military",
    1404: "Institution",
    1409: "Institution",
    1501: "Commercial and Office",
    1502: "Commercial and Office",
    1503: "Commercial and Office",
    2001: "Industry",
    2101: "Industry",
    2103: "Industry",
    2104: "Industry",
    2105: "Industry",
    2201: "Industry",
    2301: "Transportation, Communication, Utilities",
    5001: "Commercial and Office",
    5002: "Commercial and Office",
    5003: "Commercial and Office",
    5004: "Commercial and Office",
    5005: "Commercial and Office",
    5006: "Commercial and Office",
    5007: "Commercial and Office",
    5008: "Commercial and Office",
    5009: "Commercial and Office",
    6001: "Commercial and Office",
    6002: "Commercial and Office",
    6003: "Commercial and Office",
    6101: "Institution",
    6102: "Institution",
    6103: "Institution",
    6104: "Institution",
    6105: "Institution",
    6108: "Institution",
    6109: "Institution",
    6501: "Institution",
    6502: "Institution",
    6509: "Institution",
    6701: "Military",
    6702: "Military",
    6703: "Military",
    6800: "Institution",
    6801: "Institution",
    6802: "Institution",
    6803: "Institution",
    6804: "Institution",
    6805: "Institution",
    6806: "Institution",
    6807: "Institution",
    6809: "Institution",
    9201: "Water",
    9202: "Water",
    9700: "Commercial and Office",
}


def empty_land_use_result(
    status: str,
    message: str,
) -> dict:
    return {
        "code": None,
        "category": None,
        "description": None,
        "dominant_code": None,
        "dominant_category": None,
        "dominant_description": None,
        "land_use_breakdown": [],
        "mixed_land_use": None,
        "parcel_overlap_percent": None,
        "status": status,
        "source": "SANDAG Current Land Use",
        "message": message,
        "lookup_method": None,
        "search_distance_feet": None,
        "analysis_scope": None,
    }


def _raise_for_arcgis_error(data: dict) -> None:
    if "error" not in data:
        return

    error_details = data["error"]

    message = error_details.get(
        "message",
        "The land-use service returned an error.",
    )

    details = error_details.get("details", [])

    if details:
        message = f"{message} {' '.join(details)}"

    raise requests.RequestException(message)


def _normalize_land_use(
    attributes: dict,
) -> tuple[int | str | None, str | None, str | None]:
    land_use_code = attributes.get("lu")

    try:
        if land_use_code is not None:
            land_use_code = int(land_use_code)
    except (TypeError, ValueError):
        pass

    description = attributes.get("DESCRIPTION")

    category = LAND_USE_CATEGORIES.get(
        land_use_code
    )

    if not category and description:
        category = description

    return land_use_code, category, description


def query_land_use(
    latitude: float,
    longitude: float,
    search_distance: int = 0,
):
    x, y = transformer_to_2230.transform(
        longitude,
        latitude,
    )

    params = {
        "where": "1=1",
        "geometry": f"{x},{y}",
        "geometryType": "esriGeometryPoint",
        "inSR": "2230",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "lu,DESCRIPTION",
        "returnGeometry": "false",
        "f": "json",
    }

    if search_distance > 0:
        params["distance"] = search_distance
        params["units"] = "esriSRUnit_Foot"

    response = requests.get(
        URL,
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    _raise_for_arcgis_error(data)

    return data.get("features", [])


def _geojson_to_2230_geometry(
    parcel_boundary: dict,
):
    """
    Convert either GeoJSON geometry or ArcGIS polygon rings to EPSG:2230.

    Housing OS parcel boundaries normally arrive as:
        {"rings": [...], "spatialReference": {...}}

    Some callers may instead provide a GeoJSON Feature or geometry.
    """
    if not isinstance(parcel_boundary, dict):
        raise ValueError(
            "The parcel boundary was not a dictionary."
        )

    boundary = parcel_boundary

    if boundary.get("type") == "Feature":
        boundary = boundary.get("geometry") or {}

    rings = boundary.get("rings")

    if rings:
        polygons = []

        for ring in rings:
            if not isinstance(ring, list) or len(ring) < 4:
                continue

            try:
                polygon = Polygon(ring)

                if not polygon.is_valid:
                    polygon = polygon.buffer(0)

                if not polygon.is_empty:
                    polygons.append(polygon)

            except (TypeError, ValueError):
                continue

        if not polygons:
            raise ValueError(
                "The ArcGIS parcel boundary did not contain usable rings."
            )

        parcel_geometry = unary_union(polygons)

    elif boundary.get("type"):
        parcel_geometry = shape(boundary)

    else:
        raise ValueError(
            "The parcel boundary did not contain ArcGIS rings or GeoJSON type information."
        )

    if parcel_geometry.is_empty:
        raise ValueError(
            "The parcel boundary was empty."
        )

    parcel_geometry_2230 = transform(
        transformer_to_2230.transform,
        parcel_geometry,
    )

    if not parcel_geometry_2230.is_valid:
        parcel_geometry_2230 = (
            parcel_geometry_2230.buffer(0)
        )

    if parcel_geometry_2230.is_empty:
        raise ValueError(
            "The parcel boundary could not be converted."
        )

    return parcel_geometry_2230


def _shapely_to_esri_polygon(
    geometry,
) -> dict:
    polygons = []

    if geometry.geom_type == "Polygon":
        polygons = [geometry]
    elif geometry.geom_type == "MultiPolygon":
        polygons = list(geometry.geoms)
    else:
        geometry = geometry.buffer(0)

        if geometry.geom_type == "Polygon":
            polygons = [geometry]
        elif geometry.geom_type == "MultiPolygon":
            polygons = list(geometry.geoms)

    rings = []

    for polygon in polygons:
        rings.append(
            [
                [float(x), float(y)]
                for x, y in polygon.exterior.coords
            ]
        )

        for interior in polygon.interiors:
            rings.append(
                [
                    [float(x), float(y)]
                    for x, y in interior.coords
                ]
            )

    return {
        "rings": rings,
        "spatialReference": {
            "wkid": 2230,
        },
    }


def _esri_geometry_to_shapely(
    geometry: dict,
):
    rings = geometry.get("rings") or []

    polygons = []

    for ring in rings:
        if len(ring) < 4:
            continue

        try:
            polygon = Polygon(ring)

            if not polygon.is_valid:
                polygon = polygon.buffer(0)

            if not polygon.is_empty:
                polygons.append(polygon)
        except (TypeError, ValueError):
            continue

    if not polygons:
        return None

    combined = unary_union(polygons)

    if not combined.is_valid:
        combined = combined.buffer(0)

    return combined


def query_land_use_for_parcel(
    parcel_boundary: dict,
) -> tuple[list[dict], object]:
    """
    Query SANDAG with the parcel bounding box, then perform the exact parcel
    intersection locally with Shapely.

    This avoids sending a very large parcel polygon to ArcGIS, which can cause
    the remote server to reset the connection.
    """
    parcel_geometry_2230 = (
        _geojson_to_2230_geometry(
            parcel_boundary
        )
    )

    min_x, min_y, max_x, max_y = (
        parcel_geometry_2230.bounds
    )

    envelope = {
        "xmin": float(min_x),
        "ymin": float(min_y),
        "xmax": float(max_x),
        "ymax": float(max_y),
        "spatialReference": {
            "wkid": 2230,
        },
    }

    all_features = []
    result_offset = 0
    page_size = 1000

    while True:
        params = {
            "where": "1=1",
            "geometry": str(envelope).replace(
                "'", '"'
            ),
            "geometryType": "esriGeometryEnvelope",
            "inSR": "2230",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "lu,DESCRIPTION",
            "returnGeometry": "true",
            "outSR": "2230",
            "resultOffset": result_offset,
            "resultRecordCount": page_size,
            "f": "json",
        }

        response = requests.get(
            URL,
            params=params,
            timeout=45,
        )

        response.raise_for_status()

        data = response.json()

        _raise_for_arcgis_error(data)

        features = data.get("features") or []

        all_features.extend(features)

        exceeded = bool(
            data.get("exceededTransferLimit")
        )

        if not exceeded or not features:
            break

        result_offset += len(features)

        if result_offset >= 10000:
            break

    return all_features, parcel_geometry_2230


def _build_point_result(
    features: list[dict],
    lookup_method: str,
    search_distance: int,
) -> dict:
    attributes = features[0].get(
        "attributes",
        {},
    )

    (
        land_use_code,
        category,
        description,
    ) = _normalize_land_use(attributes)

    return {
        "code": land_use_code,
        "category": category,
        "description": description,
        "dominant_code": land_use_code,
        "dominant_category": category,
        "dominant_description": description,
        "land_use_breakdown": [
            {
                "code": land_use_code,
                "category": category,
                "description": description,
                "parcel_percent": None,
                "estimated_acres": None,
            }
        ],
        "mixed_land_use": False,
        "parcel_overlap_percent": None,
        "status": "found",
        "source": "SANDAG Current Land Use",
        "message": None,
        "lookup_method": lookup_method,
        "search_distance_feet": search_distance,
        "analysis_scope": "address_point",
    }


def _build_parcel_result(
    features: list[dict],
    parcel_geometry_2230,
    parcel_acres: float | None,
) -> dict | None:
    parcel_area = float(
        parcel_geometry_2230.area
    )

    if parcel_area <= 0:
        return None

    grouped: dict[
        tuple[int | str | None, str | None, str | None],
        float,
    ] = {}

    for feature in features:
        feature_geometry = (
            _esri_geometry_to_shapely(
                feature.get("geometry") or {}
            )
        )

        if feature_geometry is None:
            continue

        intersection = (
            parcel_geometry_2230.intersection(
                feature_geometry
            )
        )

        if intersection.is_empty:
            continue

        overlap_area = float(intersection.area)

        if overlap_area <= 0:
            continue

        normalized = _normalize_land_use(
            feature.get("attributes") or {}
        )

        grouped[normalized] = (
            grouped.get(normalized, 0.0)
            + overlap_area
        )

    if not grouped:
        return None

    total_classified_area = sum(
        grouped.values()
    )

    breakdown = []

    for (
        code,
        category,
        description,
    ), overlap_area in grouped.items():
        parcel_percent = round(
            min(
                100.0,
                (
                    overlap_area
                    / parcel_area
                    * 100.0
                ),
            ),
            2,
        )

        if parcel_acres is not None:
            estimated_acres = round(
                parcel_acres
                * parcel_percent
                / 100.0,
                3,
            )
        else:
            estimated_acres = round(
                overlap_area / 43560.0,
                3,
            )

        breakdown.append(
            {
                "code": code,
                "category": category,
                "description": description,
                "parcel_percent": parcel_percent,
                "estimated_acres": estimated_acres,
            }
        )

    breakdown.sort(
        key=lambda item: (
            item["parcel_percent"] or 0
        ),
        reverse=True,
    )

    dominant = breakdown[0]

    # Transportation/right-of-way polygons can overlap an entire parcel in
    # SANDAG's service. Prefer a substantial non-road use as the primary use
    # while retaining every intersecting layer in the breakdown.
    non_transportation_uses = [
        item
        for item in breakdown
        if not any(
            term in str(item.get("category") or "").lower()
            for term in ("road right of way", "rail right of way")
        )
        and (item.get("parcel_percent") or 0) >= 25
    ]

    if non_transportation_uses:
        dominant = non_transportation_uses[0]

    meaningful_uses = [
        item
        for item in breakdown
        if (
            item["parcel_percent"] or 0
        ) >= 5
    ]

    parcel_overlap_percent = round(
        min(
            100.0,
            (
                total_classified_area
                / parcel_area
                * 100.0
            ),
        ),
        2,
    )

    mixed_land_use = (
        len(meaningful_uses) > 1
    )

    message = None

    if mixed_land_use:
        message = (
            "This parcel intersects multiple, potentially overlapping "
            "SANDAG current-land-use polygons. The primary fields prefer "
            "a substantial non-right-of-way use; review the "
            "land_use_breakdown for every mapped classification."
        )

    return {
        "code": dominant["code"],
        "category": dominant["category"],
        "description": dominant["description"],
        "dominant_code": dominant["code"],
        "dominant_category": dominant["category"],
        "dominant_description": dominant["description"],
        "land_use_breakdown": breakdown,
        "mixed_land_use": mixed_land_use,
        "parcel_overlap_percent": parcel_overlap_percent,
        "status": "found",
        "source": "SANDAG Current Land Use",
        "message": message,
        "lookup_method": "parcel_polygon_intersection",
        "search_distance_feet": 0,
        "analysis_scope": "parcel_wide_polygon",
    }


def get_land_use_data(
    latitude: float,
    longitude: float,
    parcel_boundary: dict | None = None,
    parcel_acres: float | None = None,
) -> dict:
    parcel_failure_message = None

    """
    Return parcel-wide current land use when a parcel boundary is available.

    The exact address point remains a fallback for records that do not have
    usable parcel geometry. This prevents a driveway, road, parking area, or
    other small point location from being reported as the use of an entire
    large or mixed-use parcel.
    """
    if parcel_boundary:
        try:
            (
                parcel_features,
                parcel_geometry_2230,
            ) = query_land_use_for_parcel(
                parcel_boundary=parcel_boundary
            )

            parcel_result = _build_parcel_result(
                features=parcel_features,
                parcel_geometry_2230=parcel_geometry_2230,
                parcel_acres=parcel_acres,
            )

            if parcel_result is not None:
                return parcel_result

        except requests.Timeout:
            parcel_failure_message = (
                "Parcel-wide land-use analysis timed out, "
                "so Housing OS used the address point instead."
            )
        except (
            requests.RequestException,
            ValueError,
            TypeError,
        ) as error:
            parcel_failure_message = (
                "Parcel-wide land-use analysis failed, "
                f"so Housing OS used the address point instead: {error}"
            )
    else:
        parcel_failure_message = None

    try:
        features = query_land_use(
            latitude=latitude,
            longitude=longitude,
        )

        lookup_method = "exact_point"
        search_distance = 0

        if not features:
            features = query_land_use(
                latitude=latitude,
                longitude=longitude,
                search_distance=100,
            )

            lookup_method = "nearby_search"
            search_distance = 100

    except requests.Timeout:
        return empty_land_use_result(
            status="timeout",
            message=(
                "The land-use server took too long "
                "to respond. Please try again."
            ),
        )

    except requests.RequestException as error:
        return empty_land_use_result(
            status="error",
            message=str(error),
        )

    except ValueError:
        return empty_land_use_result(
            status="error",
            message=(
                "The land-use server returned "
                "an invalid response."
            ),
        )

    if not features:
        return empty_land_use_result(
            status="not_found",
            message=(
                "No current land-use record was found at "
                "or within 100 feet of this location."
            ),
        )

    point_result = _build_point_result(
        features=features,
        lookup_method=lookup_method,
        search_distance=search_distance,
    )

    if parcel_failure_message:
        point_result["message"] = (
            parcel_failure_message
        )
        point_result["analysis_scope"] = (
            "address_point_fallback"
        )

    return point_result
