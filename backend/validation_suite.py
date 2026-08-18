"""Reusable live validation matrix for the Housing OS API."""

from __future__ import annotations

import json
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_ROOT = "http://127.0.0.1:8000"
RESULT_PATH = Path(__file__).with_name("validation_results.json")
MAX_WORKERS = 3

CASES = [
    {
        "id": "ramona_standard",
        "address": "313 Penn Street",
        "expected_jurisdiction": "Unincorporated San Diego County",
    },
    {
        "id": "ramona_rural",
        "address": "16616 Highland Valley Road, Ramona, CA 92065",
        "expected_jurisdiction": "Unincorporated San Diego County",
    },
    {
        "id": "lakeside_rural",
        "address": "14351 Vista Panorama, Lakeside, CA 92040",
        "expected_jurisdiction": "Unincorporated San Diego County",
    },
    {
        "id": "san_diego_zoo",
        "address": "2920 Zoo Dr, San Diego, CA 92101",
        "expected_jurisdiction": "City of San Diego",
    },
    {
        "id": "san_diego_civic",
        "address": "202 C St, San Diego, CA 92101",
        "expected_jurisdiction": "City of San Diego",
    },
    {
        "id": "incomplete_valid",
        "address": "3411 Fairway Drive",
        "expected_jurisdiction": "Unincorporated San Diego County",
    },
    {
        "id": "la_mesa_commercial",
        "address": "8060 La Mesa Blvd, La Mesa, CA 91942",
        "expected_jurisdiction": "City of La Mesa",
    },
    {
        "id": "la_mesa_second",
        "address": "8400 La Mesa Blvd, La Mesa, CA 91942",
        "expected_jurisdiction": "City of La Mesa",
    },
    {
        "id": "encinitas_commercial",
        "address": "160 Calle Magdalena, Encinitas, CA 92024",
        "expected_jurisdiction": "City of Encinitas",
    },
    {
        "id": "ambiguous_rejected",
        "address": "100 Main Street",
        "expect_rejection": True,
    },
    {
        "id": "invalid_rejected",
        "address": "999999 Imaginary Development Way, San Diego, CA 92101",
        "expect_rejection": True,
    },
]


