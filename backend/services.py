from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed
)
from typing import Callable
 
from shapely.geometry import Polygon
 
from connectors.san_diego_gis import (
    build_map_geometry,
    get_parcel_data
)
from connectors.san_diego_zoning import get_zoning_data
from connectors.san_diego_general_plan import get_san_diego_general_plan_data
from connectors.city_of_san_diego_permit_history import get_san_diego_permit_history_data
from connectors.san_diego_county_zoning import (
    get_county_zoning_data
)
from connectors.san_diego_assessor import (
    get_lot_size_data
)
from connectors.san_diego_land_use import (
    get_land_use_data
)
from connectors.san_diego_county_general_plan import (
    get_county_general_plan_data
)
from connectors.la_mesa_planning import (
    get_la_mesa_zoning_data,
    get_la_mesa_general_plan_data
)
from connectors.la_mesa_permits import (
    get_la_mesa_permit_history_data
)
from connectors.fema_flood import get_flood_data
from connectors.san_diego_fire_hazard import (
    get_fire_hazard_data
)
from connectors.usgs_terrain import (
    get_terrain_data
)
from connectors.san_diego_habitat import (
    get_habitat_data
)
from connectors.san_diego_wetlands import (
    get_wetlands_data
)
from connectors.san_diego_utilities import (
    get_utility_data
)
from connectors.san_diego_road_access import (
    get_road_access_data
)
from connectors.san_diego_easements import (
    get_easement_screening_data
)
from connectors.san_diego_permit_history import (
    get_permit_history_data
)
from connectors.jurisdiction import (
    determine_jurisdiction
)
from buildable_area import (
    SQUARE_FEET_PER_ACRE,
    get_buildable_area_data,
    polygon_area_and_perimeter,
)
from connectors.encinitas_planning import (
    get_encinitas_general_plan_data,
    get_encinitas_zoning_data,
)
from connectors.encinitas_permits import (
    get_encinitas_permit_history_data,
)
from connectors.carlsbad_planning import (
    get_carlsbad_general_plan_data,
    get_carlsbad_zoning_data,
)
from connectors.carlsbad_permits import get_carlsbad_permit_history_data
from connectors.configured_municipal import (
    get_configured_general_plan_data,
    get_configured_permit_history_data,
    get_configured_zoning_data,
)
from feasibility import build_feasibility_summary
from development_scenario import build_development_scenario
from development_pathway import build_development_pathway
 
 
MAX_LOOKUP_WORKERS = 10
 
 
 
def get_parcel_analysis_point(
    parcel_boundary: dict | None,
    fallback_latitude: float,
    fallback_longitude: float
) -> tuple[float, float]:
    """
    Return a point safely inside the selected parcel polygon.
 
    Parcel lookup coordinates can fall on a street, driveway, or address
    point outside the tax parcel. Point-based zoning and land-use lookups
    therefore use a representative point inside the parcel boundary.
 
    The parcel boundary returned by Housing OS already uses longitude and
    latitude coordinates. No additional coordinate transformation is needed.
    If a valid interior point cannot be calculated, Housing OS falls back to
    the original parcel lookup coordinates.
    """
 
    if not isinstance(
        parcel_boundary,
        dict
    ):
        return (
            fallback_latitude,
            fallback_longitude
        )
 
    geometry = parcel_boundary.get(
        "geometry"
    )
 
    if isinstance(
        geometry,
        dict
    ):
        boundary_geometry = geometry
    else:
        boundary_geometry = parcel_boundary
 
    rings = boundary_geometry.get(
        "rings"
    )
 
    if not rings:
        return (
            fallback_latitude,
            fallback_longitude
        )
 
    polygons = []
 
    for ring in rings:
 
        try:
 
            polygon = Polygon(
                ring
            )
 
            if not polygon.is_valid:
 
                polygon = polygon.buffer(
                    0
                )
 
            if (
                polygon.is_empty
                or polygon.area <= 0
            ):
                continue
 
            polygons.append(
                polygon
            )
 
        except Exception:
 
            continue
 
    if not polygons:
        return (
            fallback_latitude,
            fallback_longitude
        )
 
    largest_polygon = max(
        polygons,
        key=lambda polygon: polygon.area
    )
 
    try:
 
        analysis_point = (
            largest_polygon.representative_point()
        )
 
        longitude = float(
            analysis_point.x
        )
 
        latitude = float(
            analysis_point.y
        )
 
        print(
            "[Housing OS analysis] Using parcel-interior "
            f"analysis point {latitude:.8f}, "
            f"{longitude:.8f}."
        )
 
        return (
            latitude,
            longitude
        )
 
    except Exception as error:
 
        print(
            "[Housing OS analysis] Could not calculate "
            "parcel-interior analysis point; using the "
            f"original lookup point. Error: {error}"
        )
 
        return (
            fallback_latitude,
            fallback_longitude
        )
 
