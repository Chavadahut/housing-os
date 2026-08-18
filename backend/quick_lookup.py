from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from connectors.san_diego_gis import (
    build_map_geometry,
    get_parcel_data,
)
from connectors.san_diego_zoning import get_zoning_data
from connectors.san_diego_county_zoning import get_county_zoning_data
from connectors.san_diego_assessor import get_lot_size_data
from connectors.san_diego_land_use import get_land_use_data
from connectors.san_diego_county_general_plan import (
    get_county_general_plan_data,
)
from connectors.la_mesa_planning import (
    get_la_mesa_zoning_data,
    get_la_mesa_general_plan_data,
)
from connectors.fema_flood import get_flood_data
from connectors.san_diego_fire_hazard import get_fire_hazard_data
from connectors.san_diego_road_access import get_road_access_data
from connectors.jurisdiction import determine_jurisdiction
from buildable_area import get_buildable_area_data


MAX_QUICK_LOOKUP_WORKERS = 6


def unsupported_zoning_result(jurisdiction: dict) -> dict:
    jurisdiction_name = jurisdiction.get("name")

    return {
        "code": None,
        "use_regulation": None,
        "density": None,
        "minimum_lot_size": None,
        "building_type": None,
        "maximum_floor_area": None,
        "floor_area_ratio": None,
        "height": None,
        "coverage": None,
        "setback": None,
        "open_space": None,
        "animal_regulations": None,
        "special_regulations": None,
        "ordinance": None,
        "case_number": None,
        "implementation_date": None,
        "jurisdiction": jurisdiction_name,
        "status": "unsupported_jurisdiction",
        "source": None,
        "message": (
            f"Zoning lookup for {jurisdiction_name or 'this jurisdiction'} "
            "has not been added yet."
        ),
        "lookup_method": None,
        "search_distance_feet": None,
    }


def unsupported_general_plan_result(jurisdiction: dict) -> dict:
    return {
        "designation": None,
        "designation_code": None,
        "description": None,
        "raw_density": None,
        "raw_potential_units": None,
        "maximum_density": None,
        "gross_acres_per_unit": None,
        "estimated_maximum_units": None,
        "estimate_status": "not_available",
        "mixed_use": None,
        "mixed_use_name": None,
        "general_plan_code": None,
        "case_number": None,
        "adoption_date": None,
        "jurisdiction": jurisdiction.get("name"),
        "status": "unsupported_jurisdiction",
        "source": None,
        "message": (
            "General Plan lookup for this jurisdiction "
            "has not been added yet."
        ),
        "warning": None,
        "lookup_method": None,
        "search_distance_feet": None,
    }


def failed_lookup_result(lookup_name: str, error: Exception) -> dict:
    return {
        "status": "error",
        "source": None,
        "message": (
            f"The {lookup_name} quick lookup failed without stopping "
            f"the property map: {error}"
        ),
    }


def run_parallel_lookups(
    lookups: dict[str, Callable[[], dict]],
) -> dict[str, dict]:
    results = {}

    with ThreadPoolExecutor(
        max_workers=min(
            MAX_QUICK_LOOKUP_WORKERS,
            max(len(lookups), 1),
        )
    ) as executor:
        future_map = {
            executor.submit(lookup): lookup_name
            for lookup_name, lookup in lookups.items()
        }

        for future in as_completed(future_map):
            lookup_name = future_map[future]

            try:
                result = future.result()

                if isinstance(result, dict):
                    results[lookup_name] = result
                else:
                    results[lookup_name] = failed_lookup_result(
                        lookup_name,
                        TypeError(
                            "Connector returned a non-dictionary result."
                        ),
                    )
            except Exception as error:
                results[lookup_name] = failed_lookup_result(
                    lookup_name,
                    error,
                )

    return results


def lookup_property_quick(address: str):
    property_data = get_parcel_data(address)

    if not property_data.get("parcels"):
        return property_data

    jurisdiction = determine_jurisdiction(property_data)
    property_data["jurisdiction"] = jurisdiction

    for parcel in property_data["parcels"]:
        latitude = parcel["latitude"]
        longitude = parcel["longitude"]
        apn = parcel.get("apn")
        parcel_boundary = parcel.get("_parcel_boundary")

        lot_size = get_lot_size_data(apn=apn)
        parcel["lot_size"] = lot_size
        parcel_acres = lot_size.get("acreage")

        zoning_connector = jurisdiction.get("zoning_connector")

        lookups = {
            "current_land_use": lambda: get_land_use_data(
                latitude=latitude,
                longitude=longitude,
            ),
            "flood_hazard": lambda: get_flood_data(
                latitude=latitude,
                longitude=longitude,
            ),
            "fire_hazard": lambda: get_fire_hazard_data(
                latitude=latitude,
                longitude=longitude,
            ),
            "road_access": lambda: get_road_access_data(
                latitude=latitude,
                longitude=longitude,
                parcel_boundary=parcel_boundary,
            ),
        }

        if zoning_connector == "city_of_san_diego":
            lookups["zoning"] = lambda: get_zoning_data(
                latitude=latitude,
                longitude=longitude,
            )
            parcel["general_plan"] = unsupported_general_plan_result(
                jurisdiction
            )

        elif zoning_connector == "city_of_la_mesa":
            lookups["zoning"] = lambda: get_la_mesa_zoning_data(
                latitude=latitude,
                longitude=longitude,
            )
            lookups["general_plan"] = lambda: get_la_mesa_general_plan_data(
                latitude=latitude,
                longitude=longitude,
                parcel_acres=parcel_acres,
            )

        elif zoning_connector == "san_diego_county":
            lookups["zoning"] = lambda: get_county_zoning_data(
                latitude=latitude,
                longitude=longitude,
            )
            lookups["general_plan"] = lambda: get_county_general_plan_data(
                latitude=latitude,
                longitude=longitude,
                parcel_acres=parcel_acres,
            )

        else:
            parcel["zoning"] = unsupported_zoning_result(jurisdiction)
            parcel["general_plan"] = unsupported_general_plan_result(
                jurisdiction
            )

        parallel_results = run_parallel_lookups(lookups)

        for lookup_name, result in parallel_results.items():
            parcel[lookup_name] = result

        parcel["buildable_area"] = get_buildable_area_data(
            parcel_boundary=parcel_boundary,
            parcel_acres=parcel_acres,
            zoning=parcel.get("zoning") or {},
            habitat={},
            wetlands={},
            terrain={},
            road_access=parcel.get("road_access") or {},
        )

        parcel["map_geometry"] = build_map_geometry(
            parcel_boundary=parcel_boundary,
            latitude=latitude,
            longitude=longitude,
            road_access=parcel.get("road_access"),
            buildable_area=parcel.get("buildable_area"),
            terrain={},
        )

        parcel.pop("_parcel_boundary", None)

    property_data["status"] = "partial"
    property_data["message"] = (
        "Core development screening loaded. Terrain, habitat, wetlands, "
        "utilities, permits, easements, and final feasibility are loading "
        "separately."
    )

    return property_data