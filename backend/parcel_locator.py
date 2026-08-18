import re
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from typing import Any

import requests
from shapely.geometry import Point, Polygon, MultiPolygon

from connectors.san_diego_gis import (
    ADDRESS_URL,
    PARCEL_URL,
    get_parcel_boundary,
    transformer,
)

CENSUS_GEOCODER_URL = (
    "https://geocoding.geo.census.gov/geocoder/"
    "locations/onelineaddress"
)

SANDAG_ADDRESS_POINTS_URL = (
    "https://geo.sandag.org/server/rest/services/"
    "Hosted/Address_Points/FeatureServer/0/query"
)

SANDAG_CURRENT_LAND_USE_URL = (
    "https://geo.sandag.org/server/rest/services/"
    "Hosted/Land_Use_2025/FeatureServer/0/query"
)

CONNECT_TIMEOUT_SECONDS = 3
COUNTY_ADDRESS_READ_TIMEOUT_SECONDS = 5
COUNTY_POINT_READ_TIMEOUT_SECONDS = 7
CENSUS_READ_TIMEOUT_SECONDS = 6

SUFFIX_ALIASES = {
    "STREET": "ST", "ST": "ST",
    "ROAD": "RD", "RD": "RD",
    "AVENUE": "AVE", "AVE": "AVE",
    "DRIVE": "DR", "DR": "DR",
    "LANE": "LN", "LN": "LN",
    "COURT": "CT", "CT": "CT",
    "BOULEVARD": "BLVD", "BLVD": "BLVD",
    "HIGHWAY": "HWY", "HWY": "HWY",
    "PLACE": "PL", "PL": "PL",
    "TERRACE": "TER", "TER": "TER",
    "CIRCLE": "CIR", "CIR": "CIR",
    "PARKWAY": "PKWY", "PKWY": "PKWY",
    "TRAIL": "TRL", "TRL": "TRL",
    "WAY": "WAY",
}


def _timed_message(label: str, started: float) -> None:
    elapsed = time.perf_counter() - started
    print(f"[Housing OS locator] {label:<34} {elapsed:.2f}s")


def _normalize(value: str | None) -> str:
    if not value:
        return ""

    value = re.sub(
        r"[^A-Z0-9]+",
        " ",
        str(value).upper().strip(),
    )

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def _escape_sql_text(value: str) -> str:
    return str(value).replace("'", "''")


def _parse_address(address: str) -> dict | None:
    if not address:
        return None

    street_part = address.split(",", 1)[0].strip()
    match = re.match(
        r"^\s*(\d+)\s+(.+?)\s*$",
        street_part,
    )

    if not match:
        return None

    number = match.group(1)
    remainder = re.sub(
        r"\s+",
        " ",
        match.group(2).strip(),
    )

    parts = remainder.split()

    if not parts:
        return None

    final_token = parts[-1].upper().rstrip(".")
    suffix = ""

    if final_token in SUFFIX_ALIASES:
        suffix = SUFFIX_ALIASES[final_token]
        street_parts = parts[:-1]
    else:
        street_parts = parts

    if not street_parts:
        return None

    direction = ""
    if street_parts and street_parts[0].upper().rstrip(".") in {
        "N", "S", "E", "W", "NE", "NW", "SE", "SW",
    }:
        direction = street_parts.pop(0).upper().rstrip(".")

    if not street_parts:
        return None

    return {
        "number": number,
        "street": " ".join(street_parts).upper(),
        "suffix": suffix,
        "direction": direction,
    }


def _request_json(
    url: str,
    params: dict[str, Any],
    label: str,
    read_timeout: int,
) -> dict:
    started = time.perf_counter()

    try:
        response = requests.get(
            url,
            params=params,
            timeout=(
                CONNECT_TIMEOUT_SECONDS,
                read_timeout,
            ),
            headers={
                "User-Agent": (
                    "HousingOS/0.1 "
                    "parcel-feasibility-research"
                )
            },
        )

        response.raise_for_status()
        data = response.json()

        if isinstance(data, dict) and data.get("error"):
            raise RuntimeError(str(data["error"]))

        return data

    finally:
        _timed_message(label, started)


def _request_address_features(
    where_clause: str,
    label: str,
) -> list[dict]:
    data = _request_json(
        ADDRESS_URL,
        params={
            "where": where_clause,
            "outFields": "*",
            "returnGeometry": "true",
            "f": "json",
        },
        label=label,
        read_timeout=(
            COUNTY_ADDRESS_READ_TIMEOUT_SECONDS
        ),
    )

    return data.get("features") or []


def _feature_to_parcel(
    feature: dict,
) -> dict | None:
    attrs = feature.get("attributes") or {}
    geometry = feature.get("geometry")

    if not geometry:
        return None

    try:
        x = float(geometry["x"])
        y = float(geometry["y"])
        # Address Points may honor outSR=2230 or occasionally return WGS84
        # coordinates directly. Detect the latter instead of projecting it a
        # second time and discarding an otherwise exact official match.
        if -180 <= x <= 180 and -90 <= y <= 90:
            longitude, latitude = x, y
        else:
            longitude, latitude = transformer.transform(x, y)
    except (KeyError, TypeError, ValueError):
        return None

    apn = attrs.get("APN")

    if apn is None:
        return None

    digits = "".join(
        character
        for character in str(apn)
        if character.isdigit()
    )

    if len(digits) != 10:
        return None

    address_number = attrs.get("ADDRNMBR")

    try:
        if address_number is not None:
            address_number = int(address_number)
    except (TypeError, ValueError):
        pass

    parcel_address = " ".join(
        str(value)
        for value in (
            address_number,
            attrs.get("ADDRNAME"),
            attrs.get("ADDRSFX"),
        )
        if value not in (None, "")
    )

    return {
        "apn": digits,
        "address": parcel_address,
        "zip": attrs.get("ADDRZIP"),
        "community": attrs.get("COMMUNITY"),
        "latitude": latitude,
        "longitude": longitude,
    }


def _attach_boundary(parcel: dict) -> dict:
    if parcel.get("_parcel_boundary"):
        return parcel

    started = time.perf_counter()

    parcel["_parcel_boundary"] = get_parcel_boundary(
        apn=parcel.get("apn")
    )

    _timed_message(
        "County APN boundary",
        started,
    )

    return parcel


