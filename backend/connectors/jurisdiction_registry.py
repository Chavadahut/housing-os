"""
Housing OS jurisdiction registry.
 
This file is the single source of truth for all incorporated municipalities
in San Diego County plus unincorporated County territory.
 
Adding a new city connector should normally require:
1. implement the connector module
2. update that city's connector names/status here
3. add the connector function routing in services.py/progressive_lookup.py
 
Jurisdiction detection itself does not need to change.
"""
 
SAN_DIEGO_COUNTY_JURISDICTIONS = {
    "carlsbad": {
        "name": "City of Carlsbad",
        "municipal_names": {"CARLSBAD", "CITY OF CARLSBAD"},
        "zoning_connector": "city_of_carlsbad",
        "general_plan_connector": "city_of_carlsbad",
        "permit_connector": "city_of_carlsbad",
        "connector_status": "implemented",
    },
    "chula_vista": {
        "name": "City of Chula Vista",
        "municipal_names": {"CHULA VISTA", "CITY OF CHULA VISTA"},
        "zoning_connector": "city_of_chula_vista",
        "general_plan_connector": "city_of_chula_vista",
        "permit_connector": "city_of_chula_vista",
        "connector_status": "implemented",
    },
    "coronado": {
        "name": "City of Coronado",
        "municipal_names": {"CORONADO", "CITY OF CORONADO"},
        "zoning_connector": "city_of_coronado",
        "general_plan_connector": "city_of_coronado",
        "permit_connector": "city_of_coronado",
        "connector_status": "implemented_with_official_map_confirmation",
    },
    "del_mar": {
        "name": "City of Del Mar",
        "municipal_names": {"DEL MAR", "CITY OF DEL MAR"},
        "zoning_connector": "city_of_del_mar",
        "general_plan_connector": "city_of_del_mar",
        "permit_connector": "city_of_del_mar",
        "connector_status": "implemented_with_official_map_confirmation",
    },
    "el_cajon": {
        "name": "City of El Cajon",
        "municipal_names": {"EL CAJON", "CITY OF EL CAJON"},
        "zoning_connector": "city_of_el_cajon",
        "general_plan_connector": "city_of_el_cajon",
        "permit_connector": "city_of_el_cajon",
        "connector_status": "implemented",
    },
    "encinitas": {
        "name": "City of Encinitas",
        "municipal_names": {"ENCINITAS", "CITY OF ENCINITAS"},
        "zoning_connector": "city_of_encinitas",
        "general_plan_connector": "city_of_encinitas",
        "permit_connector": "city_of_encinitas",
        "connector_status": "implemented",
    },
    "escondido": {
        "name": "City of Escondido",
        "municipal_names": {"ESCONDIDO", "CITY OF ESCONDIDO"},
        "zoning_connector": "city_of_escondido",
        "general_plan_connector": "city_of_escondido",
        "permit_connector": "city_of_escondido",
        "connector_status": "implemented",
    },
    "imperial_beach": {
        "name": "City of Imperial Beach",
        "municipal_names": {
            "IMPERIAL BEACH",
            "CITY OF IMPERIAL BEACH",
        },
        "zoning_connector": "city_of_imperial_beach",
        "general_plan_connector": "city_of_imperial_beach",
        "permit_connector": "city_of_imperial_beach",
        "connector_status": "implemented",
    },
    "la_mesa": {
        "name": "City of La Mesa",
        "municipal_names": {"LA MESA", "CITY OF LA MESA"},
        "zoning_connector": "city_of_la_mesa",
        "general_plan_connector": "city_of_la_mesa",
        "permit_connector": "city_of_la_mesa",
        "connector_status": "implemented",
    },
    "lemon_grove": {
        "name": "City of Lemon Grove",
        "municipal_names": {
            "LEMON GROVE",
            "CITY OF LEMON GROVE",
        },
        "zoning_connector": "city_of_lemon_grove",
        "general_plan_connector": "city_of_lemon_grove",
        "permit_connector": "city_of_lemon_grove",
        "connector_status": "implemented",
    },
    "national_city": {
        "name": "National City",
        "municipal_names": {
            "NATIONAL CITY",
            "CITY OF NATIONAL CITY",
        },
        "zoning_connector": "city_of_national_city",
        "general_plan_connector": "city_of_national_city",
        "permit_connector": "city_of_national_city",
        "connector_status": "implemented",
    },
    "oceanside": {
        "name": "City of Oceanside",
        "municipal_names": {"OCEANSIDE", "CITY OF OCEANSIDE"},
        "zoning_connector": "city_of_oceanside",
        "general_plan_connector": "city_of_oceanside",
        "permit_connector": "city_of_oceanside",
        "connector_status": "implemented",
    },
    "poway": {
        "name": "City of Poway",
        "municipal_names": {"POWAY", "CITY OF POWAY"},
        "zoning_connector": "city_of_poway",
        "general_plan_connector": "city_of_poway",
        "permit_connector": "city_of_poway",
        "connector_status": "implemented",
    },
    "san_diego": {
        "name": "City of San Diego",
        "municipal_names": {
            "SAN DIEGO",
            "CITY OF SAN DIEGO",
        },
        "zoning_connector": "city_of_san_diego",
        "general_plan_connector": "city_of_san_diego",
        "permit_connector": "city_of_san_diego",
        "connector_status": "implemented",
    },
    "san_marcos": {
        "name": "City of San Marcos",
        "municipal_names": {
            "SAN MARCOS",
            "CITY OF SAN MARCOS",
        },
        "zoning_connector": "city_of_san_marcos",
        "general_plan_connector": "city_of_san_marcos",
        "permit_connector": "city_of_san_marcos",
        "connector_status": "implemented",
    },
    "santee": {
        "name": "City of Santee",
        "municipal_names": {"SANTEE", "CITY OF SANTEE"},
        "zoning_connector": "city_of_santee",
        "general_plan_connector": "city_of_santee",
        "permit_connector": "city_of_santee",
        "connector_status": "implemented",
    },
    "solana_beach": {
        "name": "City of Solana Beach",
        "municipal_names": {
            "SOLANA BEACH",
            "CITY OF SOLANA BEACH",
        },
        "zoning_connector": "city_of_solana_beach",
        "general_plan_connector": "city_of_solana_beach",
        "permit_connector": "city_of_solana_beach",
        "connector_status": "implemented",
    },
    "vista": {
        "name": "City of Vista",
        "municipal_names": {"VISTA", "CITY OF VISTA"},
        "zoning_connector": "city_of_vista",
        "general_plan_connector": "city_of_vista",
        "permit_connector": "city_of_vista",
        "connector_status": "implemented_with_official_map_confirmation",
    },
    "unincorporated": {
        "name": "Unincorporated San Diego County",
        "municipal_names": set(),
        "zoning_connector": "san_diego_county",
        "general_plan_connector": "san_diego_county",
        "permit_connector": "san_diego_county",
        "connector_status": "implemented",
    },
}
 
 
def _public_config(
    key: str,
    config: dict,
) -> dict:
    """
    Return only JSON-safe, API-facing jurisdiction metadata.
 
    municipal_names is intentionally excluded because it is an internal
    matching set and Python sets are not JSON serializable.
    """
    return {
        "key": key,
        "name": config["name"],
        "zoning_connector": config["zoning_connector"],
        "general_plan_connector": config["general_plan_connector"],
        "permit_connector": config["permit_connector"],
        "connector_status": config["connector_status"],
    }
 
 
def get_jurisdiction_config(
    key: str,
) -> dict | None:
    config = SAN_DIEGO_COUNTY_JURISDICTIONS.get(key)
 
    if not config:
        return None
 
    return _public_config(
        key,
        config,
    )
 
 
def match_municipal_name(
    name: str | None,
) -> dict | None:
    if not name:
        return None
 
    normalized = " ".join(
        str(name).upper().replace("_", " ").split()
    )
 
    for key, config in SAN_DIEGO_COUNTY_JURISDICTIONS.items():
        if key == "unincorporated":
            continue
 
        if normalized in config.get("municipal_names", set()):
            return _public_config(
                key,
                config,
            )
 
    return None
 
 
def jurisdiction_coverage() -> list[dict]:
    rows = []
 
    for key, config in SAN_DIEGO_COUNTY_JURISDICTIONS.items():
        rows.append(
            _public_config(
                key,
                config,
            )
        )
 
    return rows
