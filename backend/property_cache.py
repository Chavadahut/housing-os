import json
import sqlite3
import time
from pathlib import Path
from threading import Lock
from typing import Any


DATABASE_PATH = Path(__file__).resolve().parent / "housing_os_cache.db"

QUICK_CACHE_TTL_SECONDS = 30 * 24 * 60 * 60
FULL_CACHE_TTL_SECONDS = 24 * 60 * 60

_db_lock = Lock()


def normalize_address(address: str) -> str:
    return " ".join(address.lower().strip().split())


def normalize_apn(apn: str | None) -> str | None:
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


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(
        DATABASE_PATH,
        timeout=15,
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    return connection


def initialize_cache_database() -> None:
    with _db_lock:
        connection = _connect()
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS property_cache (
                    cache_type TEXT NOT NULL,
                    cache_key TEXT NOT NULL,
                    apn TEXT,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (cache_type, cache_key)
                )
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_property_cache_apn
                ON property_cache (cache_type, apn)
                """
            )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS address_alias (
                    normalized_address TEXT PRIMARY KEY,
                    apn TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )

            connection.commit()
        finally:
            connection.close()


def _ttl_for(cache_type: str) -> int:
    if cache_type == "quick":
        return QUICK_CACHE_TTL_SECONDS
    return FULL_CACHE_TTL_SECONDS


def get_address_alias(address: str) -> str | None:
    normalized_address = normalize_address(address)

    with _db_lock:
        connection = _connect()
        try:
            row = connection.execute(
                """
                SELECT apn
                FROM address_alias
                WHERE normalized_address = ?
                """,
                (normalized_address,),
            ).fetchone()
        finally:
            connection.close()

    if row is None:
        return None

    return normalize_apn(row["apn"])


def get_cached_property(
    cache_type: str,
    address: str | None = None,
    apn: str | None = None,
) -> dict[str, Any] | None:
    cache_key = None

    if apn:
        normalized_apn = normalize_apn(apn)
        if normalized_apn:
            cache_key = f"apn:{normalized_apn}"

    if cache_key is None and address:
        cache_key = f"address:{normalize_address(address)}"

    if cache_key is None:
        return None

    with _db_lock:
        connection = _connect()
        try:
            row = connection.execute(
                """
                SELECT payload, created_at
                FROM property_cache
                WHERE cache_type = ?
                AND cache_key = ?
                """,
                (cache_type, cache_key),
            ).fetchone()

            if row is None:
                return None

            age_seconds = time.time() - float(row["created_at"])

            if age_seconds > _ttl_for(cache_type):
                connection.execute(
                    """
                    DELETE FROM property_cache
                    WHERE cache_type = ?
                    AND cache_key = ?
                    """,
                    (cache_type, cache_key),
                )
                connection.commit()
                return None

            return json.loads(row["payload"])
        finally:
            connection.close()


def save_cached_property(
    cache_type: str,
    address: str,
    result: dict[str, Any],
) -> None:
    if not result.get("parcels"):
        return

    first_parcel = result["parcels"][0]
    normalized_apn = normalize_apn(first_parcel.get("apn"))

    payload = json.dumps(
        result,
        separators=(",", ":"),
    )

    created_at = time.time()

    keys = [
        f"address:{normalize_address(address)}"
    ]

    if normalized_apn:
        keys.append(f"apn:{normalized_apn}")

    with _db_lock:
        connection = _connect()
        try:
            for cache_key in keys:
                connection.execute(
                    """
                    INSERT INTO property_cache (
                        cache_type,
                        cache_key,
                        apn,
                        payload,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(cache_type, cache_key)
                    DO UPDATE SET
                        apn = excluded.apn,
                        payload = excluded.payload,
                        created_at = excluded.created_at
                    """,
                    (
                        cache_type,
                        cache_key,
                        normalized_apn,
                        payload,
                        created_at,
                    ),
                )

            if normalized_apn:
                connection.execute(
                    """
                    INSERT INTO address_alias (
                        normalized_address,
                        apn,
                        updated_at
                    )
                    VALUES (?, ?, ?)
                    ON CONFLICT(normalized_address)
                    DO UPDATE SET
                        apn = excluded.apn,
                        updated_at = excluded.updated_at
                    """,
                    (
                        normalize_address(address),
                        normalized_apn,
                        created_at,
                    ),
                )

            connection.commit()
        finally:
            connection.close()


def get_cached_by_address_or_apn(
    cache_type: str,
    address: str,
) -> dict[str, Any] | None:
    cached = get_cached_property(
        cache_type=cache_type,
        address=address,
    )

    if cached is not None:
        return cached

    alias_apn = get_address_alias(address)

    if alias_apn is None:
        return None

    return get_cached_property(
        cache_type=cache_type,
        apn=alias_apn,
    )


def clear_expired_cache() -> None:
    now = time.time()

    with _db_lock:
        connection = _connect()
        try:
            connection.execute(
                """
                DELETE FROM property_cache
                WHERE cache_type = 'quick'
                AND (? - created_at) > ?
                """,
                (now, QUICK_CACHE_TTL_SECONDS),
            )

            connection.execute(
                """
                DELETE FROM property_cache
                WHERE cache_type = 'full'
                AND (? - created_at) > ?
                """,
                (now, FULL_CACHE_TTL_SECONDS),
            )

            connection.commit()
        finally:
            connection.close()