def unsupported_zoning_result(
    jurisdiction: dict
) -> dict:
 
    jurisdiction_name = jurisdiction.get(
        "name"
    )
 
    if jurisdiction_name:
 
        message = (
            f"Zoning lookup for {jurisdiction_name} "
            "has not been added yet."
        )
 
    else:
 
        message = (
            "Housing OS could not determine which zoning "
            "jurisdiction controls this property."
        )
 
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
        "message": message,
        "lookup_method": None,
        "search_distance_feet": None
    }
 
 
def unsupported_general_plan_result(
    jurisdiction: dict
) -> dict:
 
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
        "search_distance_feet": None
    }
 
 
def unsupported_permit_history_result(
    jurisdiction: dict
) -> dict:
 
    jurisdiction_name = jurisdiction.get(
        "name"
    )
 
    return {
        "discretionary_application_found": None,
        "discretionary_application_count": 0,
        "discretionary_applications": [],
        "building_permit_history_checked": False,
        "building_permit_records": [],
        "code_compliance_history_checked": False,
        "code_compliance_records": [],
        "permit_history_level": (
            "unsupported_jurisdiction"
        ),
        "constraint_level": "unknown",
        "development_warning": (
            "Automated permit-history screening has not "
            "been added for this jurisdiction."
        ),
        "manual_research_required": True,
        "citizen_access_url": None,
        "public_records_url": None,
        "status": "unsupported_jurisdiction",
        "source": None,
        "message": (
            f"Permit-history screening for "
            f"{jurisdiction_name or 'this jurisdiction'} "
            "has not been added yet."
        ),
        "analysis_scope": (
            "preliminary_public_record_screening"
        )
    }
 
 
def failed_lookup_result(
    lookup_name: str,
    error: Exception
) -> dict:
 
    return {
        "status": "error",
        "source": None,
        "message": (
            f"The {lookup_name} lookup failed without "
            f"stopping the remaining property analysis: "
            f"{error}"
        )
    }
 
 
def run_parallel_lookups(
    lookups: dict[str, Callable[[], dict]]
) -> dict[str, dict]:
 
    results = {}
 
    with ThreadPoolExecutor(
        max_workers=min(
            MAX_LOOKUP_WORKERS,
            max(
                len(lookups),
                1
            )
        )
    ) as executor:
 
        future_map = {
            executor.submit(
                lookup
            ): lookup_name
            for lookup_name, lookup in lookups.items()
        }
 
        for future in as_completed(
            future_map
        ):
 
            lookup_name = future_map[
                future
            ]
 
            try:
 
                result = future.result()
 
                if isinstance(
                    result,
                    dict
                ):
 
                    results[
                        lookup_name
                    ] = result
 
                else:
 
                    results[
                        lookup_name
                    ] = failed_lookup_result(
                        lookup_name=lookup_name,
                        error=TypeError(
                            "Connector returned a non-dictionary result."
                        )
                    )
 
            except Exception as error:
 
                results[
                    lookup_name
                ] = failed_lookup_result(
                    lookup_name=lookup_name,
                    error=error
                )
 
    return results
 
 
