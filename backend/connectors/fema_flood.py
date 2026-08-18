import requests


URL = (
    "https://hazards.fema.gov/arcgis/rest/services/"
    "public/NFHL/MapServer/28/query"
)


def clean_fema_value(value):

    if value in [-9999, -9999.0, "-9999", ""]:
        return None

    return value


def empty_flood_result(
    status: str,
    message: str
) -> dict:

    return {
        "zone": None,
        "zone_subtype": None,
        "special_flood_hazard_area": None,
        "risk_level": None,
        "annual_chance": None,
        "base_flood_elevation": None,
        "depth": None,
        "length_unit": None,
        "development_warning": None,
        "status": status,
        "source": "FEMA National Flood Hazard Layer",
        "message": message,
        "lookup_method": None
    }


def interpret_flood_zone(
    zone: str | None,
    zone_subtype: str | None,
    sfha_value: str | None
) -> dict:

    normalized_zone = (
        zone.strip().upper()
        if isinstance(zone, str)
        else None
    )

    normalized_subtype = (
        zone_subtype.strip().upper()
        if isinstance(zone_subtype, str)
        else None
    )

    is_sfha = (
        sfha_value.strip().upper() == "T"
        if isinstance(sfha_value, str)
        else None
    )

    risk_level = "unknown"
    annual_chance = None

    warning = (
        "Confirm flood requirements with FEMA and the local "
        "floodplain administrator before relying on this result."
    )

    one_percent_zones = {
        "A",
        "AE",
        "A1-30",
        "AH",
        "AO",
        "AR",
        "A99",
        "V",
        "VE",
        "V1-30"
    }

    if normalized_zone in one_percent_zones:

        risk_level = "high"
        annual_chance = "1% annual chance or greater"

        warning = (
            "The property point appears within a Special Flood "
            "Hazard Area. Floodplain development requirements, "
            "elevation standards, insurance, or additional review "
            "may apply."
        )

    elif normalized_zone == "X":

        if (
            normalized_subtype
            and (
                "0.2 PCT" in normalized_subtype
                or "0.2 PERCENT" in normalized_subtype
            )
        ):

            risk_level = "moderate"
            annual_chance = "0.2% annual chance"

            warning = (
                "The property point appears within a moderate "
                "flood-hazard area. Flood risk is lower than the "
                "1% annual-chance floodplain but is not zero."
            )

        elif (
            normalized_subtype
            and "FUTURE CONDITIONS" in normalized_subtype
        ):

            risk_level = "future_conditions"
            annual_chance = (
                "Future-condition 1% annual chance"
            )

            warning = (
                "The property point appears within a future-condition "
                "flood-hazard area. Additional review is recommended."
            )

        else:

            risk_level = "minimal"
            annual_chance = (
                "Outside mapped 1% annual-chance floodplain"
            )

            warning = (
                "The property point appears outside the mapped "
                "Special Flood Hazard Area. This does not mean the "
                "property has no flood risk."
            )

    elif normalized_zone == "D":

        risk_level = "undetermined"

        warning = (
            "Flood risk has not been fully determined for this "
            "location. Additional investigation is recommended."
        )

    if (
        normalized_subtype
        and "FLOODWAY" in normalized_subtype
    ):

        risk_level = "regulatory_floodway"

        warning = (
            "The property point appears within a regulatory floodway. "
            "Development may be heavily restricted and detailed "
            "hydraulic review may be required."
        )

    return {
        "special_flood_hazard_area": is_sfha,
        "risk_level": risk_level,
        "annual_chance": annual_chance,
        "development_warning": warning
    }


def get_flood_data(
    latitude: float,
    longitude: float
) -> dict:

    params = {
        "where": "1=1",
        "geometry": f"{longitude},{latitude}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": (
            "FLD_ZONE,ZONE_SUBTY,SFHA_TF,"
            "STATIC_BFE,DEPTH,LEN_UNIT"
        ),
        "returnGeometry": "false",
        "f": "json"
    }

    try:

        response = requests.get(
            URL,
            params=params,
            timeout=30
        )

        response.raise_for_status()

        data = response.json()

        if "error" in data:

            error_details = data["error"]

            message = error_details.get(
                "message",
                "The FEMA flood service returned an error."
            )

            details = error_details.get("details", [])

            if details:
                message = f"{message} {' '.join(details)}"

            return empty_flood_result(
                status="error",
                message=message
            )

    except requests.Timeout:

        return empty_flood_result(
            status="timeout",
            message=(
                "The FEMA flood server took too long "
                "to respond. Please try again."
            )
        )

    except requests.RequestException as error:

        return empty_flood_result(
            status="error",
            message=str(error)
        )

    except ValueError:

        return empty_flood_result(
            status="error",
            message=(
                "The FEMA flood server returned "
                "an invalid response."
            )
        )

    features = data.get("features", [])

    if not features:

        return empty_flood_result(
            status="not_found",
            message=(
                "No FEMA flood-zone polygon was found at "
                "the parcel lookup point. This does not prove "
                "that the entire parcel is free of flood risk."
            )
        )

    attributes = features[0].get(
        "attributes",
        {}
    )

    zone = attributes.get("FLD_ZONE")
    zone_subtype = attributes.get("ZONE_SUBTY")
    sfha_value = attributes.get("SFHA_TF")

    interpretation = interpret_flood_zone(
        zone=zone,
        zone_subtype=zone_subtype,
        sfha_value=sfha_value
    )

    return {
        "zone": zone,
        "zone_subtype": zone_subtype,
        "special_flood_hazard_area": interpretation[
            "special_flood_hazard_area"
        ],
        "risk_level": interpretation[
            "risk_level"
        ],
        "annual_chance": interpretation[
            "annual_chance"
        ],
        "base_flood_elevation": clean_fema_value(
            attributes.get("STATIC_BFE")
        ),
        "depth": clean_fema_value(
            attributes.get("DEPTH")
        ),
        "length_unit": clean_fema_value(
            attributes.get("LEN_UNIT")
        ),
        "development_warning": interpretation[
            "development_warning"
        ],
        "status": "found",
        "source": "FEMA National Flood Hazard Layer",
        "message": None,
        "lookup_method": "exact_point"
    }