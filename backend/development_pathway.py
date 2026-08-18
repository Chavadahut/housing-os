"""Explainable preliminary entitlement pathway generator."""

from __future__ import annotations


HIGH = {"high", "very_high", "very high", "severe", "major"}


def _text(*values) -> str:
    return " ".join(str(value or "") for value in values).lower()


def _flag(label: str, status: str, detail: str) -> dict:
    return {"label": label, "status": status, "detail": detail}


def _concept_eligibility(zoning: dict, general_plan: dict, land_use: dict, units) -> dict:
    """Separate supported, incompatible, and assumption-based concept states."""
    zoning_text = _text(
        zoning.get("use_regulation"),
        zoning.get("code"),
        zoning.get("description"),
    )
    use_text = _text(
        land_use.get("description"),
        land_use.get("use_description"),
        land_use.get("category"),
    )
    plan_text = _text(
        general_plan.get("designation"),
        general_plan.get("designation_code"),
        general_plan.get("description"),
    )
    residential_terms = (
        "residential", "dwelling", "single family", "single-family",
        "multi family", "multi-family", "multifamily",
    )
    zoning_supports_housing = any(term in zoning_text for term in residential_terms)
    plan_supports_housing = any(term in plan_text for term in residential_terms)
    zoning_supports_multifamily = any(
        term in zoning_text
        for term in ("multi family", "multi-family", "multifamily", "apartment", "townhome")
    )
    use_supports_housing = any(term in use_text for term in residential_terms)
    vacant_use = any(term in use_text for term in ("vacant", "undeveloped", "unused land"))
    nonresidential_terms = (
        "commercial", "industrial", "office", "institutional", "public facility",
        "park", "open space", "recreation",
    )
    zoning_is_nonresidential = any(term in zoning_text for term in nonresidential_terms)
    density_known = isinstance(units, int) and units >= 1
    zoning_found = zoning.get("status") == "found"
    residential_policy_support = zoning_supports_housing or plan_supports_housing
    use_is_compatible = use_supports_housing or vacant_use or not use_text.strip()
    confirmed_incompatible = zoning_found and zoning_is_nonresidential and not plan_supports_housing
    supported = zoning_found and residential_policy_support and use_is_compatible and density_known and not confirmed_incompatible

    blockers = []
    if confirmed_incompatible:
        blockers.append("The mapped zoning and General Plan screening do not support a residential concept")
    else:
        if not zoning_found:
            blockers.append("Controlling zoning is not confirmed")
        if not residential_policy_support:
            blockers.append("Residential zoning or General Plan support is not confirmed")
        if not use_is_compatible:
            blockers.append("The existing-use screen conflicts with a residential concept")
        if not density_known:
            blockers.append("A preliminary residential unit yield is not available")

    options = []
    if supported:
        options.append({
            "id": "one_home",
            "label": "One home",
            "description": "Explore one detached home within the screened site envelope.",
            "units": 1,
        })
        if units >= 2:
            options.append({
                "id": "two_homes",
                "label": "Two homes",
                "description": "Explore a two-home layout without exceeding the screened yield.",
                "units": 2,
            })
            options.append({
                "id": "lot_subdivision",
                "label": "Lot subdivision",
                "description": f"Explore separate residential lots without exceeding the {units}-unit screen.",
                "units": units,
            })
            options.append({
                "id": "home_plus_adu",
                "label": "Home plus ADU",
                "description": "Explore a primary home and accessory dwelling within the two-unit screen.",
                "units": 2,
            })
        if units >= 3:
            options.append({
                "id": "small_residential_site",
                "label": f"Residential site · up to {units} homes",
                "description": "Test a multi-home site plan capped at the preliminary density screen.",
                "units": units,
            })
        if zoning_supports_multifamily and units >= 3:
            options.append({
                "id": "townhomes",
                "label": "Townhomes",
                "description": f"Explore an attached-home concept capped at {units} units.",
                "units": units,
            })
            options.append({
                "id": "small_multifamily",
                "label": "Small multifamily",
                "description": f"Explore a multifamily layout capped at {units} units.",
                "units": units,
            })
        if zoning_supports_multifamily and units >= 5:
            options.append({
                "id": "apartments",
                "label": "Apartments",
                "description": f"Explore an apartment concept capped at {units} units.",
                "units": units,
            })
        options.append({
            "id": "custom_project",
            "label": "Custom residential project",
            "description": f"Set a custom residential program from 1 to {units} units.",
            "units": units,
        })

    assumption_units = units if density_known else 1
    assumption_options = [{
        "id": "assumed_residential",
        "label": "Residential concept using assumptions",
        "description": "Explore a conservative residential layout without treating the use as confirmed.",
        "units": assumption_units,
    }]

    return {
        "eligible": bool(options),
        "status": "eligible" if options else "incompatible" if confirmed_incompatible else "assumption_required",
        "determination": "supported" if options else "confirmed_nonresidential" if confirmed_incompatible else "unconfirmed_or_conflicting",
        "screened_max_units": units if density_known else None,
        "options": options,
        "assumption_options": assumption_options,
        "bypass_allowed": not confirmed_incompatible,
        "blockers": blockers,
        "evidence": [
            f"Zoning: {zoning.get('code') or 'not confirmed'}",
            f"General Plan: {general_plan.get('designation') or general_plan.get('designation_code') or 'not confirmed'}",
            f"Existing use: {land_use.get('description') or 'not confirmed'}",
        ],
        "basis": "Preliminary zoning, current-use, and density screening",
    }


