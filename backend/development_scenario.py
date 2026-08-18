from __future__ import annotations

import math
import re
from typing import Any


SQFT_PER_ACRE = 43560.0


def _number(value: Any) -> float | None:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))

    if not match:
        return None

    try:
        return float(match.group())
    except ValueError:
        return None


def _minimum_lot_size_square_feet(value: Any) -> float | None:
    """Normalize common zoning lot-size values to square feet."""
    number = _number(value)

    if number is None:
        return None

    text = str(value).strip().upper().replace(" ", "")

    if re.search(r"(?:AC|ACRE|ACRES)$", text):
        return number * SQFT_PER_ACRE

    if re.search(r"(?:SF|SQFT|FT2|FT²)$", text):
        return number

    # County zoning feeds sometimes return a bare numeric value. Preserve
    # the historical square-foot interpretation only for those values.
    return number


def _round(value: float | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _constraint_value(value: Any, default: str = "unknown") -> str:
    if value is None:
        return default

    text = str(value).strip().lower()

    if not text:
        return default

    return text


def _is_residential(zoning: dict, land_use: dict) -> bool:
    zoning_text = " ".join(
        str(zoning.get(key) or "")
        for key in ("code", "use_regulation")
    ).lower()

    land_use_text = " ".join(
        str(land_use.get(key) or "")
        for key in ("category", "description")
    ).lower()

    residential_terms = (
        "residential",
        "single family",
        "single-family",
        "dwelling"
    )

    return any(
        term in zoning_text or term in land_use_text
        for term in residential_terms
    )


def _estimate_zoning_units(
    lot_square_feet: float | None,
    minimum_lot_size_square_feet: float | None
) -> int | None:

    if (
        lot_square_feet is None
        or minimum_lot_size_square_feet is None
        or minimum_lot_size_square_feet <= 0
    ):
        return None

    return max(
        1,
        math.floor(
            lot_square_feet
            / minimum_lot_size_square_feet
        )
    )


def _preliminary_unit_estimate(
    general_plan_units: int | None,
    zoning_units: int | None,
    residential: bool
) -> int | None:

    candidates = [
        value
        for value in (
            general_plan_units,
            zoning_units
        )
        if isinstance(value, int)
        and value >= 0
    ]

    if candidates:
        return min(candidates)

    if residential:
        return 1

    return None


def _lot_split_potential(
    lot_square_feet: float | None,
    minimum_lot_size_square_feet: float | None
) -> str:

    if (
        lot_square_feet is None
        or minimum_lot_size_square_feet is None
        or minimum_lot_size_square_feet <= 0
    ):
        return "requires_review"

    if (
        lot_square_feet
        >= minimum_lot_size_square_feet * 2
    ):
        return "requires_review"

    return "unlikely_from_minimum_lot_size_screen"


def _access_constraint(road_access: dict) -> str:

    if road_access.get(
        "legal_access_confirmed"
    ) is True:
        return "low"

    level = _constraint_value(
        road_access.get(
            "constraint_level"
        )
    )

    if level != "unknown":
        return level

    if road_access.get(
        "frontage_edge_found"
    ):
        return "review"

    return "unknown"


def _easement_constraint(easements: dict) -> str:

    if easements.get(
        "title_review_required"
    ):
        return "unknown"

    return _constraint_value(
        easements.get(
            "constraint_level"
        )
    )


def _development_confidence(
    parcel: dict,
    preliminary_units: int | None
) -> str:

    score = 0

    lot_size = parcel.get(
        "lot_size"
    ) or {}

    zoning = parcel.get(
        "zoning"
    ) or {}

    general_plan = parcel.get(
        "general_plan"
    ) or {}

    buildable_area = parcel.get(
        "buildable_area"
    ) or {}

    road_access = parcel.get(
        "road_access"
    ) or {}

    if lot_size.get(
        "square_feet"
    ):
        score += 1

    if zoning.get(
        "status"
    ) == "found":
        score += 2

    if general_plan.get(
        "status"
    ) == "found":
        score += 1

    if buildable_area.get(
        "preliminary_buildable_acres"
    ) is not None:
        score += 2

    if road_access.get(
        "frontage_edge_found"
    ):
        score += 1

    if preliminary_units is not None:
        score += 1

    if score >= 7:
        return "moderate"

    if score >= 4:
        return "low_to_moderate"

    return "low"


def build_development_scenario(
    parcel: dict
) -> dict:

    lot_size = parcel.get(
        "lot_size"
    ) or {}

    current_land_use = parcel.get(
        "current_land_use"
    ) or {}

    general_plan = parcel.get(
        "general_plan"
    ) or {}

    zoning = parcel.get(
        "zoning"
    ) or {}

    buildable_area = parcel.get(
        "buildable_area"
    ) or {}

    flood = parcel.get(
        "flood_hazard"
    ) or {}

    fire = parcel.get(
        "fire_hazard"
    ) or {}

    terrain = parcel.get(
        "terrain"
    ) or {}

    habitat = parcel.get(
        "habitat"
    ) or {}

    wetlands = parcel.get(
        "wetlands"
    ) or {}

    utilities = parcel.get(
        "utilities"
    ) or {}

    road_access = parcel.get(
        "road_access"
    ) or {}

    easements = parcel.get(
        "easements"
    ) or {}

    permit_history = parcel.get(
        "permit_history"
    ) or {}

    parcel_acres = _number(
        lot_size.get(
            "acreage"
        )
    )

    lot_square_feet = _number(
        lot_size.get(
            "square_feet"
        )
    )

    if (
        lot_square_feet is None
        and parcel_acres is not None
    ):
        lot_square_feet = (
            parcel_acres
            * SQFT_PER_ACRE
        )

    setback_envelope_acres = _number(
        buildable_area.get(
            "directional_setback_screened_acres"
        )
    )

    setback_envelope_square_feet = (
        setback_envelope_acres * SQFT_PER_ACRE
        if setback_envelope_acres is not None
        else None
    )

    setback_envelope_percent = _number(
        buildable_area.get(
            "directional_setback_screened_percent"
        )
    )

    minimum_lot_size = _minimum_lot_size_square_feet(
        zoning.get(
            "minimum_lot_size"
        )
    )

    general_plan_units_raw = general_plan.get(
        "estimated_maximum_units"
    )

    general_plan_units = (
        int(general_plan_units_raw)
        if isinstance(
            general_plan_units_raw,
            (int, float)
        )
        else None
    )

    zoning_units = _estimate_zoning_units(
        lot_square_feet=lot_square_feet,
        minimum_lot_size_square_feet=minimum_lot_size
    )

    residential = _is_residential(
        zoning=zoning,
        land_use=current_land_use
    )

    preliminary_units = _preliminary_unit_estimate(
        general_plan_units=general_plan_units,
        zoning_units=zoning_units,
        residential=residential
    )

    if residential:
        scenario = (
            "single_family_residential"
            if preliminary_units in (
                None,
                1
            )
            else "residential"
        )
    else:
        scenario = (
            "development_use_requires_review"
        )

    primary_use = (
        "Single-family residential"
        if scenario
        == "single_family_residential"
        else (
            current_land_use.get(
                "description"
            )
            or zoning.get(
                "code"
            )
            or "Requires zoning review"
        )
    )

    site_constraints = {
        "flood": (
            _constraint_value(
                flood.get(
                    "risk_level"
                ),
                "unknown"
            )
        ),
        "fire": (
            _constraint_value(
                fire.get(
                    "risk_level"
                ),
                "unknown"
            )
        ),
        "slope": (
            _constraint_value(
                terrain.get(
                    "terrain_class"
                ),
                "unknown"
            )
        ),
        "habitat": (
            _constraint_value(
                habitat.get(
                    "constraint_level"
                ),
                "unknown"
            )
        ),
        "wetlands": (
            _constraint_value(
                wetlands.get(
                    "constraint_level"
                ),
                "unknown"
            )
        ),
        "access": _access_constraint(
            road_access
        ),
        "utilities": (
            _constraint_value(
                utilities.get(
                    "constraint_level"
                ),
                "unknown"
            )
        ),
        "easements": _easement_constraint(
            easements
        )
    }

    major_flags: list[str] = []

    next_steps: list[str] = []

    reasoning: list[str] = []

    if (
        lot_square_feet is not None
        and minimum_lot_size is not None
    ):
        if (
            lot_square_feet
            >= minimum_lot_size
        ):
            reasoning.append(
                "The parcel passes the preliminary "
                f"minimum-lot-size screen: approximately "
                f"{round(lot_square_feet):,} square feet "
                f"versus a mapped minimum of "
                f"{round(minimum_lot_size):,} square feet."
            )
        else:
            major_flags.append(
                "The mapped parcel area appears smaller "
                "than the zoning minimum lot size. Legal "
                "lot status and any nonconforming-lot rights "
                "must be reviewed."
            )

    if general_plan_units is not None:
        reasoning.append(
            "The General Plan data produces a preliminary "
            f"gross-density estimate of up to "
            f"{general_plan_units} dwelling unit"
            f"{'' if general_plan_units == 1 else 's'}."
        )

    if zoning_units is not None:
        reasoning.append(
            "Using mapped parcel area divided by the zoning "
            "minimum lot size produces a rough lot-size "
            f"capacity screen of {zoning_units} lot"
            f"{'' if zoning_units == 1 else 's'}. "
            "This is not a subdivision approval."
        )

    if setback_envelope_square_feet is not None:
        reasoning.append(
            "The preliminary directional setback envelope "
            f"contains approximately "
            f"{round(setback_envelope_square_feet):,} square feet. "
            "This is not a final buildable-area calculation."
        )

    if road_access.get(
        "legal_access_confirmed"
    ) is not True:
        major_flags.append(
            "Legal access has not been confirmed."
        )
        next_steps.append(
            "Confirm legal access and recorded frontage "
            "through title documents and agency records."
        )

    if easements.get(
        "title_review_required"
    ):
        major_flags.append(
            "A complete recorded-easement inventory is "
            "not available from the GIS screening."
        )
        next_steps.append(
            "Obtain and review a preliminary title report "
            "and recorded easement documents."
        )

    if permit_history.get(
        "building_permit_found"
    ):
        major_flags.append(
            "Prior building-permit history was identified "
            "and should be reviewed for status, scope, and "
            "possible unresolved conditions."
        )
        next_steps.append(
            "Review identified permit and inspection "
            "records before relying on the site for a new "
            "development proposal."
        )

    if utilities.get(
        "inside_sanitation_district"
    ) is True:
        next_steps.append(
            "Confirm actual sewer connection availability, "
            "capacity, lateral location, fees, and right to connect."
        )
    else:
        next_steps.append(
            "Confirm sewer or onsite wastewater feasibility."
        )

    if zoning.get(
        "status"
    ) == "found":
        next_steps.append(
            "Verify zoning, setbacks, height, parking, and "
            "other development standards with the controlling agency."
        )
    else:
        major_flags.append(
            "A complete zoning result is not currently available."
        )

    next_steps.append(
        "Confirm legal lot status before relying on the "
        "preliminary unit estimate."
    )

    if residential:
        next_steps.append(
            "Evaluate ADU eligibility separately under the "
            "current state and local rules before counting "
            "additional units."
        )

    confidence = _development_confidence(
        parcel=parcel,
        preliminary_units=preliminary_units
    )

    return {
        "scenario": scenario,
        "confidence": confidence,
        "parcel": {
            "lot_acres": _round(
                parcel_acres,
                3
            ),
            "lot_square_feet": _round(
                lot_square_feet,
                2
            ),
            "buildable_acres": None,
            "buildable_square_feet": None,
            "buildable_percent": None,
            "setback_envelope_acres": _round(
                setback_envelope_acres,
                3
            ),
            "setback_envelope_square_feet": _round(
                setback_envelope_square_feet,
                2
            ),
            "setback_envelope_percent": _round(
                setback_envelope_percent,
                2
            )
        },
        "density": {
            "general_plan_max_units": (
                general_plan_units
            ),
            "zoning_lot_size_screen_units": (
                zoning_units
            ),
            "preliminary_max_units": (
                preliminary_units
            ),
            "minimum_lot_size_square_feet": (
                _round(
                    minimum_lot_size,
                    2
                )
            )
        },
        "likely_development": {
            "primary_use": primary_use,
            "estimated_units": preliminary_units,
            "adu_potential": (
                "requires_review"
                if residential
                else "not_evaluated"
            ),
            "lot_split_potential": (
                _lot_split_potential(
                    lot_square_feet=lot_square_feet,
                    minimum_lot_size_square_feet=minimum_lot_size
                )
            )
        },
        "site_constraints": (
            site_constraints
        ),
        "major_flags": major_flags,
        "next_steps": next_steps,
        "reasoning": reasoning,
        "status": "preliminary",
        "disclaimer": (
            "This development scenario is an automated "
            "screening result, not an entitlement, zoning "
            "determination, subdivision approval, building "
            "permit determination, legal opinion, survey, "
            "title opinion, or guarantee of development "
            "capacity. Final development potential depends "
            "on current law, agency interpretation, legal "
            "lot status, title, access, utilities, site "
            "design, environmental review, fire requirements, "
            "and project-specific approvals."
        )
    }
