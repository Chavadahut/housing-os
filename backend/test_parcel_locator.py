import json
import time
import unittest

from parcel_locator import (
    _official_address_feature_matches,
    _parse_address,
    get_parcel_data_resilient,
)


ADDRESSES = [
    "16616 Highland Valley Road, Ramona, CA 92065",
    "14405 Mussey Grade Road, Ramona, CA 92065",
    "3411 Fairway Drive",
    "14351 Vista Panorama, Lakeside, CA 92040",
]


class OfficialAddressMatchTests(unittest.TestCase):
    def test_conflicting_street_suffix_is_rejected(self):
        parsed = _parse_address("100 Main Street")
        feature = {
            "attributes": {
                "addrnmbr": 100,
                "addrname": "MAIN",
                "addrsfx": "AVE",
                "addrzip": "92028",
            }
        }

        self.assertFalse(
            _official_address_feature_matches(
                feature,
                parsed,
            )
        )

    def test_equivalent_street_suffix_is_accepted(self):
        parsed = _parse_address("100 Main Street")
        feature = {
            "attributes": {
                "addrnmbr": 100,
                "addrname": "MAIN",
                "addrsfx": "ST",
                "addrzip": "92028",
            }
        }

        self.assertTrue(
            _official_address_feature_matches(
                feature,
                parsed,
            )
        )


def main():
    print("=" * 80)
    print("HOUSING OS PARCEL LOCATOR TEST")
    print("=" * 80)

    for address in ADDRESSES:
        print("\n" + "-" * 80)
        print(address)
        print("-" * 80)

        started = time.perf_counter()

        result = get_parcel_data_resilient(
            address
        )

        elapsed = time.perf_counter() - started

        summary = {
            "address": result.get("address"),
            "status": result.get("status"),
            "parcel_count": result.get("parcel_count"),
            "lookup_method": result.get("lookup_method"),
            "source": result.get("source"),
            "message": result.get("message"),
            "apns": [
                parcel.get("apn")
                for parcel in result.get("parcels", [])
            ],
            "parcel_addresses": [
                parcel.get("address")
                for parcel in result.get("parcels", [])
            ],
            "elapsed_seconds": round(elapsed, 2),
        }

        print(
            json.dumps(
                summary,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