def build_development_pathway(parcel: dict) -> dict:
    scenario = parcel.get("development_scenario") or {}
    density = scenario.get("density") or {}
    likely = scenario.get("likely_development") or {}
    zoning = parcel.get("zoning") or {}
    general_plan = parcel.get("general_plan") or {}
    land_use = parcel.get("current_land_use") or {}
    fire = parcel.get("fire_hazard") or {}
    habitat = parcel.get("habitat") or {}
    wetlands = parcel.get("wetlands") or {}
    terrain = parcel.get("terrain") or {}
    flood = parcel.get("flood_hazard") or {}
    utilities = parcel.get("utilities") or {}
    access = parcel.get("road_access") or {}
    easements = parcel.get("easements") or {}

    units = density.get("preliminary_max_units") or likely.get("estimated_units")
    residential = any(term in _text(zoning.get("use_regulation"), zoning.get("code"), land_use.get("description")) for term in ("residential", "dwelling", "single family", "single-family"))
    subdivision = isinstance(units, int) and units > 1
    scenario_name = (
        f"{units} Single-Family Homes" if residential and units and units > 1
        else "1 Single-Family Home" if residential
        else likely.get("primary_use") or "Development Concept Requiring Use Review"
    )

    entitlements = []
    if subdivision:
        entitlements.append("Minor Subdivision" if units <= 4 else "Tentative Subdivision Map")
    entitlements.append("Site Plan Review")
    if zoning.get("special_regulations"):
        entitlements.append("Specific Plan / Overlay Consistency Review")
    if wetlands.get("mapped_wetland") or wetlands.get("wetland_indicator"):
        entitlements.append("Environmental / Wetland Agency Review")

    planning = [
        _flag("Residential use appears permitted", "pass" if residential and zoning.get("status") == "found" else "review", "Based on mapped zoning and current land-use screening."),
        _flag(
            f"Density supports approximately {units} unit{'s' if units != 1 else ''}" if units else "Residential density requires confirmation",
            "pass" if units else "review",
            "Preliminary gross-density and minimum-lot-size screen; not an approval.",
        ),
    ]
    if subdivision:
        planning.append(_flag("Lot subdivision required", "warning", "Creating separate legal lots requires subdivision approval and mapping."))
    if zoning.get("status") != "found":
        planning.append(_flag("Official zoning confirmation required", "warning", zoning.get("message") or "Confirm controlling zoning with the jurisdiction."))

    environmental = []
    studies = ["Preliminary drainage study", "Geotechnical investigation"]
    score = 0
    fire_level = _text(fire.get("risk_level"), fire.get("hazard_class"))
    if any(term in fire_level for term in HIGH):
        environmental.append(_flag("Very High Fire Hazard", "warning", fire.get("development_warning") or "Fire-agency design review is likely."))
        studies.append("Fire protection plan")
        score += 2
    habitat_level = _text(habitat.get("constraint_level"), habitat.get("habitat_value"))
    if any(term in habitat_level for term in HIGH) or habitat.get("constrained_acres"):
        environmental.append(_flag("Biological sensitivity", "warning", habitat.get("development_warning") or "Mapped habitat may constrain disturbance."))
        studies.append("Biological resources survey")
        score += 2
    if wetlands.get("hydric_soils_indicator") or wetlands.get("wetland_indicator") or wetlands.get("mapped_wetland"):
        environmental.append(_flag("Wetland or hydric-soil indicators", "warning", wetlands.get("development_warning") or "Field delineation may be needed."))
        studies.append("Wetland delineation / jurisdictional assessment")
        score += 2
    if flood.get("special_flood_hazard_area"):
        environmental.append(_flag("Special flood hazard area", "warning", flood.get("development_warning") or "Floodplain review is likely."))
        studies.append("Hydrology and floodplain analysis")
        score += 2
    if not environmental:
        environmental.append(_flag("No major mapped environmental trigger identified", "pass", "Field verification and agency review may still identify constraints."))
    if _text(terrain.get("terrain_class")) in {"steep", "very_steep", "very steep"}:
        studies.append("Slope stability analysis")
        score += 1

    water_known = bool(utilities.get("water_district"))
    sewer_known = utilities.get("inside_sanitation_district") is True
    legal_access = access.get("legal_access_confirmed") is True
    infrastructure = [
        _flag("Water district identified" if water_known else "Water service not confirmed", "pass" if water_known else "warning", utilities.get("water_district") or utilities.get("water_screening") or "Confirm service, capacity, and fees."),
        _flag("Public sewer district identified" if sewer_known else "Public sewer not confirmed", "pass" if sewer_known else "warning", utilities.get("sanitation_district") or utilities.get("sewer_screening") or "Evaluate sewer extension or onsite wastewater."),
        _flag("Legal access confirmed" if legal_access else "Legal access requires verification", "pass" if legal_access else "warning", access.get("development_warning") or "Confirm through title and agency records."),
    ]
    if not sewer_known:
        studies.append("Septic feasibility evaluation")
        score += 2
    if not legal_access or easements.get("title_review_required"):
        score += 1

    unknowns = []
    if not sewer_known: unknowns.append((3, "Wastewater feasibility"))
    if not legal_access: unknowns.append((2, "Legal access and recorded easements"))
    if zoning.get("status") != "found": unknowns.append((3, "Controlling zoning and development standards"))
    if wetlands.get("wetland_indicator") or wetlands.get("hydric_soils_indicator"): unknowns.append((2, "Wetland jurisdiction and developable footprint"))
    if not units: unknowns.append((2, "Allowable density and unit yield"))

    known_checks = [zoning.get("status") == "found", bool(units), water_known, sewer_known, legal_access, habitat.get("status") == "found", wetlands.get("status") == "found", fire.get("status") == "found"]
    confidence = round(45 + 50 * sum(known_checks) / len(known_checks))
    complexity = "HIGH" if score >= 5 or subdivision and score >= 3 else "MODERATE" if score >= 2 or subdivision else "LOW"
    timeline = {"LOW": "6-12 months", "MODERATE": "12-18 months", "HIGH": "18-30 months"}[complexity]

    return {
        "title": "Likely Development Path",
        "scenario_label": "Scenario A",
        "scenario_name": scenario_name,
        "likely_entitlement": " + ".join(entitlements),
        "entitlements": entitlements,
        "planning_findings": planning,
        "environmental_findings": environmental,
        "studies_likely_required": list(dict.fromkeys(studies)),
        "infrastructure_findings": infrastructure,
        "approval_complexity": complexity,
        "preconstruction_timeline": timeline,
        "confidence_percent": min(confidence, 95),
        "biggest_unknown": max(unknowns)[1] if unknowns else "Final agency confirmation of development standards",
        "concept_eligibility": _concept_eligibility(zoning, general_plan, land_use, units),
        "status": "preliminary",
        "disclaimer": "This is an explainable screening pathway, not an entitlement determination, agency commitment, or guarantee of approval.",
    }
