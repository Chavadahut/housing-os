"""
Housing OS - stale cache buster.

Run this any time you change zoning/land-use/analysis-point logic and want
to force a completely fresh lookup for a specific address, instead of
waiting up to 24 hours for the "full" cache entry to expire on its own.

Usage:
    python clear_cache.py
    python clear_cache.py "1234 Some Other St, City, CA 90000"
    python clear_cache.py --all

Run this from inside the backend folder (the same folder that contains
housing_os_cache.db), or it will not find the database.
"""

import sqlite3
import sys
from pathlib import Path


DATABASE_PATH = Path(__file__).resolve().parent / "housing_os_cache.db"

DEFAULT_ADDRESS = "8060 La Mesa Blvd, La Mesa, CA 91942"
DEFAULT_APN = "4705810700"


def normalize_address(address: str) -> str:
    return " ".join(address.lower().strip().split())


def normalize_apn(apn: str | None) -> str | None:
    if apn is None:
        return None

    digits = "".join(character for character in str(apn) if character.isdigit())

    if len(digits) != 10:
        return None

    return digits


def clear_all(connection: sqlite3.Connection) -> None:
    cursor = connection.execute("DELETE FROM property_cache")
    connection.execute("DELETE FROM address_alias")
    connection.commit()
    print(f"Cleared entire cache. Removed {cursor.rowcount} row(s) from property_cache.")


def clear_for_address(connection: sqlite3.Connection, address: str, apn: str | None) -> None:
    normalized_address = normalize_address(address)
    normalized_apn = normalize_apn(apn)

    keys_to_clear = [f"address:{normalized_address}"]

    if normalized_apn:
        keys_to_clear.append(f"apn:{normalized_apn}")

    total_removed = 0

    for cache_type in ("full", "quick"):
        for cache_key in keys_to_clear:
            cursor = connection.execute(
                """
                DELETE FROM property_cache
                WHERE cache_type = ?
                AND cache_key = ?
                """,
                (cache_type, cache_key),
            )
            total_removed += cursor.rowcount

    connection.commit()

    print(f"Address:          {address}")
    print(f"Normalized as:    {normalized_address}")
    print(f"APN targeted:     {normalized_apn or '(none provided)'}")
    print(f"Cache keys cleared: {keys_to_clear}")
    print(f"Rows removed:     {total_removed}")

    if total_removed == 0:
        print(
            "\nNo matching rows were found. Either this address was never "
            "cached, or it was already cleared/expired."
        )
    else:
        print("\nDone. The next request for this address will run a fresh lookup.")


def main() -> None:
    if not DATABASE_PATH.exists():
        print(f"Could not find {DATABASE_PATH}.")
        print("Run this script from inside your backend folder, next to housing_os_cache.db.")
        sys.exit(1)

    connection = sqlite3.connect(DATABASE_PATH)

    try:
        if len(sys.argv) > 1 and sys.argv[1] == "--all":
            clear_all(connection)
            return

        address = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ADDRESS
        apn = DEFAULT_APN if address == DEFAULT_ADDRESS else None

        clear_for_address(connection, address=address, apn=apn)
    finally:
        connection.close()


if __name__ == "__main__":
    main()