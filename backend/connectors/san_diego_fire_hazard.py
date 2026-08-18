import requests


URL = (
    "https://gis-public.sandiegocounty.gov/arcgis/rest/services/"
    "hosted/OES_KnowYourHazards_Wildfire_1/FeatureServer/0/query"
)


def empty_fire_hazard_result(
    status: str,
    message: str
) -> dict:

    return {
        "hazard_class": None,
        "hazard_code": None,
        "description": None,
        "risk_level": None,
        "development_warning": None,
        "dataset_note": (
            "This is a preliminary point-based screening result. "
            "Confirm current requirements with the applicable fire "
            "authority and building department."
        ),
        "status": status,
        "source": (
            "San Diego County OES and CAL FIRE "
            "Fire Hazard Severity Zones"
        ),
        "message": message,
        "lookup_method": None
    }


def interpret_fire_hazard(
    hazard_class: str | None
) -> dict:

    normalized_class = (
        hazard_class.strip().upper()
        if isinstance(hazard_class, str)
        else None
    )

    if normalized_class == "VERY HIGH":
        return {
            "risk_level": "very_high",
            "development_warning": (
                "The property point appears within a Very High "
                "Fire Hazard Severity Zone. Wildland-urban interface "
                "building standards, defensible-space requirements, "
                "access standards, vegetation management, and fire "
                "agency review may apply."
            )
        }

    if normalized_class == "HIGH":
        return {
            "risk_level": "high",
            "development_warning": (
                "The property point appears within a High Fire Hazard "
                "Severity Zone. Additional building, access, vegetation, "
                "and fire-protection requirements may apply."
            )
        }

    if normalized_class == "MODERATE":
        return {
            "risk_level": "moderate",
            "development_warning": (
                "The property point appears within a Moderate Fire "
                "Hazard Severity Zone. Fire-safety and vegetation "
                "requirements may still affect development."
            )
        }

    if normalized_class == "NO DESIGNATION":
        return {
            "risk_level": "not_designated",
            "development_warning": (
                "The property point is not designated within the mapped "
                "Moderate, High, or Very High categories in this dataset. "
                "This does not mean the property has no wildfire risk."
            )
        }

    return {
        "risk_level": "unknown",
        "development_warning": (
            "Housing OS could not interpret the mapped fire-hazard "
            "classification. Confirm the result with the local fire "
            "authority."
        )
    }


def get_fire_hazard_data(
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
            "fhsz,fhsz_description,haz_class"
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
                "The fire-hazard service returned an error."
            )

            details = error_details.get("details", [])

            if details:
                message = f"{message} {' '.join(details)}"

            return empty_fire_hazard_result(
                status="error",
                message=message
            )

    except requests.Timeout:
        return empty_fire_hazard_result(
            status="timeout",
            message=(
                "The fire-hazard server took too long "
                "to respond. Please try again."
            )
        )

    except requests.RequestException as error:
        return empty_fire_hazard_result(
            status="error",
            message=str(error)
        )

    except ValueError:
        return empty_fire_hazard_result(
            status="error",
            message=(
                "The fire-hazard server returned "
                "an invalid response."
            )
        )

    features = data.get("features", [])

    if not features:
        return empty_fire_hazard_result(
            status="not_found",
            message=(
                "No fire-hazard polygon was found at the parcel "
                "lookup point. This does not prove that the entire "
                "parcel is outside a mapped fire-hazard zone."
            )
        )

    attributes = features[0].get(
        "attributes",
        {}
    )

    hazard_class = attributes.get("haz_class")

    interpretation = interpret_fire_hazard(
        hazard_class=hazard_class
    )

    return {
        "hazard_class": hazard_class,
        "hazard_code": attributes.get("fhsz"),
        "description": attributes.get(
            "fhsz_description"
        ),
        "risk_level": interpretation[
            "risk_level"
        ],
        "development_warning": interpretation[
            "development_warning"
        ],
        "dataset_note": (
            "This is a preliminary point-based screening result. "
            "The County dataset combines adopted State Responsibility "
            "Area mapping with interim Local Responsibility Area data. "
            "Confirm current requirements with the applicable fire "
            "authority and building department."
        ),
        "status": "found",
        "source": (
            "San Diego County OES and CAL FIRE "
            "Fire Hazard Severity Zones"
        ),
        "message": None,
        "lookup_method": "exact_point"
    }