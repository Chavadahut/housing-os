"""
Countywide jurisdiction detection for Housing OS.

Detection order:
1. Use the parcel's latitude/longitude.
2. Verify the point is inside San Diego County.
3. Query the SANDAG/SanGIS Municipal Boundaries polygon layer.
4. If the point intersects a municipality, return that city's registry entry.
5. If the point is in San Diego County but not inside a municipal polygon,
   classify it as Unincorporated San Diego County.

This deliberately does NOT infer jurisdiction from ZIP code, mailing city,
community name, or nearest city.
"""

import time
from typing import Any

import requests

from connectors.jurisdiction_registry import (
    get_jurisdiction_config,
    match_municipal_name,
)

MUNICIPAL_BOUNDARIES_URL = (
    "https://geo.sandag.org/server/rest/services/"
    "Hosted/Municipal_Boundaries/FeatureServer/0/query"
)

COUNTY_BOUNDARY_URL = (
    "https://geo.sandag.org/server/rest/services/"
    "Hosted/San_Diego_County_Boundary/FeatureServer/0/query"
)

CONNECT_TIMEOUT_SECONDS = 3
READ_TIMEOUT_SECONDS = 8


def _request_json(
    url: str,
    params: dict[str, Any],
) -> dict:
    response = requests.get(
        url,
        params=params,
        timeout=(
            CONNECT_TIMEOUT_SECONDS,
            READ_TIMEOUT_SECONDS,
        ),
        headers={
            "User-Agent": (
                "HousingOS/0.1 "
                "san-diego-jurisdiction-screening"
            )
        },
    )

    response.raise_for_status()
    data = response.json()

    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(str(data["error"]))

    return data


def _point_query_params(
    latitude: float,
    longitude: float,
    out_fields: str,
) -> dict:
    return {
        "where": "1=1",
        "geometry": f"{longitude},{latitude}",
        "geometryType": "esriGeometryPoint",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": out_fields,
        "returnGeometry": "false",
        "resultRecordCount": 5,
        "f": "json",
    }


def _inside_san_diego_county(
    latitude: float,
    longitude: float,
) -> bool:
    data = _request_json(
        COUNTY_BOUNDARY_URL,
        _point_query_params(
            latitude=latitude,
            longitude=longitude,
            out_fields="*",
        ),
    )

    return bool(data.get("features"))


def _municipal_boundary_match(
    latitude: float,
    longitude: float,
) -> tuple[str | None, dict | None]:
    data = _request_json(
        MUNICIPAL_BOUNDARIES_URL,
        _point_query_params(
            latitude=latitude,
            longitude=longitude,
            out_fields="*",
        ),
    )

    features = data.get("features") or []

    if not features:
        return None, None

    # A normal point should intersect one municipal jurisdiction. If an
    # annexation representation produces multiple records, accept only if
    # they all normalize to the same registered city.
    matches = []

    for feature in features:
        attrs = feature.get("attributes") or {}

        candidate_values = [
            attrs.get("name"),
            attrs.get("NAME"),
            attrs.get("jurisdiction"),
            attrs.get("JURISDICTION"),
            attrs.get("city"),
            attrs.get("CITY"),
            attrs.get("MUNI_NAME"),
            attrs.get("MUN_NAME"),
            attrs.get("CITY_NAME"),
        ]

        for candidate in candidate_values:
            match = match_municipal_name(candidate)

            if match:
                matches.append(
                    (
                        str(candidate),
                        match,
                    )
                )
                break

    if not matches:
        raw_name = None

        if features:
            attrs = features[0].get("attributes") or {}
            raw_name = (
                attrs.get("name")
                or attrs.get("NAME")
                or attrs.get("jurisdiction")
                or attrs.get("JURISDICTION")
                or attrs.get("city")
                or attrs.get("CITY")
                or attrs.get("MUNI_NAME")
                or attrs.get("MUN_NAME")
                or attrs.get("CITY_NAME")
            )

        return raw_name, None

    unique_keys = {
        match["key"]
        for _, match in matches
    }

    if len(unique_keys) != 1:
        return None, None

    return matches[0]


def _unknown_result(
    message: str,
    *,
    latitude: float | None = None,
    longitude: float | None = None,
) -> dict:
    return {
        "key": "unknown",
        "name": None,
        "type": "unknown",
        "zoning_connector": None,
        "general_plan_connector": None,
        "permit_connector": None,
        "connector_status": "unknown",
        "status": "not_determined",
        "source": (
            "SANDAG/SanGIS Municipal Boundaries"
        ),
        "lookup_method": "exact_point",
        "latitude": latitude,
        "longitude": longitude,
        "message": message,
    }