def _post(path: str, address: str, timeout: int = 300) -> dict:
    request = Request(
        f"{API_ROOT}{path}",
        data=json.dumps({"address": address}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _validate_success(case: dict, result: dict) -> tuple[list[str], list[str]]:
    failures = []
    warnings = []
    parcels = result.get("parcels") or []

    if len(parcels) != 1:
        failures.append(f"expected one parcel; received {len(parcels)}")
        return failures, warnings

    parcel = parcels[0]
    jurisdiction = parcel.get("jurisdiction") or result.get("jurisdiction") or {}
    jurisdiction_name = jurisdiction.get("name")

    if jurisdiction_name != case["expected_jurisdiction"]:
        failures.append(
            f"jurisdiction was {jurisdiction_name!r}; expected "
            f"{case['expected_jurisdiction']!r}"
        )

    if not parcel.get("apn"):
        failures.append("APN missing")

    lot_size = parcel.get("lot_size") or {}
    lot_square_feet = lot_size.get("square_feet")
    if not isinstance(lot_square_feet, (int, float)) or lot_square_feet <= 0:
        failures.append("usable lot size missing")

    zoning = parcel.get("zoning") or {}
    general_plan = parcel.get("general_plan") or {}

    if zoning.get("status") not in {"found", "not_implemented"}:
        warnings.append(f"zoning status: {zoning.get('status')}")

    if general_plan.get("status") not in {"found", "not_implemented"}:
        warnings.append(f"general-plan status: {general_plan.get('status')}")

    scenario = parcel.get("development_scenario") or {}
    density = scenario.get("density") or {}
    minimum_sqft = density.get("minimum_lot_size_square_feet")
    zoning_units = density.get("zoning_lot_size_screen_units")

    if isinstance(minimum_sqft, (int, float)) and minimum_sqft < 100:
        failures.append(f"implausible minimum lot size: {minimum_sqft} sq ft")

    if (
        isinstance(lot_square_feet, (int, float))
        and isinstance(minimum_sqft, (int, float))
        and minimum_sqft > 0
        and isinstance(zoning_units, int)
    ):
        expected_screen = max(1, math.floor(lot_square_feet / minimum_sqft))
        if zoning_units != expected_screen:
            failures.append(
                f"zoning capacity {zoning_units} disagrees with normalized "
                f"lot-size screen {expected_screen}"
            )

    scenario_parcel = scenario.get("parcel") or {}
    if scenario_parcel.get("buildable_acres") is not None:
        failures.append("scenario still labels setback acreage as buildable")

    buildable_area = parcel.get("buildable_area") or {}
    if buildable_area.get("preliminary_buildable_acres") is not None:
        failures.append("buildable-area payload still labels setback acreage as buildable")

    acreage_difference = buildable_area.get("acreage_difference_percent")
    if (
        isinstance(acreage_difference, (int, float))
        and acreage_difference >= 5
        and buildable_area.get("acreage_consistency_status") != "review"
    ):
        failures.append("material acreage discrepancy was not flagged for review")

    land_use = parcel.get("current_land_use") or {}
    if land_use.get("mixed_land_use") and not land_use.get("land_use_breakdown"):
        failures.append("mixed land use is missing its breakdown")

    wetlands = parcel.get("wetlands") or {}
    if (
        wetlands.get("mapped_wetland") is True
        and wetlands.get("wetland_indicator") is not True
    ):
        failures.append("wetland is labeled mapped without a positive wetland indicator")

    terrain = parcel.get("terrain") or {}
    if terrain.get("status") != "found":
        warnings.append(f"terrain unavailable: {terrain.get('message')}")

    return failures, warnings


def _run_case(case: dict) -> dict:
    started = time.perf_counter()
    path = "/lookup-property/base" if case.get("expect_rejection") else "/lookup-property"

    try:
        result = _post(path, case["address"])
        elapsed = round(time.perf_counter() - started, 2)
    except (HTTPError, URLError, TimeoutError) as error:
        return {
            **case,
            "passed": False,
            "elapsed_seconds": round(time.perf_counter() - started, 2),
            "failures": [f"request failed: {error}"],
            "warnings": [],
        }

    parcels = result.get("parcels") or []

    if case.get("expect_rejection"):
        failures = [] if not parcels else [
            f"unsafe match returned: {parcels[0].get('address')}"
        ]
        warnings = []
    else:
        failures, warnings = _validate_success(case, result)

    parcel = parcels[0] if parcels else {}
    jurisdiction = parcel.get("jurisdiction") or result.get("jurisdiction") or {}

    return {
        **case,
        "passed": not failures,
        "elapsed_seconds": elapsed,
        "status": result.get("status"),
        "apn": parcel.get("apn"),
        "matched_address": parcel.get("address"),
        "jurisdiction": jurisdiction.get("name"),
        "zoning": (parcel.get("zoning") or {}).get("code"),
        "general_plan": (parcel.get("general_plan") or {}).get("designation"),
        "preliminary_units": (
            (parcel.get("feasibility_summary") or {}).get("preliminary_unit_estimate")
        ),
        "failures": failures,
        "warnings": warnings,
    }


def main() -> None:
    started = time.perf_counter()
    results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_run_case, case): case for case in CASES}

        for future in as_completed(futures):
            try:
                row = future.result()
            except Exception as error:
                case = futures[future]
                row = {
                    **case,
                    "passed": False,
                    "elapsed_seconds": 0,
                    "failures": [
                        f"validation runner error: {type(error).__name__}: {error}"
                    ],
                    "warnings": [],
                }
            results.append(row)
            state = "PASS" if row["passed"] else "FAIL"
            print(f"[{state}] {row['id']} ({row['elapsed_seconds']:.2f}s)")
            for failure in row["failures"]:
                print(f"  failure: {failure}")
            for warning in row["warnings"]:
                print(f"  warning: {warning}")

    order = {case["id"]: index for index, case in enumerate(CASES)}
    results.sort(key=lambda row: order[row["id"]])
    passed = sum(row["passed"] for row in results)

    report = {
        "generated_at_unix": time.time(),
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "passed": passed,
        "failed": len(results) - passed,
        "cases": results,
    }

    RESULT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(results)} cases passed")
    print(f"Saved {RESULT_PATH}")

    if passed != len(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
