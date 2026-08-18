from connectors.san_diego_gis import (
    build_map_geometry,
    get_parcel_data,
)
from connectors.san_diego_assessor import get_lot_size_data
from connectors.san_diego_zoning import get_zoning_data
from connectors.san_diego_general_plan import get_san_diego_general_plan_data
from connectors.city_of_san_diego_permit_history import (
    get_san_diego_permit_history_data,
)
from connectors.san_diego_county_zoning import get_county_zoning_data
from connectors.san_diego_land_use import get_land_use_data
from connectors.san_diego_county_general_plan import (
    get_county_general_plan_data,
)
from connectors.la_mesa_planning import (
    get_la_mesa_zoning_data,
    get_la_mesa_general_plan_data,
)
from connectors.la_mesa_permits import (
    get_la_mesa_permit_history_data,
)
from connectors.fema_flood import get_flood_data
from connectors.san_diego_fire_hazard import get_fire_hazard_data
from connectors.usgs_terrain import get_terrain_data
from connectors.san_diego_habitat import get_habitat_data
from connectors.san_diego_wetlands import get_wetlands_data
from connectors.san_diego_utilities import get_utility_data
from connectors.san_diego_road_access import get_road_access_data
from connectors.san_diego_easements import (
    get_easement_screening_data,
)
from connectors.san_diego_permit_history import (
    get_permit_history_data,
)
from connectors.jurisdiction import determine_jurisdiction
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


SUPPORTED_SECTIONS = {
    "zoning",
    "general_plan",
    "current_land_use",
    "fire_hazard",
    "flood_hazard",
    "road_access",
    "terrain",
    "habitat",
    "wetlands",
    "utilities",
    "easements",
    "permit_history",
}


def _unsupported(section: str, jurisdiction: dict) -> dict:
    return {
        "status": "unsupported_jurisdiction",
        "source": None,
        "message": (
            f"{section.replace('_', ' ').title()} lookup for "
            f"{jurisdiction.get('name') or 'this jurisdiction'} "
            "has not been added yet."
        ),
    }


def lookup_property_base(address: str) -> dict:
    """
    Fastest useful first response:
    address -> parcel -> lot size -> basic parcel map.

    No zoning, FEMA, fire, road, environmental, utility,
    permit, or easement service can delay this response.
    """
    property_data = get_parcel_data(address)

    if not property_data.get("parcels"):
        return property_data

    jurisdiction = determine_jurisdiction(property_data)
    property_data["jurisdiction"] = jurisdiction

    for parcel in property_data["parcels"]:
        apn = parcel.get("apn")
        latitude = parcel.get("latitude")
        longitude = parcel.get("longitude")
        parcel_boundary = parcel.get("_parcel_boundary")

        parcel["lot_size"] = get_lot_size_data(apn=apn)

        parcel["map_geometry"] = build_map_geometry(
            parcel_boundary=parcel_boundary,
            latitude=latitude,
            longitude=longitude,
            road_access={},
            buildable_area={},
            terrain={},
        )

        parcel.pop("_parcel_boundary", None)

    property_data["status"] = "partial"
    property_data["message"] = (
        "Parcel and lot size loaded. Development datasets "
        "are loading independently."
    )

    return property_data