def determine_jurisdiction(
    property_data: dict,
) -> dict:
    parcels = property_data.get("parcels") or []

    if not parcels:
        return _unknown_result(
            "No parcel coordinates were available for jurisdiction detection."
        )

    parcel = parcels[0]

    try:
        latitude = float(parcel["latitude"])
        longitude = float(parcel["longitude"])
    except (KeyError, TypeError, ValueError):
        return _unknown_result(
            "The parcel did not contain usable latitude/longitude coordinates."
        )

    started = time.perf_counter()

    try:
        raw_name, municipal = _municipal_boundary_match(
            latitude=latitude,
            longitude=longitude,
        )

        if municipal:
            result = {
                **municipal,
                "type": "incorporated_city",
                "status": "found",
                "source": (
                    "SANDAG/SanGIS Municipal Boundaries"
                ),
                "lookup_method": "exact_point",
                "latitude": latitude,
                "longitude": longitude,
                "raw_municipal_name": raw_name,
                "message": None,
            }

            elapsed = time.perf_counter() - started
            print(
                "[Housing OS jurisdiction] "
                f"{result['name']} {elapsed:.2f}s"
            )

            return result

        # No incorporated municipality intersected the point. Verify that
        # it is actually inside San Diego County before calling it
        # unincorporated.
        inside_county = _inside_san_diego_county(
            latitude=latitude,
            longitude=longitude,
        )

        if inside_county:
            config = get_jurisdiction_config(
                "unincorporated"
            )

            result = {
                **config,
                "type": "unincorporated_county",
                "status": "found",
                "source": (
                    "SANDAG/SanGIS Municipal Boundaries "
                    "and San Diego County Boundary"
                ),
                "lookup_method": "exact_point",
                "latitude": latitude,
                "longitude": longitude,
                "raw_municipal_name": raw_name,
                "message": None,
            }

            elapsed = time.perf_counter() - started
            print(
                "[Housing OS jurisdiction] "
                f"{result['name']} {elapsed:.2f}s"
            )

            return result

        elapsed = time.perf_counter() - started
        print(
            "[Housing OS jurisdiction] "
            f"outside county {elapsed:.2f}s"
        )

        return _unknown_result(
            "The parcel point was not identified inside San Diego County.",
            latitude=latitude,
            longitude=longitude,
        )

    except Exception as error:
        elapsed = time.perf_counter() - started

        print(
            "[Housing OS jurisdiction] "
            f"lookup failed {elapsed:.2f}s: {error}"
        )

        # Conservative fallback: preserve the old known-safe classifications
        # only when the parcel's existing metadata is explicit.
        community = str(
            parcel.get("community") or ""
        ).strip().upper()

        address = str(
            parcel.get("address") or ""
        ).upper()

        if (
            "LA MESA" in address
            or community == "LA MESA"
        ):
            config = get_jurisdiction_config("la_mesa")
        elif (
            (
                "SAN DIEGO" in address
                and "COUNTY" not in address
            )
            or community == "SAN DIEGO"
        ):
            config = get_jurisdiction_config("san_diego")
        elif community in {
            "RAMONA",
            "LAKESIDE",
            "ALPINE",
            "BONSALL",
            "BORREGO SPRINGS",
            "CAMPO",
            "DESCANSO",
            "FALLBROOK",
            "JAMUL",
            "JULIAN",
            "PINE VALLEY",
            "SPRING VALLEY",
            "VALLEY CENTER",
        }:
            config = get_jurisdiction_config("unincorporated")
        else:
            config = None

        if config:
            return {
                **config,
                "type": (
                    "unincorporated_county"
                    if config["key"] == "unincorporated"
                    else "incorporated_city"
                ),
                "status": "fallback",
                "source": "parcel metadata fallback",
                "lookup_method": "metadata_fallback",
                "latitude": latitude,
                "longitude": longitude,
                "raw_municipal_name": None,
                "message": (
                    "The authoritative municipal-boundary query failed, "
                    "so Housing OS used a conservative metadata fallback."
                ),
            }

        return _unknown_result(
            (
                "The authoritative municipal-boundary query failed and "
                "Housing OS did not have enough evidence to safely infer "
                f"the jurisdiction: {error}"
            ),
            latitude=latitude,
            longitude=longitude,
        )