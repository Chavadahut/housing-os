import math

import requests


URL = (
    "https://gis-public.sandiegocounty.gov/arcgis/rest/services/"
    "HCD/HCD_Map/FeatureServer/0/query"
)

SQUARE_FEET_PER_ACRE = 43560


def empty_lot_size_result(
    status: str,
    message: str
) -> dict:

    return {
        "acreage": None,
        "square_feet": None,
        "status": status,
        "source": "County of San Diego Assessor Parcels",
        "message": message
    }


def clean_apn(
    apn: str | None
) -> str | None:

    if apn is None:
        return None

    digits = "".join(
        character
        for character in str(apn)
        if character.isdigit()
    )

    if len(digits) != 10:
        return None

    return digits


def polygon_area_square_feet(
    rings: list
) -> float | None:

    if not rings:
        return None

    total_signed_area = 0.0

    for ring in rings:

        if not isinstance(ring, list):
            continue

        points = []

        for point in ring:

            try:
                x = float(point[0])
                y = float(point[1])

            except (
                TypeError,
                ValueError,
                IndexError
            ):
                continue

            points.append(
                (
                    x,
                    y
                )
            )

        if len(points) < 3:
            continue

        if points[0] != points[-1]:
            points.append(
                points[0]
            )

        signed_area = 0.0

        for index in range(
            len(points) - 1
        ):

            x1, y1 = points[index]
            x2, y2 = points[index + 1]

            signed_area += (
                x1 * y2
                - x2 * y1
            )

        total_signed_area += (
            signed_area / 2
        )

    area = abs(
        total_signed_area
    )

    if area <= 0:
        return None

    return area


def get_lot_size_data(
    apn: str
) -> dict:

    normalized_apn = clean_apn(
        apn
    )

    if normalized_apn is None:

        return empty_lot_size_result(
            status="invalid_apn",
            message=(
                "A valid ten-digit APN was not available "
                "for lot-size lookup."
            )
        )

    params = {
        "where": (
            f"APN = '{normalized_apn}'"
        ),
        "outFields": "APN,ACREAGE",
        "returnGeometry": "true",
        "outSR": 2230,
        "geometryPrecision": 3,
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

            error_details = data[
                "error"
            ]

            message = error_details.get(
                "message",
                "The assessor parcel service returned an error."
            )

            details = error_details.get(
                "details",
                []
            )

            if details:

                message = (
                    f"{message} "
                    f"{' '.join(str(item) for item in details)}"
                )

            return empty_lot_size_result(
                status="error",
                message=message
            )

    except requests.Timeout:

        return empty_lot_size_result(
            status="timeout",
            message=(
                "The assessor parcel server took too long "
                "to respond. Please try again."
            )
        )

    except requests.RequestException as error:

        return empty_lot_size_result(
            status="error",
            message=str(error)
        )

    except ValueError:

        return empty_lot_size_result(
            status="error",
            message=(
                "The assessor parcel server returned "
                "an invalid response."
            )
        )

    features = data.get(
        "features",
        []
    )

    if not features:

        return empty_lot_size_result(
            status="not_found",
            message=(
                "No assessor parcel record was found "
                f"for APN {normalized_apn}."
            )
        )

    feature = features[0]

    attributes = feature.get(
        "attributes",
        {}
    )

    acreage = attributes.get(
        "ACREAGE"
    )

    if acreage is not None:

        try:

            acreage = float(
                acreage
            )

            if math.isfinite(
                acreage
            ) and acreage > 0:

                square_feet = round(
                    acreage
                    * SQUARE_FEET_PER_ACRE,
                    2
                )

                return {
                    "acreage": round(
                        acreage,
                        4
                    ),
                    "square_feet": square_feet,
                    "status": "found",
                    "source": (
                        "County of San Diego Assessor Parcels"
                    ),
                    "message": None
                }

        except (
            TypeError,
            ValueError
        ):
            pass

    # Some assessor parcel records exist but have a null ACREAGE field.
    # When that happens, calculate a preliminary parcel area from the
    # assessor polygon itself. The service geometry is requested in
    # EPSG:2230, whose units are US survey feet, so polygon area is
    # directly usable as square feet for this screening estimate.
    geometry = feature.get(
        "geometry",
        {}
    )

    rings = geometry.get(
        "rings",
        []
    )

    geometry_square_feet = (
        polygon_area_square_feet(
            rings
        )
    )

    if geometry_square_feet is None:

        return empty_lot_size_result(
            status="not_available",
            message=(
                "The assessor parcel record was found, "
                "but the ACREAGE field was empty and a "
                "usable parcel polygon was not available "
                "for a geometry-based lot-size estimate."
            )
        )

    geometry_acres = (
        geometry_square_feet
        / SQUARE_FEET_PER_ACRE
    )

    return {
        "acreage": round(
            geometry_acres,
            4
        ),
        "square_feet": round(
            geometry_square_feet,
            2
        ),
        "status": "found",
        "source": (
            "County of San Diego Assessor Parcels"
        ),
        "message": (
            "The assessor ACREAGE field was not available. "
            "Housing OS calculated this preliminary lot size "
            "from the mapped assessor parcel polygon in "
            "San Diego County State Plane coordinates. "
            "This geometry-based acreage should be treated "
            "as a screening estimate, not a surveyed or "
            "recorded legal acreage."
        )
    }