def lookup_property_section(
    address: str,
    section: str,
) -> dict:
    if section not in SUPPORTED_SECTIONS:
        return {
            "section": section,
            "status": "unsupported_section",
            "data": None,
            "message": (
                f"Unsupported progressive section: {section}"
            ),
        }

    property_data = get_parcel_data(address)

    if not property_data.get("parcels"):
        return {
            "section": section,
            "status": "property_not_found",
            "data": None,
            "message": property_data.get("message"),
        }

    jurisdiction = determine_jurisdiction(property_data)
    zoning_connector = jurisdiction.get("zoning_connector")

    # Current UI selects one parcel. Return one result per parcel so
    # multi-parcel addresses remain supported.
    results = []

    for parcel in property_data["parcels"]:
        apn = parcel.get("apn")
        latitude = parcel.get("latitude")
        longitude = parcel.get("longitude")
        parcel_address = parcel.get("address")
        parcel_boundary = parcel.get("_parcel_boundary")

        lot_size = get_lot_size_data(apn=apn)
        parcel_acres = lot_size.get("acreage")

        if section == "zoning":
            if zoning_connector == "city_of_san_diego":
                data = get_zoning_data(
                    latitude=latitude,
                    longitude=longitude,
                )
            elif zoning_connector == "city_of_la_mesa":
                data = get_la_mesa_zoning_data(
                    latitude=latitude,
                    longitude=longitude,
                )
            elif zoning_connector == "san_diego_county":
                data = get_county_zoning_data(
                    latitude=latitude,
                    longitude=longitude,
                )
            elif zoning_connector == "city_of_encinitas":
                data = get_encinitas_zoning_data(
                    latitude=latitude,
                    longitude=longitude,
                )
            elif zoning_connector == "city_of_carlsbad":
                data = get_carlsbad_zoning_data(
                    latitude=latitude,
                    longitude=longitude,
                )
            elif zoning_connector in {
                "city_of_chula_vista", "city_of_escondido",
                "city_of_oceanside", "city_of_poway", "city_of_lemon_grove", "city_of_santee",
                "city_of_coronado", "city_of_del_mar", "city_of_el_cajon", "city_of_imperial_beach",
                "city_of_national_city", "city_of_san_marcos", "city_of_solana_beach", "city_of_vista",
            }:
                data = get_configured_zoning_data(
                    zoning_connector.removeprefix("city_of_"), latitude, longitude, apn
                )
            else:
                data = _unsupported(section, jurisdiction)

        elif section == "general_plan":
            if zoning_connector == "city_of_san_diego":
                data = get_san_diego_general_plan_data(
                    latitude=latitude,
                    longitude=longitude,
                    parcel_acres=parcel_acres,
                )
            elif zoning_connector == "city_of_la_mesa":
                data = get_la_mesa_general_plan_data(
                    latitude=latitude,
                    longitude=longitude,
                    parcel_acres=parcel_acres,
                )
            elif zoning_connector == "san_diego_county":
                data = get_county_general_plan_data(
                    latitude=latitude,
                    longitude=longitude,
                    parcel_acres=parcel_acres,
                )
            elif zoning_connector == "city_of_encinitas":
                data = get_encinitas_general_plan_data(
                    latitude=latitude,
                    longitude=longitude,
                    parcel_acres=parcel_acres,
                )
            elif zoning_connector == "city_of_carlsbad":
                data = get_carlsbad_general_plan_data(
                    latitude=latitude,
                    longitude=longitude,
                    parcel_acres=parcel_acres,
                )
            elif zoning_connector in {
                "city_of_chula_vista", "city_of_escondido",
                "city_of_oceanside", "city_of_poway", "city_of_lemon_grove", "city_of_santee",
                "city_of_coronado", "city_of_del_mar", "city_of_el_cajon", "city_of_imperial_beach",
                "city_of_national_city", "city_of_san_marcos", "city_of_solana_beach", "city_of_vista",
            }:
                data = get_configured_general_plan_data(
                    zoning_connector.removeprefix("city_of_"),
                    latitude, longitude, parcel_acres,
                )
            else:
                data = _unsupported(section, jurisdiction)

        elif section == "current_land_use":
            data = get_land_use_data(
                latitude=latitude,
                longitude=longitude,
            )

        elif section == "fire_hazard":
            data = get_fire_hazard_data(
                latitude=latitude,
                longitude=longitude,
            )

        elif section == "flood_hazard":
            data = get_flood_data(
                latitude=latitude,
                longitude=longitude,
            )

        elif section == "road_access":
            data = get_road_access_data(
                latitude=latitude,
                longitude=longitude,
                parcel_boundary=parcel_boundary,
            )

        elif section == "terrain":
            data = get_terrain_data(
                latitude=latitude,
                longitude=longitude,
                parcel_boundary=parcel_boundary,
            )

        elif section == "habitat":
            data = get_habitat_data(
                latitude=latitude,
                longitude=longitude,
                parcel_boundary=parcel_boundary,
                parcel_acres=parcel_acres,
            )

        elif section == "wetlands":
            data = get_wetlands_data(
                latitude=latitude,
                longitude=longitude,
                parcel_boundary=parcel_boundary,
                parcel_acres=parcel_acres,
            )

        elif section == "utilities":
            data = get_utility_data(
                latitude=latitude,
                longitude=longitude,
                apn=apn,
            )

        elif section == "easements":
            data = get_easement_screening_data(
                latitude=latitude,
                longitude=longitude,
                parcel_boundary=parcel_boundary,
            )

        elif section == "permit_history":
            if zoning_connector == "city_of_san_diego":
                data = get_san_diego_permit_history_data(
                    apn=apn,
                    address=parcel_address,
                )
            elif zoning_connector == "city_of_la_mesa":
                data = get_la_mesa_permit_history_data(
                    apn=apn,
                    address=parcel_address,
                )
            elif zoning_connector == "san_diego_county":
                data = get_permit_history_data(apn=apn)
            elif zoning_connector == "city_of_encinitas":
                data = get_encinitas_permit_history_data(
                    apn=apn,
                    address=parcel.get("address"),
                )
            elif zoning_connector == "city_of_carlsbad":
                data = get_carlsbad_permit_history_data(
                    apn=apn,
                    address=parcel_address,
                )
            elif zoning_connector in {
                "city_of_chula_vista", "city_of_escondido",
                "city_of_oceanside", "city_of_poway", "city_of_lemon_grove", "city_of_santee",
                "city_of_coronado", "city_of_del_mar", "city_of_el_cajon", "city_of_imperial_beach",
                "city_of_national_city", "city_of_san_marcos", "city_of_solana_beach", "city_of_vista",
            }:
                data = get_configured_permit_history_data(
                    zoning_connector.removeprefix("city_of_"), apn, parcel_address
                )
            else:
                data = _unsupported(section, jurisdiction)

        else:
            data = _unsupported(section, jurisdiction)

        results.append({
            "apn": apn,
            "data": data,
        })

    return {
        "section": section,
        "status": "complete",
        "results": results,
    }
