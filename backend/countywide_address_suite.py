"""Live countywide address and jurisdiction regression suite for Housing OS."""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_API_ROOT = "http://127.0.0.1:8000"
RESULT_PATH = Path(__file__).with_name("countywide_address_results.json")
MAX_WORKERS = 3

# Prefer civic facilities and previously verified parcels: these addresses are
# relatively stable and collectively exercise all 18 cities plus the County.
CASES = [
    ("carlsbad", "1200 Carlsbad Village Dr, Carlsbad, CA 92008"),
    ("chula_vista", "276 Fourth Ave, Chula Vista, CA 91910"),
    ("coronado", "1825 Strand Way, Coronado, CA 92118"),
    ("del_mar", "1050 Camino Del Mar, Del Mar, CA 92014"),
    ("el_cajon", "200 Civic Center Way, El Cajon, CA 92020"),
    ("encinitas", "505 S Vulcan Ave, Encinitas, CA 92024"),
    ("escondido", "201 N Broadway, Escondido, CA 92025"),
    ("imperial_beach", "700 Seacoast Dr, Imperial Beach, CA 91932"),
    ("la_mesa", "8060 La Mesa Blvd, La Mesa, CA 91942"),
    ("lemon_grove", "3232 Main St, Lemon Grove, CA 91945"),
    ("national_city", "1243 National City Blvd, National City, CA 91950"),
    ("oceanside", "300 N Coast Hwy, Oceanside, CA 92054"),
    ("poway", "13025 Danielson St, Poway, CA 92064"),
    ("san_diego", "202 C St, San Diego, CA 92101"),
    ("san_marcos", "1 Civic Center Dr, San Marcos, CA 92069"),
    ("santee", "10601 Magnolia Ave, Santee, CA 92071"),
    ("solana_beach", "120 Stevens Ave, Solana Beach, CA 92075"),
    ("vista", "200 Civic Center Dr, Vista, CA 92084"),
    ("unincorporated", "14351 Vista Panorama, Lakeside, CA 92040"),
]

OFFICIAL_MAP_CONFIRMATION = {"coronado", "del_mar", "vista"}


def post(api_root: str, path: str, payload: dict, timeout: int = 90) -> dict:
    request = Request(
        f"{api_root}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def run_case(api_root: str, jurisdiction_key: str, address: str) -> dict:
    started = time.perf_counter()
    failures: list[str] = []
    warnings: list[str] = []
    base = post(api_root, "/lookup-property/base", {"address": address})
    parcels = base.get("parcels") or []
    jurisdiction = base.get("jurisdiction") or {}

    if not parcels:
        failures.append("no parcel resolved")
    if jurisdiction.get("key") != jurisdiction_key:
        failures.append(
            f"routed to {jurisdiction.get('key')!r}, expected {jurisdiction_key!r}"
        )
    if parcels and not all(parcel.get("apn") for parcel in parcels):
        failures.append("one or more parcels are missing an APN")

    zoning_statuses: list[str] = []
    if parcels:
        zoning = post(
            api_root,
            "/lookup-property/section",
            {"address": address, "section": "zoning"},
        )
        for item in zoning.get("results") or []:
            data = item.get("data") or {}
            status = data.get("status")
            zoning_statuses.append(status)
            if jurisdiction_key in OFFICIAL_MAP_CONFIRMATION:
                if status != "manual_review_required":
                    failures.append(f"expected official-map confirmation, received {status}")
                if not data.get("zoning_map_url"):
                    failures.append("official zoning-map URL missing")
            elif status != "found":
                warnings.append(f"zoning status for {item.get('apn')}: {status}")

    return {
        "jurisdiction_key": jurisdiction_key,
        "address": address,
        "passed": not failures,
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "parcel_count": len(parcels),
        "apns": [parcel.get("apn") for parcel in parcels],
        "connector_status": jurisdiction.get("connector_status"),
        "zoning_statuses": zoning_statuses,
        "failures": failures,
        "warnings": warnings,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-root", default=DEFAULT_API_ROOT)
    args = parser.parse_args()
    started = time.perf_counter()
    results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(run_case, args.api_root, key, address): (key, address)
            for key, address in CASES
        }
        for future in as_completed(futures):
            key, address = futures[future]
            try:
                row = future.result()
            except (HTTPError, URLError, TimeoutError, ValueError) as error:
                row = {
                    "jurisdiction_key": key,
                    "address": address,
                    "passed": False,
                    "elapsed_seconds": 0,
                    "failures": [f"request failed: {type(error).__name__}: {error}"],
                    "warnings": [],
                }
            results.append(row)
            print(
                f"[{'PASS' if row['passed'] else 'FAIL'}] {key} "
                f"({row['elapsed_seconds']:.2f}s)"
            )
            for failure in row["failures"]:
                print(f"  failure: {failure}")
            for warning in row["warnings"]:
                print(f"  warning: {warning}")

    order = {key: index for index, (key, _) in enumerate(CASES)}
    results.sort(key=lambda row: order[row["jurisdiction_key"]])
    passed = sum(row["passed"] for row in results)
    report = {
        "generated_at_unix": time.time(),
        "api_root": args.api_root,
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "passed": passed,
        "failed": len(results) - passed,
        "cases": results,
    }
    RESULT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(results)} jurisdictions passed")
    print(f"Saved {RESULT_PATH}")
    if passed != len(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
