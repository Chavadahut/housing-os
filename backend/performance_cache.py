import functools
import hashlib
import json
import sqlite3
import time
from pathlib import Path
from threading import Lock
from typing import Any


DATABASE_PATH = Path(__file__).resolve().parent / "housing_os_cache.db"
_db_lock = Lock()

# Bump this whenever connector cache semantics change.
# This makes old/stale dataset-cache keys harmless without deleting
# the entire SQLite database.
DATASET_CACHE_VERSION = "v13"
FAILED_RESULT_TTL_SECONDS = 5 * 60


# How long each type of data can be reused before Housing OS calls
# the outside service again.
TTL_BY_CATEGORY = {
    "parcel": 30 * 24 * 60 * 60,
    "lot_size": 30 * 24 * 60 * 60,
    "zoning": 30 * 24 * 60 * 60,
    "general_plan": 30 * 24 * 60 * 60,
    "land_use": 30 * 24 * 60 * 60,
    "terrain": 90 * 24 * 60 * 60,
    "habitat": 30 * 24 * 60 * 60,
    "wetlands": 30 * 24 * 60 * 60,
    "flood": 7 * 24 * 60 * 60,
    "fire": 7 * 24 * 60 * 60,
    "utilities": 7 * 24 * 60 * 60,
    "road_access": 30 * 24 * 60 * 60,
    "easements": 7 * 24 * 60 * 60,
    "permits": 24 * 60 * 60,
    "default": 7 * 24 * 60 * 60,
}