def _county_exact_lookup(
    address: str,
) -> dict | None:
    parsed = _parse_address(address)

    if parsed is None:
        return None

    street_name = _escape_sql_text(parsed["street"])
    street_suffix = _escape_sql_text(
        parsed.get("suffix", "")
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
        features = _request_address_features(
            exact_where,
            "County ADDRAPN exact",
        )
    except Exception as error:
        print(
            "[Housing OS locator] County exact lookup failed: "
            f"{error}"
        )
        return None

    for feature in features:
        parcel = _feature_to_parcel(feature)

        if parcel and _parcel_matches_requested_zip(parcel, address):
            return parcel

    return None


def _county_number_fallback(
    address: str,
) -> dict | None:
    parsed = _parse_address(address)

    if parsed is None:
        return None

    number_where = (
        f"ADDRNMBR = {parsed['number']}"
    )

    try:
        candidates = _request_address_features(
            number_where,
            "County ADDRAPN number fallback",
        )
    except Exception as error:
        print(
            "[Housing OS locator] County number lookup failed: "
            f"{error}"
        )
        return None

    target_street = _normalize(parsed["street"])
    target_suffix = _normalize(
        parsed.get("suffix", "")
    )

    target_full = _normalize(
        " ".join(
            value
            for value in (
                target_street,
                target_suffix,
            )
            if value
        )
    )

    for feature in candidates:
        attrs = feature.get("attributes") or {}

        candidate_name = _normalize(
            attrs.get("ADDRNAME")
        )

        candidate_suffix = _normalize(
            attrs.get("ADDRSFX")
        )

        if (
            target_suffix
            and candidate_suffix
            and candidate_suffix != target_suffix
        ):
            continue

        candidate_full = _normalize(
            " ".join(
                value
                for value in (
                    candidate_name,
                    candidate_suffix,
                )
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
            parcel = _feature_to_parcel(feature)

            if parcel and _parcel_matches_requested_zip(parcel, address):
                return parcel

    return None


def _geocode_with_census(
    address: str,
) -> dict | None:
    try:
        data = _request_json(
            CENSUS_GEOCODER_URL,
            params={
                "address": address,
                "benchmark": "Public_AR_Current",
                "format": "json",
            },
            label="Census geocoder",
            read_timeout=(
                CENSUS_READ_TIMEOUT_SECONDS
            ),
        )
    except Exception as error:
        print(
            "[Housing OS locator] Census geocoder failed: "
            f"{error}"
        )
        return None

    matches = (
        (
            data.get("result")
            or {}
        ).get("addressMatches")
        or []
    )

    if not matches:
        return None

    best = matches[0]
    coordinates = best.get("coordinates") or {}

    try:
        longitude = float(coordinates["x"])
        latitude = float(coordinates["y"])
    except (KeyError, TypeError, ValueError):
        return None

    return {
        "latitude": latitude,
        "longitude": longitude,
        "matched_address": best.get(
            "matchedAddress"
        ),
    }


def _find_exact_parcel_at_point(
    latitude: float,
    longitude: float,
) -> str | None:
    try:
        data = _request_json(
            PARCEL_URL,
            params={
                "where": "1=1",
                "geometry": (
                    f"{longitude},{latitude}"
                ),
                "geometryType": (
                    "esriGeometryPoint"
                ),
                "inSR": 4326,
                "spatialRel": (
                    "esriSpatialRelIntersects"
                ),
                "outFields": "APN",
                "returnGeometry": "false",
                "resultRecordCount": 2,
                "f": "json",
            },
            label=(
                "County exact point-to-parcel"
            ),
            read_timeout=(
                COUNTY_POINT_READ_TIMEOUT_SECONDS
            ),
        )
    except Exception as error:
        print(
            "[Housing OS locator] Exact point lookup failed: "
            f"{error}"
        )
        return None

    features = data.get("features") or []

    # Safety rule: exact point must identify exactly one parcel.
    if len(features) != 1:
        if len(features) > 1:
            print(
                "[Housing OS locator] Exact point returned "
                "multiple parcels; refusing to guess."
            )
        return None

    attrs = features[0].get("attributes") or {}
    apn = attrs.get("APN")

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


def _county_result(
    address: str,
    parcel: dict,
    method: str,
) -> dict:
    parcel = _attach_boundary(parcel)

    return {
        "address": address,
        "parcel_count": 1,
        "parcels": [parcel],
        "source": "San Diego GIS",
        "status": "found",
        "message": None,
        "lookup_method": method,
    }


def _fallback_result(
    address: str,
    geocoded: dict,
    apn: str,
) -> dict:
    parcel = {
        "apn": apn,
        "address": (
            geocoded.get("matched_address")
            or address
        ),
        "zip": None,
        "community": None,
        "latitude": geocoded["latitude"],
        "longitude": geocoded["longitude"],
    }

    parcel = _attach_boundary(parcel)

    return {
        "address": address,
        "parcel_count": 1,
        "parcels": [parcel],
        "source": (
            "U.S. Census Geocoder + "
            "County of San Diego Assessor Parcels"
        ),
        "status": "found",
        "message": (
            "Housing OS geocoded the address and confirmed "
            "the exact County parcel polygon containing that "
            "point."
        ),
        "lookup_method": (
            "geocode_then_exact_parcel_intersection"
        ),
    }



def _feature_to_sandag_parcel(
    feature: dict,
) -> dict | None:
    attrs = feature.get("attributes") or {}
    geometry = feature.get("geometry") or {}

    apn = attrs.get("apn") or attrs.get("APN")

    if not apn:
        return None

    digits = "".join(
        character
        for character in str(apn)
        if character.isdigit()
    )

    if len(digits) != 10:
        return None

    try:
        longitude, latitude = transformer.transform(
            geometry["x"],
            geometry["y"],
        )
    except (KeyError, TypeError, ValueError):
        return None

    number = attrs.get("addrnmbr") or attrs.get("ADDRNMBR")
    prefix = attrs.get("addrpdir") or attrs.get("ADDRPDIR") or ""
    street = attrs.get("addrname") or attrs.get("ADDRNAME") or ""
    suffix = attrs.get("addrsfx") or attrs.get("ADDRSFX") or ""
    postfix = attrs.get("addrpostd") or attrs.get("ADDRPOSTD") or ""
    unit = attrs.get("addrunit") or attrs.get("ADDRUNIT") or ""

    parcel_address = " ".join(
        str(value).strip()
        for value in (
            number,
            prefix,
            street,
            suffix,
            postfix,
        )
        if value not in (None, "")
    )

    if unit:
        parcel_address = f"{parcel_address} Unit {unit}".strip()

    return {
        "apn": digits,
        "address": parcel_address,
        "zip": attrs.get("addrzip") or attrs.get("ADDRZIP"),
        "community": attrs.get("community") or attrs.get("COMMUNITY"),
        "address_jurisdiction_code": (
            attrs.get("addrjur") or attrs.get("ADDRJUR")
        ),
        "address_source": attrs.get("asource") or attrs.get("ASOURCE"),
        "placement_location": (
            attrs.get("placement_location")
            or attrs.get("PLACEMENT_LOCATION")
        ),
        "latitude": latitude,
        "longitude": longitude,
    }


def _extract_zip(address: str) -> str | None:
    matches = re.findall(
        r"\b(\d{5})(?:-\d{4})?\b",
        str(address or ""),
    )
    # A five-digit house number can look like a ZIP. Postal ZIPs appear at
    # the end of a conventional address, so use the final five-digit token.
    return matches[-1] if matches else None


def _parcel_matches_requested_zip(parcel: dict, address: str) -> bool:
    """Reject a same-number/same-street parcel in a different ZIP."""
    requested_zip = _extract_zip(address)
    parcel_zip = _normalize(parcel.get("zip"))
    return not requested_zip or not parcel_zip or parcel_zip == requested_zip


def _sandag_address_lookup(
    address: str,
) -> list[dict]:
    """
    Official countywide textual address lookup.

    Queries progressively from narrow to broad, then verifies house number
    and normalized street in Python. Handles suffix stored separately or as
    part of addrname.
    """
    parsed = _parse_address(address)

    if parsed is None:
        return []

    target_zip = _extract_zip(address)

    where_clauses = []

    if target_zip:
        where_clauses.append(
            (
                f"addrnmbr = {parsed['number']} "
                f"AND addrzip = '{_escape_sql_text(target_zip)}'"
            )
        )

    # Ask the service for the exact official street name before broader
    # number-only strategies. This is both faster and more reliable for
    # suffixless streets such as VISTA PANORAMA.
    where_clauses.insert(
        0,
        (
            f"addrnmbr = {parsed['number']} AND "
            f"addrname = '{_escape_sql_text(parsed['street'])}'"
            + (f" AND addrzip = '{_escape_sql_text(target_zip)}'" if target_zip else "")
        ),
    )

    where_clauses.append(
        f"addrnmbr = {parsed['number']}"
    )

    all_features = []
    seen = set()

    for index, where_clause in enumerate(where_clauses, start=1):
        try:
            data = _request_json(
                SANDAG_ADDRESS_POINTS_URL,
                params={
                    "where": where_clause,
                    "outFields": "*",
                    "returnGeometry": "true",
                    "outSR": 2230,
                    "resultRecordCount": 2000,
                    "f": "json",
                },
                label=f"SanGIS exact strategy {index}",
                read_timeout=10,
            )
        except Exception as error:
            print(
                "[Housing OS locator] SanGIS exact strategy "
                f"{index} failed: {error}"
            )
            continue

        features = data.get("features") or []

        print(
            "[Housing OS locator] SanGIS exact strategy "
            f"{index} returned {len(features)} raw point(s)."
        )

        for feature in features:
            attrs = feature.get("attributes") or {}
            oid = (
                attrs.get("objectid")
                or attrs.get("OBJECTID")
                or repr(feature)
            )

            if oid in seen:
                continue

            seen.add(oid)
            all_features.append(feature)

        parcels = _features_to_unique_parcels(
            features=all_features,
            parsed=parsed,
            target_zip=target_zip,
        )

        if parcels:
            print(
                "[Housing OS locator] SanGIS exact address verified "
                f"{len(parcels)} unique APN(s)."
            )
            return parcels

    print(
        "[Housing OS locator] SanGIS exact address verification found 0 APNs."
    )
    return []


def _sandag_exact_official_lookup(address: str) -> list[dict]:
    """Resolve an exact SanGIS address without invoking geocoder fallbacks."""
    parsed = _parse_address(address)
    if not parsed:
        return []
    target_zip = _extract_zip(address)
    where = (
        f"addrnmbr = {parsed['number']} AND "
        f"addrname = '{_escape_sql_text(parsed['street'])}'"
    )
    if target_zip:
        where += f" AND addrzip = '{_escape_sql_text(target_zip)}'"
    try:
        data = _request_json(
            SANDAG_ADDRESS_POINTS_URL,
            params={"where": where, "outFields": "*", "returnGeometry": "true", "outSR": 2230, "f": "json"},
            label="SanGIS narrow exact address",
            read_timeout=12,
        )
    except Exception as error:
        print(f"[Housing OS locator] Narrow exact address failed: {error}")
        return []
    return _features_to_unique_parcels(data.get("features") or [], parsed, target_zip)


def _street_variants(
    parsed: dict,
) -> set[str]:
    """
    Handle both common SanGIS storage patterns:
      addrname='LA MESA', addrsfx='BLVD'
      addrname='LA MESA BLVD', addrsfx=null
    """
    street = _normalize(parsed.get("street"))
    suffix = _normalize(parsed.get("suffix"))

    variants = {street}

    if suffix:
        variants.add(
            _normalize(f"{street} {suffix}")
        )

    return {
        value
        for value in variants
        if value
    }


def _official_address_feature_matches(
    feature: dict,
    parsed: dict,
    target_zip: str | None = None,
) -> bool:
    attrs = feature.get("attributes") or {}

    candidate_number = attrs.get("addrnmbr") or attrs.get("ADDRNMBR")

    try:
        candidate_number = str(int(float(candidate_number)))
    except (TypeError, ValueError):
        candidate_number = _normalize(candidate_number)

    if candidate_number != str(parsed.get("number")):
        return False

    candidate_name = _normalize(
        attrs.get("addrname") or attrs.get("ADDRNAME")
    )
    candidate_suffix = _normalize(
        attrs.get("addrsfx") or attrs.get("ADDRSFX")
    )

    target_direction = _normalize(parsed.get("direction"))
    candidate_direction = _normalize(
        attrs.get("addrpredir")
        or attrs.get("ADDRPREDIR")
        or attrs.get("prefix")
        or attrs.get("PREFIX")
        or attrs.get("streetdir")
        or attrs.get("STREETDIR")
    )

    if target_direction and candidate_direction and candidate_direction != target_direction:
        return False

    target_suffix = _normalize(
        parsed.get("suffix")
    )

    # A supplied street type is meaningful identity evidence. Do not treat
    # "MAIN ST" as an exact match for an official "MAIN AVE" point merely
    # because both records store MAIN in the street-name field.
    if (
        target_suffix
        and candidate_suffix
        and candidate_suffix != target_suffix
    ):
        return False

    candidate_full = _normalize(
        " ".join(
            value
            for value in (
                candidate_name,
                candidate_suffix,
            )
            if value
        )
    )

    variants = _street_variants(parsed)

    if (
        candidate_name not in variants
        and candidate_full not in variants
    ):
        return False

    if target_zip:
        candidate_zip = _normalize(
            attrs.get("addrzip") or attrs.get("ADDRZIP")
        )

        # ZIP mismatch is only disqualifying if the candidate actually
        # carries a ZIP. Some official records leave it blank.
        if candidate_zip and candidate_zip != _normalize(target_zip):
            return False

    return True


def _features_to_unique_parcels(
    features: list[dict],
    parsed: dict,
    target_zip: str | None = None,
) -> list[dict]:
    best_by_apn = {}

    for feature in features:
        if not _official_address_feature_matches(
            feature,
            parsed,
            target_zip,
        ):
            continue

        parcel = _feature_to_sandag_parcel(feature)

        if not parcel:
            continue

        apn = parcel["apn"]

        score = 100

        if target_zip and _normalize(parcel.get("zip")) == _normalize(target_zip):
            score += 20

        if str(parcel.get("address_source") or "").upper() == "S":
            score += 5

        if str(parcel.get("placement_location") or "").upper() in {"S", "E"}:
            score += 3

        current = best_by_apn.get(apn)

        if current is None or score > current[0]:
            best_by_apn[apn] = (
                score,
                parcel,
            )

    rows = list(best_by_apn.values())
    rows.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    return [
        parcel
        for _, parcel in rows
    ]


def _sandag_nearby_verified_address_lookup(
    address: str,
    geocoded: dict,
    distance_feet: int = 500,
) -> list[dict]:
    """
    Spatial fallback using the official SanGIS address layer.

    This does NOT select the nearest parcel. It retrieves nearby official
    address points and accepts only records whose house number + street
    match the requested address.
    """
    parsed = _parse_address(address)

    if parsed is None:
        return []

    target_zip = _extract_zip(address)

    longitude = geocoded.get("longitude")
    latitude = geocoded.get("latitude")

    if longitude is None or latitude is None:
        return []

    try:
        x, y = transformer.transform(
            float(longitude),
            float(latitude),
            direction="INVERSE",
        )
    except Exception:
        # transformer in the existing connector is normally State Plane -> WGS84.
        # pyproj inverse direction may not be available depending on version.
        # ArcGIS can accept WGS84 point directly, so use that instead.
        x = float(longitude)
        y = float(latitude)
        in_sr = 4326
        distance = 0.002
        units = "esriSRUnit_Degree"
    else:
        in_sr = 2230
        distance = distance_feet
        units = "esriSRUnit_Foot"

    try:
        data = _request_json(
            SANDAG_ADDRESS_POINTS_URL,
            params={
                "where": "1=1",
                "geometry": f"{x},{y}",
                "geometryType": "esriGeometryPoint",
                "inSR": in_sr,
                "spatialRel": "esriSpatialRelIntersects",
                "distance": distance,
                "units": units,
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": 2230,
                "resultRecordCount": 2000,
                "f": "json",
            },
            label="SanGIS nearby verified address",
            read_timeout=10,
        )
    except Exception as error:
        print(
            "[Housing OS locator] Nearby SanGIS address lookup failed: "
            f"{error}"
        )
        return []

    features = data.get("features") or []

    print(
        "[Housing OS locator] Nearby SanGIS query returned "
        f"{len(features)} address point(s) before address verification."
    )

    parcels = _features_to_unique_parcels(
        features=features,
        parsed=parsed,
        target_zip=target_zip,
    )

    print(
        "[Housing OS locator] Nearby SanGIS verified "
        f"{len(parcels)} matching APN(s)."
    )

    return parcels



def _sandag_nearby_same_street_parcel_lookup(
    address: str,
    geocoded: dict,
    distance_feet: int = 700,
) -> dict | None:
    """
    Resolve tenant/business addresses that do not exist as exact SITUS points.

    Uses nearby OFFICIAL SanGIS addresses on the same street and groups them
    by APN. A parcel can be selected when the official address pattern strongly
    indicates that the requested missing number belongs to the same tax parcel,
    such as a shopping center, office complex, apartment campus, or similar
    multi-address property.
    """
    parsed = _parse_address(address)

    if parsed is None:
        return None

    target_zip = _extract_zip(address)
    target_number = int(parsed["number"])
    street_variants = _street_variants(parsed)

    longitude = geocoded.get("longitude")
    latitude = geocoded.get("latitude")

    if longitude is None or latitude is None:
        return None

    try:
        x, y = transformer.transform(
            float(longitude),
            float(latitude),
            direction="INVERSE",
        )
        in_sr = 2230
        distance = distance_feet
        units = "esriSRUnit_Foot"
    except Exception:
        x = float(longitude)
        y = float(latitude)
        in_sr = 4326
        distance = 0.003
        units = "esriSRUnit_Degree"

    try:
        data = _request_json(
            SANDAG_ADDRESS_POINTS_URL,
            params={
                "where": "1=1",
                "geometry": f"{x},{y}",
                "geometryType": "esriGeometryPoint",
                "inSR": in_sr,
                "spatialRel": "esriSpatialRelIntersects",
                "distance": distance,
                "units": units,
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": 2230,
                "resultRecordCount": 2000,
                "f": "json",
            },
            label="SanGIS nearby same-street parcel",
            read_timeout=10,
        )
    except Exception as error:
        print(
            "[Housing OS locator] Same-street parcel inference failed: "
            f"{error}"
        )
        return None

    features = data.get("features") or []
    grouped: dict[str, dict] = {}

    for feature in features:
        attrs = feature.get("attributes") or {}

        candidate_name = _normalize(
            attrs.get("addrname") or attrs.get("ADDRNAME")
        )
        candidate_suffix = _normalize(
            attrs.get("addrsfx") or attrs.get("ADDRSFX")
        )
        candidate_full = _normalize(
            " ".join(
                value
                for value in (candidate_name, candidate_suffix)
                if value
            )
        )

        if (
            candidate_name not in street_variants
            and candidate_full not in street_variants
        ):
            continue

        candidate_zip = _normalize(
            attrs.get("addrzip") or attrs.get("ADDRZIP")
        )

        if (
            target_zip
            and candidate_zip
            and candidate_zip != _normalize(target_zip)
        ):
            continue

        raw_number = attrs.get("addrnmbr") or attrs.get("ADDRNMBR")

        try:
            candidate_number = int(float(raw_number))
        except (TypeError, ValueError):
            continue

        parcel = _feature_to_sandag_parcel(feature)

        if not parcel:
            continue

        apn = parcel["apn"]
        row = grouped.setdefault(
            apn,
            {
                "apn": apn,
                "numbers": set(),
                "best_parcel": parcel,
            },
        )
        row["numbers"].add(candidate_number)

    if not grouped:
        print(
            "[Housing OS locator] Same-street inference found no "
            "official nearby street-address candidates."
        )
        return None

    ranked = []

    for apn, row in grouped.items():
        numbers = sorted(row["numbers"])
        nearest_gap = min(
            abs(number - target_number)
            for number in numbers
        )

        lower = [
            number
            for number in numbers
            if number < target_number
        ]
        upper = [
            number
            for number in numbers
            if number > target_number
        ]

        score = 0
        reasons = []

        if target_number in numbers:
            score += 120
            reasons.append("exact house number")

        target_parity = target_number % 2
        same_parity_numbers = [
            number
            for number in numbers
            if number % 2 == target_parity
        ]
        opposite_parity_numbers = [
            number
            for number in numbers
            if number % 2 != target_parity
        ]

        if same_parity_numbers:
            score += 20
            reasons.append("same-side address parity present")
        elif opposite_parity_numbers:
            score -= 80
            reasons.append("only opposite-side address parity present")

        distinct_count = len(numbers)

        if distinct_count >= 4:
            score += 45
            reasons.append("4+ same-street addresses on one APN")
        elif distinct_count >= 2:
            score += 25
            reasons.append("multiple same-street addresses on one APN")

        same_parity_lower = [
            number
            for number in same_parity_numbers
            if number < target_number
        ]
        same_parity_upper = [
            number
            for number in same_parity_numbers
            if number > target_number
        ]

        if same_parity_lower and same_parity_upper:
            low = max(same_parity_lower)
            high = min(same_parity_upper)
            span = high - low

            if span <= 20:
                score += 70
                reasons.append(
                    f"same-side official addresses bracket target ({low}-{high})"
                )
            elif span <= 60:
                score += 40
                reasons.append(
                    f"same-side nearby addresses bracket target ({low}-{high})"
                )

        if same_parity_numbers:
            same_parity_gap = min(
                abs(number - target_number)
                for number in same_parity_numbers
            )

            if same_parity_gap <= 2:
                score += 45
                reasons.append(
                    "same-side official address within 2 house numbers"
                )
            elif same_parity_gap <= 6:
                score += 30
                reasons.append(
                    "same-side official address within 6 house numbers"
                )
            elif same_parity_gap <= 20:
                score += 15
                reasons.append(
                    "same-side official address within 20 house numbers"
                )

        ranked.append(
            {
                "apn": apn,
                "score": score,
                "nearest_gap": nearest_gap,
                "numbers": numbers,
                "parcel": row["best_parcel"],
                "reasons": reasons,
            }
        )

    ranked.sort(
        key=lambda item: (
            item["score"],
            -item["nearest_gap"],
        ),
        reverse=True,
    )

    print(
        "[Housing OS locator] Same-street parcel candidates: "
        + "; ".join(
            (
                f"{item['apn']} score={item['score']} "
                f"numbers={item['numbers'][:8]} "
                f"target_parity={'even' if target_number % 2 == 0 else 'odd'}"
            )
            for item in ranked[:5]
        )
    )

    best = ranked[0]
    second_score = (
        ranked[1]["score"]
        if len(ranked) > 1
        else -1
    )

    if best["score"] < 60:
        print(
            "[Housing OS locator] Same-street evidence was too weak "
            "to select a parcel."
        )
        return None

    if (
        len(ranked) > 1
        and best["score"] - second_score < 20
    ):
        print(
            "[Housing OS locator] Same-street parcel candidates were "
            "too close to choose safely."
        )
        return None

    parcel = dict(best["parcel"])

    if _candidate_parcel_is_obvious_transportation(parcel):
        print(
            "[Housing OS locator] Same-street candidate "
            f"{best['apn']} was rejected because it appears to be "
            "a transportation/right-of-way parcel."
        )
        return None
    parcel["address"] = (
        geocoded.get("matched_address")
        or address
    )
    parcel["latitude"] = geocoded["latitude"]
    parcel["longitude"] = geocoded["longitude"]
    parcel["address_match_confidence"] = "high"
    parcel["address_match_method"] = (
        "nearby_official_same_street_addresses"
    )

    print(
        "[Housing OS locator] Same-street inference accepted APN "
        f"{best['apn']} (score={best['score']}; "
        f"{', '.join(best['reasons'])})."
    )

    return parcel



def _candidate_parcel_is_obvious_transportation(
    parcel: dict,
) -> bool:
    """
    Reject a parcel candidate that is very likely a roadway / transportation
    parcel when resolving a normal numbered street address.

    This is a conservative secondary safeguard for inferred tenant/business
    addresses. It does not replace zoning analysis and only screens obvious
    transportation/right-of-way labels when those labels are already present
    on the candidate payload.
    """
    values = []

    for key in (
        "land_use",
        "land_use_category",
        "land_use_description",
        "zoning",
        "zoning_code",
        "general_plan",
        "general_plan_code",
        "description",
        "category",
    ):
        value = parcel.get(key)

        if value is not None:
            values.append(str(value).upper())

    combined = " | ".join(values)

    blocked_terms = (
        "ROAD RIGHT OF WAY",
        "RIGHT OF WAY",
        "ROADWAY",
        "ROADWAYS",
        "TRANSPORTATION",
        "TRANS",
    )

    return any(term in combined for term in blocked_terms)



def _same_street_parcel_result(
    address: str,
    parcel: dict,
) -> dict:
    parcel = _attach_boundary(parcel)

    return {
        "address": address,
        "parcel_count": 1,
        "parcels": [parcel],
        "source": (
            "SanGIS Address Points + U.S. Census Geocoder + "
            "County of San Diego Assessor Parcels"
        ),
        "status": "found",
        "message": (
            "The requested tenant/business address was not present as an "
            "exact official SITUS point. Housing OS identified the shared "
            "tax parcel using nearby official addresses on the same street."
        ),
        "lookup_method": (
            "geocode_then_same_street_official_parcel_inference"
        ),
    }


def _attach_boundaries(
    parcels: list[dict],
) -> list[dict]:
    resolved = []

    for parcel in parcels:
        try:
            resolved.append(
                _attach_boundary(dict(parcel))
            )
        except Exception as error:
            print(
                "[Housing OS locator] Boundary lookup failed for APN "
                f"{parcel.get('apn')}: {error}"
            )

            fallback = dict(parcel)
            fallback["_parcel_boundary"] = None
            resolved.append(fallback)

    return resolved


def _sandag_result(
    address: str,
    parcels: list[dict],
) -> dict:
    parcels = _attach_boundaries(parcels)

    return {
        "address": address,
        "parcel_count": len(parcels),
        "parcels": parcels,
        "source": (
            "SanGIS Address Points + "
            "County of San Diego Assessor Parcels"
        ),
        "status": "found",
        "message": (
            None
            if len(parcels) == 1
            else (
                f"The official address matched {len(parcels)} tax parcels. "
                "Housing OS returned all exact APN matches."
            )
        ),
        "lookup_method": "sangis_countywide_address_points",
    }



def _arcgis_geometry_to_shape(
    geometry: dict,
):
    rings = geometry.get("rings") or []

    if not rings:
        return None

    polygons = []

    for ring in rings:
        try:
            polygon = Polygon(ring)

            if not polygon.is_valid:
                polygon = polygon.buffer(0)

            if not polygon.is_empty:
                polygons.append(polygon)
        except Exception:
            continue

    if not polygons:
        return None

    if len(polygons) == 1:
        return polygons[0]

    return MultiPolygon(polygons)



def _candidate_shape_point(shape):
    """
    Return a point guaranteed to be on/in the candidate parcel geometry.
    representative_point() is safer than centroid for concave parcels.
    """
    try:
        return shape.representative_point()
    except Exception:
        return None


def _query_current_land_use_for_shape(
    shape,
) -> dict:
    """
    Query SANDAG's countywide 2025 existing-land-use layer at a representative
    point inside the candidate parcel.

    This is used only as a resolver sanity check. It does not replace the
    normal Housing OS land-use analysis performed after the parcel is selected.
    """
    point = _candidate_shape_point(shape)

    if point is None:
        return {
            "description": None,
            "code": None,
        }

    try:
        data = _request_json(
            SANDAG_CURRENT_LAND_USE_URL,
            params={
                "where": "1=1",
                "geometry": f"{point.x},{point.y}",
                "geometryType": "esriGeometryPoint",
                "inSR": 2230,
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": "lu,description",
                "returnGeometry": "false",
                "resultRecordCount": 5,
                "f": "json",
            },
            label="Candidate land-use validation",
            read_timeout=8,
        )
    except Exception as error:
        print(
            "[Housing OS locator] SANDAG candidate land-use request failed: "
            f"{type(error).__name__}: {error}"
        )
        return {
            "description": None,
            "code": None,
        }

    features = data.get("features") or []

    if not features:
        return {
            "description": None,
            "code": None,
        }

    attributes = features[0].get("attributes") or {}

    return {
        "description": (
            attributes.get("description")
            or attributes.get("DESCRIPTION")
        ),
        "code": (
            attributes.get("lu")
            or attributes.get("LU")
        ),
    }


def _transportation_land_use_penalty(
    description: str | None,
) -> tuple[int, str | None]:
    """
    Return a large negative score for obvious road/transportation parcels.

    These are almost never the correct tax parcel for a normal numbered
    residential/business address when the match is inferred rather than exact.
    """
    normalized = _normalize(description)

    if not normalized:
        return 0, None

    blocked_phrases = (
        "ROAD RIGHT OF WAY",
        "RIGHT OF WAY",
        "ROADWAY",
        "ROADWAYS",
        "FREEWAY",
        "TRANSPORTATION",
        "RAIL RIGHT OF WAY",
        "TROLLEY RIGHT OF WAY",
    )

    if any(phrase in normalized for phrase in blocked_phrases):
        return -250, f"transportation land use: {description}"

    return 0, None


def _positive_land_use_score(
    description: str | None,
) -> tuple[int, str | None]:
    """
    Give a modest positive score to ordinary developable land uses.
    The score is intentionally much smaller than authoritative address evidence.
    """
    normalized = _normalize(description)

    if not normalized:
        return 0, None

    positive_terms = (
        "RESIDENTIAL",
        "COMMERCIAL",
        "SHOPPING",
        "OFFICE",
        "INDUSTRIAL",
        "MIXED USE",
        "INSTITUTIONAL",
        "SCHOOL",
        "HOTEL",
        "MOTEL",
        "VACANT",
    )

    if any(term in normalized for term in positive_terms):
        return 35, f"plausible property land use: {description}"

    return 5, f"non-transportation land use: {description}"



def _extract_sandag_apn(
    attributes: dict,
) -> str | None:
    raw_apn = (
        attributes.get("apn")
        or attributes.get("APN")
    )

    if raw_apn is None:
        return None

    digits = "".join(
        character
        for character in str(raw_apn)
        if character.isdigit()
    )

    if len(digits) != 10:
        return None

    return digits


def _collect_nearby_official_address_evidence(
    address: str,
    geocoded: dict,
    distance_feet: int = 1200,
) -> dict[str, dict]:
    """
    Build APN-level address evidence from official SanGIS address points.

    Evidence is never treated as independently authoritative unless an exact
    address match has already been found by the earlier resolver path.
    Here it only contributes to candidate ranking.
    """
    parsed = _parse_address(address)

    if parsed is None:
        return {}

    target_zip = _extract_zip(address)
    street_variants = _street_variants(parsed)

    try:
        x, y = transformer.transform(
            float(geocoded["longitude"]),
            float(geocoded["latitude"]),
            direction="INVERSE",
        )
    except Exception:
        return {}

    try:
        data = _request_json(
            SANDAG_ADDRESS_POINTS_URL,
            params={
                "where": "1=1",
                "geometry": f"{x},{y}",
                "geometryType": "esriGeometryPoint",
                "inSR": 2230,
                "spatialRel": "esriSpatialRelIntersects",
                "distance": distance_feet,
                "units": "esriSRUnit_Foot",
                "outFields": "*",
                "returnGeometry": "false",
                "resultRecordCount": 2000,
                "f": "json",
            },
            label="Candidate address evidence",
            read_timeout=10,
        )
    except Exception:
        return {}

    evidence: dict[str, dict] = {}

    for feature in data.get("features") or []:
        attrs = feature.get("attributes") or {}

        apn = _extract_sandag_apn(attrs)

        if not apn:
            continue

        candidate_zip = _normalize(
            attrs.get("addrzip") or attrs.get("ADDRZIP")
        )

        if (
            target_zip
            and candidate_zip
            and candidate_zip != _normalize(target_zip)
        ):
            continue

        candidate_name = _normalize(
            attrs.get("addrname") or attrs.get("ADDRNAME")
        )
        candidate_suffix = _normalize(
            attrs.get("addrsfx") or attrs.get("ADDRSFX")
        )
        candidate_full = _normalize(
            " ".join(
                part
                for part in (candidate_name, candidate_suffix)
                if part
            )
        )

        same_street = (
            candidate_name in street_variants
            or candidate_full in street_variants
        )

        raw_number = (
            attrs.get("addrnmbr")
            or attrs.get("ADDRNMBR")
        )

        try:
            number = int(float(raw_number))
        except (TypeError, ValueError):
            number = None

        row = evidence.setdefault(
            apn,
            {
                "all_numbers": set(),
                "same_street_numbers": set(),
                "same_street_count": 0,
            },
        )

        if number is not None:
            row["all_numbers"].add(number)

        if same_street:
            row["same_street_count"] += 1

            if number is not None:
                row["same_street_numbers"].add(number)

    return evidence


def _score_address_evidence(
    target_number: int,
    evidence: dict | None,
) -> tuple[int, list[str]]:
    if not evidence:
        return 0, []

    numbers = sorted(
        evidence.get("same_street_numbers") or []
    )

    if not numbers:
        return 0, []

    score = 35
    reasons = ["official address points on requested street"]

    if target_number in numbers:
        score += 180
        reasons.append("exact official house number on candidate APN")
        return score, reasons

    parity = target_number % 2
    same_parity = [
        number
        for number in numbers
        if number % 2 == parity
    ]
    opposite_parity = [
        number
        for number in numbers
        if number % 2 != parity
    ]

    if same_parity:
        score += 25
        reasons.append("same-side address parity")

        nearest_gap = min(
            abs(number - target_number)
            for number in same_parity
        )

        if nearest_gap <= 2:
            score += 50
            reasons.append("same-side official number within 2")
        elif nearest_gap <= 6:
            score += 35
            reasons.append("same-side official number within 6")
        elif nearest_gap <= 20:
            score += 20
            reasons.append("same-side official number within 20")

        lower = [
            number
            for number in same_parity
            if number < target_number
        ]
        upper = [
            number
            for number in same_parity
            if number > target_number
        ]

        if lower and upper:
            low = max(lower)
            high = min(upper)

            if high - low <= 40:
                score += 55
                reasons.append(
                    f"same-side official numbers bracket target ({low}-{high})"
                )

    elif opposite_parity:
        score -= 55
        reasons.append("only opposite-side address parity")

    if len(numbers) >= 4:
        score += 20
        reasons.append("multi-address parcel")
    elif len(numbers) >= 2:
        score += 10
        reasons.append("multiple same-street addresses")

    return score, reasons


def _rank_nearby_parcel_candidates_impl(
    address: str,
    geocoded: dict,
    max_distance_feet: float = 325.0,
) -> dict | None:
    """
    Central inferred-address resolver.

    IMPORTANT:
    This function is used only after exact/verified official address matching
    has failed.

    It ranks multiple nearby parcels using:
      - measured parcel distance from the geocoder point
      - official SanGIS same-street address evidence by APN
      - even/odd side-of-street parity
      - SANDAG 2025 countywide current-land-use sanity checking

    A nearby roadway/right-of-way parcel is intentionally allowed to lose to a
    slightly farther plausible property parcel. If evidence is ambiguous, the
    function returns None rather than guessing.
    """
    parsed = _parse_address(address)

    if parsed is None:
        return None

    target_number = int(parsed["number"])

    try:
        x, y = transformer.transform(
            float(geocoded["longitude"]),
            float(geocoded["latitude"]),
            direction="INVERSE",
        )
    except Exception:
        return None

    try:
        data = _request_json(
            PARCEL_URL,
            params={
                "where": "1=1",
                "geometry": f"{x},{y}",
                "geometryType": "esriGeometryPoint",
                "inSR": 2230,
                "spatialRel": "esriSpatialRelIntersects",
                "distance": max_distance_feet,
                "units": "esriSRUnit_Foot",
                "outFields": "APN",
                "returnGeometry": "true",
                "outSR": 2230,
                "resultRecordCount": 50,
                "f": "json",
            },
            label="Ranked parcel candidate query",
            read_timeout=10,
        )
    except Exception as error:
        print(
            "[Housing OS locator] Ranked parcel candidate query failed: "
            f"{error}"
        )
        return None

    point = Point(x, y)
    candidates_by_apn = {}

    for feature in data.get("features") or []:
        attrs = feature.get("attributes") or {}
        raw_apn = attrs.get("APN")

        if raw_apn is None:
            continue

        apn = "".join(
            ch
            for ch in str(raw_apn)
            if ch.isdigit()
        )

        if len(apn) != 10:
            continue

        shape = _arcgis_geometry_to_shape(
            feature.get("geometry") or {}
        )

        if shape is None:
            continue

        distance = float(shape.distance(point))

        current = candidates_by_apn.get(apn)

        if (
            current is None
            or distance < current["distance_feet"]
        ):
            candidates_by_apn[apn] = {
                "apn": apn,
                "shape": shape,
                "distance_feet": distance,
            }

    candidates = sorted(
        candidates_by_apn.values(),
        key=lambda item: item["distance_feet"],
    )

    if not candidates:
        return None

    # Keep the validation set bounded for latency.
    candidates = candidates[:12]

    print(
        "[Housing OS locator] Parcel candidate query produced "
        f"{len(candidates)} unique APN candidate(s): "
        + ", ".join(candidate["apn"] for candidate in candidates)
    )

    address_evidence = _collect_nearby_official_address_evidence(
        address=address,
        geocoded=geocoded,
    )

    print(
        "[Housing OS locator] Validating "
        f"{len(candidates)} nearby parcel candidate(s)."
    )

    # Run candidate validation sequentially. This stage is intentionally kept
    # simple and deterministic because correctness matters more than shaving a
    # second or two from an inferred address lookup.
    for index, candidate in enumerate(candidates, start=1):
        print(
            "[Housing OS locator] Validating candidate "
            f"{index}/{len(candidates)} APN {candidate['apn']} "
            f"distance={candidate['distance_feet']:.1f}ft"
        )

        try:
            candidate["land_use"] = _query_current_land_use_for_shape(
                candidate["shape"]
            )
        except Exception as error:
            print(
                "[Housing OS locator] Candidate land-use validation "
                f"failed for APN {candidate['apn']}: "
                f"{type(error).__name__}: {error}"
            )
            traceback.print_exc()
            candidate["land_use"] = {
                "description": None,
                "code": None,
            }

    ranked = []

    for candidate in candidates:
        score = 0
        reasons = []
        distance = candidate["distance_feet"]

        # Distance is useful, but intentionally not dominant.
        if distance <= 5:
            score += 55
            reasons.append("geocoder point essentially on parcel")
        elif distance <= 20:
            score += 45
            reasons.append("parcel within 20 ft")
        elif distance <= 50:
            score += 32
            reasons.append("parcel within 50 ft")
        elif distance <= 100:
            score += 20
            reasons.append("parcel within 100 ft")
        elif distance <= 175:
            score += 10
            reasons.append("parcel within 175 ft")
        else:
            score += 0

        evidence_score, evidence_reasons = _score_address_evidence(
            target_number=target_number,
            evidence=address_evidence.get(
                candidate["apn"]
            ),
        )
        score += evidence_score
        reasons.extend(evidence_reasons)

        land_use_description = (
            candidate.get("land_use", {})
            .get("description")
        )

        penalty, penalty_reason = (
            _transportation_land_use_penalty(
                land_use_description
            )
        )
        score += penalty

        if penalty_reason:
            reasons.append(penalty_reason)
        else:
            positive, positive_reason = (
                _positive_land_use_score(
                    land_use_description
                )
            )
            score += positive

            if positive_reason:
                reasons.append(positive_reason)

        ranked.append(
            {
                "apn": candidate["apn"],
                "distance_feet": round(distance, 1),
                "score": score,
                "land_use_description": land_use_description,
                "land_use_code": (
                    candidate.get("land_use", {})
                    .get("code")
                ),
                "reasons": reasons,
            }
        )

    ranked.sort(
        key=lambda item: (
            item["score"],
            -item["distance_feet"],
        ),
        reverse=True,
    )

    print(
        "[Housing OS locator] Ranked parcel candidates: "
        + "; ".join(
            (
                f"{item['apn']} score={item['score']} "
                f"dist={item['distance_feet']}ft "
                f"landuse={item['land_use_description']!r}"
            )
            for item in ranked[:6]
        )
    )

    best = ranked[0]
    second = ranked[1] if len(ranked) > 1 else None

    # Never accept a candidate that the current-land-use sanity check says is
    # clearly transportation/right-of-way.
    best_transport_penalty, _ = _transportation_land_use_penalty(
        best["land_use_description"]
    )

    if best_transport_penalty < 0:
        print(
            "[Housing OS locator] Best inferred candidate was still a "
            "transportation/right-of-way parcel. Refusing to guess."
        )
        return None

    # Require enough affirmative evidence.
    if best["score"] < 30:
        print(
            "[Housing OS locator] Inferred parcel evidence was too weak "
            "to choose safely."
        )
        return None

    # If the top two are close, return ambiguity rather than a false certainty.
    if (
        second is not None
        and best["score"] - second["score"] < 18
    ):
        print(
            "[Housing OS locator] Top inferred parcel candidates were too "
            "close to choose safely."
        )
        return None

    confidence = (
        "high"
        if best["score"] >= 90
        else "moderate"
    )

    print(
        "[Housing OS locator] Ranked resolver accepted APN "
        f"{best['apn']} score={best['score']} "
        f"at {best['distance_feet']} ft "
        f"({confidence} confidence)."
    )

    return {
        "apn": best["apn"],
        "distance_feet": best["distance_feet"],
        "confidence": confidence,
        "score": best["score"],
        "land_use_description": best["land_use_description"],
        "land_use_code": best["land_use_code"],
        "resolution_reasons": best["reasons"],
        "candidate_count": len(ranked),
    }



def _rank_nearby_parcel_candidates(
    address: str,
    geocoded: dict,
    max_distance_feet: float = 325.0,
) -> dict | None:
    """
    Diagnostic wrapper around the complete inferred parcel ranking stage.
    No exception is allowed to disappear silently.
    """
    try:
        return _rank_nearby_parcel_candidates_impl(
            address=address,
            geocoded=geocoded,
            max_distance_feet=max_distance_feet,
        )
    except Exception as error:
        print(
            "[Housing OS locator] Full candidate ranking failed: "
            f"{type(error).__name__}: {error}"
        )
        traceback.print_exc()
        raise



def _ranked_candidate_result(
    address: str,
    geocoded: dict,
    match: dict,
) -> dict:
    parcel = {
        "apn": match["apn"],
        "address": (
            geocoded.get("matched_address")
            or address
        ),
        "zip": _extract_zip(address),
        "community": None,
        "latitude": geocoded["latitude"],
        "longitude": geocoded["longitude"],
        "address_match_confidence": match["confidence"],
        "address_to_parcel_distance_feet": (
            match["distance_feet"]
        ),
        "address_match_score": match["score"],
        "address_match_method": (
            "ranked_multi_signal_parcel_candidates"
        ),
        "address_match_reasons": (
            match.get("resolution_reasons")
            or []
        ),
    }

    parcel = _attach_boundary(parcel)

    return {
        "address": address,
        "parcel_count": 1,
        "parcels": [parcel],
        "source": (
            "SanGIS Address Points + SANDAG Land Use 2025 + "
            "U.S. Census Geocoder + County of San Diego Assessor Parcels"
        ),
        "status": "found",
        "message": (
            "The address was not available as an exact official SITUS record. "
            "Housing OS ranked multiple nearby tax parcels using parcel "
            "distance, official address-point evidence, side-of-street parity, "
            "and countywide current-land-use validation."
        ),
        "lookup_method": (
            "geocode_then_ranked_multi_signal_parcel_candidates"
        ),
    }



def _find_nearby_parcel_with_confidence(
    latitude: float,
    longitude: float,
    max_distance_feet: float = 175.0,
) -> dict | None:
    """
    Tolerant parcel resolution for geocoded addresses that land just outside
    a parcel polygon (common with shopping centers, driveways, road centerlines,
    and interpolated business addresses).

    Safety rules:
    - Query only within a small 175-foot radius.
    - Calculate true geometry distance locally.
    - Accept only when the closest parcel is clearly better than the runner-up,
      OR the geocoder point is extremely close to one parcel.
    - Never accept a parcel farther than max_distance_feet.
    """

    try:
        # Existing transformer is State Plane 2230 -> WGS84, so reverse it.
        x, y = transformer.transform(
            longitude,
            latitude,
            direction="INVERSE",
        )
    except Exception:
        return None

    try:
        data = _request_json(
            PARCEL_URL,
            params={
                "where": "1=1",
                "geometry": f"{x},{y}",
                "geometryType": "esriGeometryPoint",
                "inSR": 2230,
                "spatialRel": "esriSpatialRelIntersects",
                "distance": max_distance_feet,
                "units": "esriSRUnit_Foot",
                "outFields": "APN",
                "returnGeometry": "true",
                "outSR": 2230,
                "resultRecordCount": 20,
                "f": "json",
            },
            label="County nearby parcel candidates",
            read_timeout=8,
        )
    except Exception as error:
        print(
            "[Housing OS locator] Nearby parcel candidate query failed: "
            f"{error}"
        )
        return None

    features = data.get("features") or []

    print(
        "[Housing OS locator] Nearby parcel query returned "
        f"{len(features)} candidate parcel(s)."
    )

    if not features:
        return None

    point = Point(x, y)
    candidates = []

    for feature in features:
        attrs = feature.get("attributes") or {}
        apn = attrs.get("APN")

        if not apn:
            continue

        digits = "".join(
            character
            for character in str(apn)
            if character.isdigit()
        )

        if len(digits) != 10:
            continue

        shape = _arcgis_geometry_to_shape(
            feature.get("geometry") or {}
        )

        if shape is None:
            continue

        distance = float(shape.distance(point))

        candidates.append(
            {
                "apn": digits,
                "distance_feet": distance,
            }
        )

    if not candidates:
        return None

    # De-duplicate APNs and keep the minimum measured distance.
    best_by_apn = {}

    for candidate in candidates:
        apn = candidate["apn"]
        distance = candidate["distance_feet"]

        if (
            apn not in best_by_apn
            or distance < best_by_apn[apn]
        ):
            best_by_apn[apn] = distance

    ranked = sorted(
        (
            {
                "apn": apn,
                "distance_feet": distance,
            }
            for apn, distance in best_by_apn.items()
        ),
        key=lambda item: item["distance_feet"],
    )

    closest = ranked[0]

    if closest["distance_feet"] > max_distance_feet:
        return None

    # If the point is within 20 feet of the parcel, confidence is high.
    if closest["distance_feet"] <= 20:
        confidence = "high"
    elif len(ranked) == 1:
        confidence = "high"
    else:
        second = ranked[1]

        gap = second["distance_feet"] - closest["distance_feet"]

        # Require a meaningful separation from the next possible parcel.
        if gap >= 35:
            confidence = "high"
        elif (
            closest["distance_feet"] <= 60
            and second["distance_feet"]
            >= closest["distance_feet"] * 2
        ):
            confidence = "moderate"
        else:
            print(
                "[Housing OS locator] Nearby parcel candidates were too "
                "ambiguous to choose safely."
            )
            return None

    print(
        "[Housing OS locator] Nearby parcel accepted APN "
        f"{closest['apn']} at {closest['distance_feet']:.1f} ft "
        f"({confidence} confidence)."
    )

    return {
        "apn": closest["apn"],
        "distance_feet": round(
            closest["distance_feet"],
            1,
        ),
        "confidence": confidence,
    }


def _nearby_parcel_result(
    address: str,
    geocoded: dict,
    match: dict,
) -> dict:
    parcel = {
        "apn": match["apn"],
        "address": (
            geocoded.get("matched_address")
            or address
        ),
        "zip": None,
        "community": None,
        "latitude": geocoded["latitude"],
        "longitude": geocoded["longitude"],
        "address_match_confidence": match["confidence"],
        "address_to_parcel_distance_feet": (
            match["distance_feet"]
        ),
    }

    parcel = _attach_boundary(parcel)

    return {
        "address": address,
        "parcel_count": 1,
        "parcels": [parcel],
        "source": (
            "U.S. Census Geocoder + "
            "County of San Diego Assessor Parcels"
        ),
        "status": "found",
        "message": (
            "The geocoded address did not fall directly inside a parcel. "
            "Housing OS matched it to the nearest clearly distinguishable "
            f"parcel within {match['distance_feet']} feet."
        ),
        "lookup_method": (
            "geocode_then_confident_nearby_parcel"
        ),
    }


def get_parcel_data_resilient(
    address: str,
) -> dict:
    """
    Countywide address -> parcel resolver.

    Resolution order:
      A. Exact official SanGIS address -> APN(s)
      B. Legacy County exact address -> APN
      C. Census geocode -> nearby official SanGIS point, but still require
         exact house number + street -> APN(s)
      D. If no exact official address exists, rank multiple nearby parcels
         using distance + official address evidence + parity + current land use

    The inferred stage intentionally does NOT use "nearest parcel wins."
    If the evidence is ambiguous, Housing OS returns not_found rather than
    silently attaching the address to a roadway or unrelated neighboring APN.
    """

    overall_started = time.perf_counter()

    # A. Best source: exact official countywide SanGIS address point.
    sandag_parcels = _sandag_exact_official_lookup(address)
    if not sandag_parcels:
        sandag_parcels = _sandag_address_lookup(address)

    if sandag_parcels:
        result = _sandag_result(
            address=address,
            parcels=sandag_parcels,
        )

        _timed_message(
            "TOTAL parcel locator",
            overall_started,
        )
        return result

    print(
        "[Housing OS locator] Exact SanGIS text lookup did not resolve; "
        "starting verified geocode fallback."
    )

    executor = ThreadPoolExecutor(
        max_workers=4,
        thread_name_prefix="housing_os_locator",
    )

    county_exact_future = executor.submit(
        _county_exact_lookup,
        address,
    )
    census_future = executor.submit(
        _geocode_with_census,
        address,
    )

    number_future = None
    nearby_verified_future = None
    ranked_future = None
    geocoded = None

    pending = {
        county_exact_future,
        census_future,
    }

    try:
        while pending:
            done, pending = wait(
                pending,
                return_when=FIRST_COMPLETED,
            )

            for future in done:
                if future is county_exact_future:
                    try:
                        county_parcel = future.result()
                    except Exception:
                        county_parcel = None

                    if county_parcel:
                        result = _county_result(
                            address=address,
                            parcel=county_parcel,
                            method="county_addrapn_exact",
                        )

                        _timed_message(
                            "TOTAL parcel locator",
                            overall_started,
                        )

                        executor.shutdown(
                            wait=False,
                            cancel_futures=True,
                        )
                        return result

                    if number_future is None:
                        number_future = executor.submit(
                            _county_number_fallback,
                            address,
                        )
                        pending.add(number_future)

                elif future is census_future:
                    try:
                        geocoded = future.result()
                    except Exception:
                        geocoded = None

                    if geocoded:
                        # First ask SanGIS whether the geocoder landed near an
                        # official point that EXACTLY matches the requested
                        # house number + street.
                        nearby_verified_future = executor.submit(
                            _sandag_nearby_verified_address_lookup,
                            address,
                            geocoded,
                        )
                        pending.add(nearby_verified_future)

                        if number_future is None:
                            number_future = executor.submit(
                                _county_number_fallback,
                                address,
                            )
                            pending.add(number_future)

                    elif number_future is None:
                        number_future = executor.submit(
                            _county_number_fallback,
                            address,
                        )
                        pending.add(number_future)

                elif future is nearby_verified_future:
                    try:
                        parcels = future.result()
                    except Exception:
                        parcels = []

                    if parcels:
                        result = _sandag_result(
                            address=address,
                            parcels=parcels,
                        )
                        result["lookup_method"] = (
                            "geocode_then_verified_nearby_sangis_address"
                        )

                        _timed_message(
                            "TOTAL parcel locator",
                            overall_started,
                        )

                        executor.shutdown(
                            wait=False,
                            cancel_futures=True,
                        )
                        return result

                    # No exact official tenant/SITUS point exists. This is the
                    # only place where inference is allowed.
                    if (
                        geocoded
                        and ranked_future is None
                    ):
                        ranked_future = executor.submit(
                            _rank_nearby_parcel_candidates,
                            address,
                            geocoded,
                        )
                        pending.add(ranked_future)

                elif future is ranked_future:
                    try:
                        match = future.result()
                    except Exception as error:
                        print(
                            "[Housing OS locator] Ranked resolver crashed: "
                            f"{type(error).__name__}: {error}"
                        )
                        traceback.print_exc()
                        match = None

                    if match and geocoded:
                        result = _ranked_candidate_result(
                            address=address,
                            geocoded=geocoded,
                            match=match,
                        )

                        _timed_message(
                            "TOTAL parcel locator",
                            overall_started,
                        )

                        executor.shutdown(
                            wait=False,
                            cancel_futures=True,
                        )
                        return result

                elif future is number_future:
                    try:
                        county_parcel = future.result()
                    except Exception:
                        county_parcel = None

                    if county_parcel:
                        result = _county_result(
                            address=address,
                            parcel=county_parcel,
                            method="county_addrapn_number_fallback",
                        )

                        _timed_message(
                            "TOTAL parcel locator",
                            overall_started,
                        )

                        executor.shutdown(
                            wait=False,
                            cancel_futures=True,
                        )
                        return result

        _timed_message(
            "TOTAL parcel locator",
            overall_started,
        )

        return {
            "address": address,
            "parcel_count": 0,
            "parcels": [],
            "source": (
                "SanGIS Address Points + SANDAG Land Use 2025 + "
                "San Diego GIS + U.S. Census Geocoder"
            ),
            "status": "not_found",
            "message": (
                "Housing OS could not identify one parcel with enough "
                "evidence to choose safely. Multiple parcels may be plausible, "
                "or the address may be a tenant/unit address without a direct "
                "official parcel address."
            ),
        }

    finally:
        try:
            executor.shutdown(
                wait=False,
                cancel_futures=True,
            )
        except Exception:
            pass