def lookup_property(
    address: str
):
 
    property_data = get_parcel_data(
        address
    )
 
    if not property_data.get(
        "parcels"
    ):
        return property_data
 
    jurisdiction = determine_jurisdiction(
        property_data
    )
 
    property_data[
        "jurisdiction"
    ] = jurisdiction
 
    for parcel in property_data["parcels"]:
 
        latitude = parcel["latitude"]
        longitude = parcel["longitude"]
        apn = parcel.get("apn")
        parcel_address = parcel.get("address")
 
        parcel_boundary = parcel.get(
            "_parcel_boundary"
        )
 
        (
            analysis_latitude,
            analysis_longitude
        ) = get_parcel_analysis_point(
            parcel_boundary=parcel_boundary,
            fallback_latitude=latitude,
            fallback_longitude=longitude
        )
 
        lot_size = get_lot_size_data(
            apn=apn
        )

        if not lot_size.get("acreage") and parcel_boundary:
            geometry_square_feet, _ = polygon_area_and_perimeter(
                parcel_boundary.get("rings") or []
            )

            if geometry_square_feet and geometry_square_feet > 0:
                geometry_acres = geometry_square_feet / SQUARE_FEET_PER_ACRE
                original_message = lot_size.get("message")
                lot_size = {
                    "acreage": round(geometry_acres, 4),
                    "square_feet": round(geometry_square_feet, 2),
                    "status": "geometry_estimate",
                    "source": (
                        "County of San Diego Assessor parcel geometry"
                    ),
                    "message": (
                        "The assessor acreage lookup was unavailable. "
                        "Housing OS calculated this preliminary lot size "
                        "from the mapped assessor parcel polygon. It is "
                        "not a surveyed or recorded legal acreage."
                        + (
                            f" Original lookup message: {original_message}"
                            if original_message
                            else ""
                        )
                    ),
                }
 
        parcel["lot_size"] = lot_size
 
        parcel_acres = lot_size.get(
            "acreage"
        )
 
        zoning_connector = jurisdiction.get(
            "zoning_connector"
        )
 
        lookups = {
            "current_land_use": lambda: (
                get_land_use_data(
                    latitude=latitude,
                    longitude=longitude,
                    parcel_boundary=parcel_boundary,
                    parcel_acres=parcel_acres
                )
            ),
            "flood_hazard": lambda: (
                get_flood_data(
                    latitude=analysis_latitude,
                    longitude=analysis_longitude
                )
            ),
            "fire_hazard": lambda: (
                get_fire_hazard_data(
                    latitude=analysis_latitude,
                    longitude=analysis_longitude
                )
            ),
            "terrain": lambda: (
                get_terrain_data(
                    latitude=analysis_latitude,
                    longitude=analysis_longitude,
                    parcel_boundary=parcel_boundary
                )
            ),
            "habitat": lambda: (
                get_habitat_data(
                    latitude=analysis_latitude,
                    longitude=analysis_longitude,
                    parcel_boundary=parcel_boundary,
                    parcel_acres=parcel_acres
                )
            ),
            "wetlands": lambda: (
                get_wetlands_data(
                    latitude=analysis_latitude,
                    longitude=analysis_longitude,
                    parcel_boundary=parcel_boundary,
                    parcel_acres=parcel_acres
                )
            ),
            "utilities": lambda: (
                get_utility_data(
                    latitude=analysis_latitude,
                    longitude=analysis_longitude,
                    apn=apn
                )
            ),
            "road_access": lambda: (
                get_road_access_data(
                    latitude=analysis_latitude,
                    longitude=analysis_longitude,
                    parcel_boundary=parcel_boundary
                )
            ),
            "easements": lambda: (
                get_easement_screening_data(
                    latitude=analysis_latitude,
                    longitude=analysis_longitude,
                    parcel_boundary=parcel_boundary
                )
            )
        }
 
        if zoning_connector == "city_of_san_diego":
 
            lookups["zoning"] = lambda: (
                get_zoning_data(
                    latitude=analysis_latitude,
                    longitude=analysis_longitude
                )
            )
 
            lookups["general_plan"] = lambda: (
                get_san_diego_general_plan_data(
                    latitude=analysis_latitude,
                    longitude=analysis_longitude,
                    parcel_acres=parcel_acres
                )
            )
 
            lookups["permit_history"] = lambda: (
                get_san_diego_permit_history_data(
                    apn=apn,
                    address=parcel_address
                )
            )
 
        elif zoning_connector == "city_of_la_mesa":
 
            lookups["zoning"] = lambda: (
                get_la_mesa_zoning_data(
                    latitude=analysis_latitude,
                    longitude=analysis_longitude
                )
            )
 
            lookups["general_plan"] = lambda: (
                get_la_mesa_general_plan_data(
                    latitude=analysis_latitude,
                    longitude=analysis_longitude,
                    parcel_acres=parcel_acres
                )
            )
 
            lookups["permit_history"] = lambda: (
                get_la_mesa_permit_history_data(
                    apn=apn,
                    address=parcel_address
                )
            )
 
        elif zoning_connector == "san_diego_county":
 
            lookups["zoning"] = lambda: (
                get_county_zoning_data(
                    latitude=analysis_latitude,
                    longitude=analysis_longitude
                )
            )
 
            lookups["general_plan"] = lambda: (
                get_county_general_plan_data(
                    latitude=analysis_latitude,
                    longitude=analysis_longitude,
                    parcel_acres=parcel_acres
                )
            )
 
            lookups["permit_history"] = lambda: (
                get_permit_history_data(
                    apn=apn
                )
            )

        elif zoning_connector == "city_of_encinitas":

            lookups["zoning"] = lambda: (
                get_encinitas_zoning_data(
                    latitude=analysis_latitude,
                    longitude=analysis_longitude
                )
            )

            lookups["general_plan"] = lambda: (
                get_encinitas_general_plan_data(
                    latitude=analysis_latitude,
                    longitude=analysis_longitude,
                    parcel_acres=parcel_acres
                )
            )

            lookups["permit_history"] = lambda: (
                get_encinitas_permit_history_data(
                    apn=apn,
                    address=parcel_address
                )
            )

        elif zoning_connector == "city_of_carlsbad":
            lookups["zoning"] = lambda: get_carlsbad_zoning_data(
                latitude=analysis_latitude, longitude=analysis_longitude
            )
            lookups["general_plan"] = lambda: get_carlsbad_general_plan_data(
                latitude=analysis_latitude,
                longitude=analysis_longitude,
                parcel_acres=parcel_acres,
            )
            lookups["permit_history"] = lambda: get_carlsbad_permit_history_data(
                apn=apn, address=parcel_address
            )

        elif zoning_connector in {
            "city_of_chula_vista",
            "city_of_escondido",
            "city_of_oceanside",
            "city_of_poway",
            "city_of_lemon_grove",
            "city_of_santee",
            "city_of_coronado",
            "city_of_del_mar",
            "city_of_el_cajon",
            "city_of_imperial_beach",
            "city_of_national_city",
            "city_of_san_marcos",
            "city_of_solana_beach",
            "city_of_vista",
        }:
            city_key = zoning_connector.removeprefix("city_of_")
            lookups["zoning"] = lambda city_key=city_key: get_configured_zoning_data(
                city_key, analysis_latitude, analysis_longitude, apn
            )
            lookups["general_plan"] = lambda city_key=city_key: get_configured_general_plan_data(
                city_key, analysis_latitude, analysis_longitude, parcel_acres
            )
            lookups["permit_history"] = lambda city_key=city_key: get_configured_permit_history_data(
                city_key, apn, parcel_address
            )
 
        else:
 
            parcel["zoning"] = (
                unsupported_zoning_result(
                    jurisdiction
                )
            )
 
            parcel["general_plan"] = (
                unsupported_general_plan_result(
                    jurisdiction
                )
            )
 
            parcel["permit_history"] = (
                unsupported_permit_history_result(
                    jurisdiction
                )
            )
 
        parallel_results = run_parallel_lookups(
            lookups=lookups
        )
 
        for lookup_name, result in parallel_results.items():
 
            parcel[
                lookup_name
            ] = result
 
        parcel["buildable_area"] = (
            get_buildable_area_data(
                parcel_boundary=parcel_boundary,
                parcel_acres=parcel_acres,
                zoning=parcel.get("zoning") or {},
                habitat=parcel.get("habitat") or {},
                wetlands=parcel.get("wetlands") or {},
                terrain=parcel.get("terrain") or {},
                road_access=parcel.get("road_access") or {}
            )
        )
 
        parcel["map_geometry"] = build_map_geometry(
            parcel_boundary=parcel_boundary,
            latitude=analysis_latitude,
            longitude=analysis_longitude,
            road_access=parcel.get(
                "road_access"
            ),
            buildable_area=parcel.get(
                "buildable_area"
            ),
            terrain=parcel.get(
                "terrain"
            )
        )
 
        parcel["feasibility_summary"] = (
            build_feasibility_summary(
                parcel=parcel
            )
        )
 
        parcel["development_scenario"] = (
            build_development_scenario(
                parcel=parcel
            )
        )

        parcel["development_pathway"] = build_development_pathway(parcel)
 
        parcel.pop(
            "_parcel_boundary",
            None
        )
 
    return property_data