# We only wrap likely external-data connector functions.
# Several possible historical names are included so this can work
# with the current Housing OS service file without forcing a rewrite.
FUNCTION_CATEGORY = {
    "get_parcel_data": "parcel",
    "get_lot_size_data": "lot_size",
    "get_zoning_data": "zoning",
    "get_county_zoning_data": "zoning",
    "get_la_mesa_zoning_data": "zoning",
    "get_encinitas_zoning_data": "zoning",
    "get_carlsbad_zoning_data": "zoning",
    "get_general_plan_data": "general_plan",
    "get_county_general_plan_data": "general_plan",
    "get_la_mesa_general_plan_data": "general_plan",
    "get_encinitas_general_plan_data": "general_plan",
    "get_carlsbad_general_plan_data": "general_plan",
    "get_land_use_data": "land_use",
    "get_current_land_use_data": "land_use",
    "get_sandag_land_use_data": "land_use",
    "get_flood_hazard_data": "flood",
    "get_flood_data": "flood",
    "get_fire_hazard_data": "fire",
    "get_fire_data": "fire",
    "get_terrain_data": "terrain",
    "get_habitat_data": "habitat",
    "get_wetlands_data": "wetlands",
    "get_utility_data": "utilities",
    "get_utilities_data": "utilities",
    "get_road_access_data": "road_access",
    "get_easement_data": "easements",
    "get_easements_data": "easements",
    "get_easement_screening_data": "easements",
    "get_permit_history_data": "permits",
    "get_la_mesa_permit_history_data": "permits",
    "get_encinitas_permit_history_data": "permits",
    "get_carlsbad_permit_history_data": "permits",
    "get_permit_data": "permits",
}


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(
        DATABASE_PATH,
        timeout=15,
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    return connection


def initialize_dataset_cache() -> None:
    with _db_lock:
        connection = _connect()
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS dataset_cache (
                    function_name TEXT NOT NULL,
                    cache_key TEXT NOT NULL,
                    category TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (function_name, cache_key)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_dataset_cache_category
                ON dataset_cache (category, created_at)
                """
            )
            connection.commit()
        finally:
            connection.close()


def _stable_value(value: Any) -> Any:
    """
    Convert connector arguments into a repeatable JSON-safe shape.

    Parcel GeoJSON can be large, so it is still hashed before being
    used as an SQLite cache key.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, dict):
        return {
            str(key): _stable_value(item)
            for key, item in sorted(
                value.items(),
                key=lambda pair: str(pair[0]),
            )
        }

    if isinstance(value, (list, tuple)):
        return [_stable_value(item) for item in value]

    if isinstance(value, set):
        return sorted(_stable_value(item) for item in value)

    return repr(value)


def _make_cache_key(args: tuple, kwargs: dict) -> str:
    raw = json.dumps(
        {
            "cache_version": DATASET_CACHE_VERSION,
            "args": _stable_value(args),
            "kwargs": _stable_value(kwargs),
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _get_cached(
    function_name: str,
    cache_key: str,
    category: str,
):
    ttl_seconds = TTL_BY_CATEGORY.get(
        category,
        TTL_BY_CATEGORY["default"],
    )

    with _db_lock:
        connection = _connect()
        try:
            row = connection.execute(
                """
                SELECT payload, created_at
                FROM dataset_cache
                WHERE function_name = ?
                AND cache_key = ?
                """,
                (function_name, cache_key),
            ).fetchone()

            if row is None:
                return None

            cached_result = json.loads(row["payload"])
            age_seconds = time.time() - float(row["created_at"])

            if (
                isinstance(cached_result, dict)
                and cached_result.get("status") in {
                    "not_found",
                    "error",
                    "partial_error",
                }
            ):
                ttl_seconds = min(
                    ttl_seconds,
                    FAILED_RESULT_TTL_SECONDS,
                )

            if age_seconds > ttl_seconds:
                connection.execute(
                    """
                    DELETE FROM dataset_cache
                    WHERE function_name = ?
                    AND cache_key = ?
                    """,
                    (function_name, cache_key),
                )
                connection.commit()
                return None

            return cached_result
        finally:
            connection.close()


def _save_cached(
    function_name: str,
    cache_key: str,
    category: str,
    result,
) -> None:
    try:
        payload = json.dumps(
            result,
            separators=(",", ":"),
            default=str,
        )
    except Exception:
        return

    with _db_lock:
        connection = _connect()
        try:
            connection.execute(
                """
                INSERT INTO dataset_cache (
                    function_name,
                    cache_key,
                    category,
                    payload,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(function_name, cache_key)
                DO UPDATE SET
                    category = excluded.category,
                    payload = excluded.payload,
                    created_at = excluded.created_at
                """,
                (
                    function_name,
                    cache_key,
                    category,
                    payload,
                    time.time(),
                ),
            )
            connection.commit()
        finally:
            connection.close()


def _format_seconds(seconds: float) -> str:
    return f"{seconds:.2f}s"


def _wrap_connector(
    function,
    function_name: str,
    category: str,
):
    if getattr(function, "_housing_os_cached", False):
        return function

    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        cache_key = _make_cache_key(args, kwargs)

        cache_started = time.perf_counter()
        cached = _get_cached(
            function_name,
            cache_key,
            category,
        )
        cache_elapsed = time.perf_counter() - cache_started

        if cached is not None:
            print(
                f"[Housing OS cache HIT] "
                f"{function_name:<32} "
                f"{_format_seconds(cache_elapsed)}"
            )
            return cached

        started = time.perf_counter()

        try:
            result = function(*args, **kwargs)
        except Exception:
            elapsed = time.perf_counter() - started
            print(
                f"[Housing OS ERROR]     "
                f"{function_name:<32} "
                f"{_format_seconds(elapsed)}"
            )
            raise

        elapsed = time.perf_counter() - started

        # Cache returned connector dictionaries/lists. We intentionally
        # avoid caching raised exceptions.
        #
        # IMPORTANT: never cache a failed address -> parcel lookup.
        # A temporary County GIS failure must not become a persistent
        # "property not found" result.
        should_cache = isinstance(result, (dict, list))

        if (
            should_cache
            and category == "parcel"
            and isinstance(result, dict)
            and not result.get("parcels")
        ):
            should_cache = False

        if should_cache:
            _save_cached(
                function_name,
                cache_key,
                category,
                result,
            )

        print(
            f"[Housing OS LIVE]      "
            f"{function_name:<32} "
            f"{_format_seconds(elapsed)}"
        )

        return result

    wrapped._housing_os_cached = True
    return wrapped


def install_dataset_cache(service_module) -> list[str]:
    """
    Replace external connector functions already imported into
    services.py with cached/timed wrappers.

    The lookup_property code itself does not need to change.
    """
    initialize_dataset_cache()

    installed = []

    for function_name, category in FUNCTION_CATEGORY.items():
        function = getattr(
            service_module,
            function_name,
            None,
        )

        if not callable(function):
            continue

        wrapped = _wrap_connector(
            function,
            function_name,
            category,
        )

        setattr(
            service_module,
            function_name,
            wrapped,
        )
        installed.append(function_name)

    print(
        "[Housing OS] Per-dataset cache enabled for: "
        + (
            ", ".join(installed)
            if installed
            else "no matching connector functions"
        )
    )

    return installed
