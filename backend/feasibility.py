import re
from typing import Any


def parse_minimum_lot_requirement(
    value: Any
) -> tuple[
    float | None,
    float | None,
    str | None
]:

    if value is None:
        return None, None, None

    normalized_value = (
        str(value)
        .strip()
        .upper()
        .replace(",", "")
    )

    if normalized_value in {
        "",
        "-",
        "NONE",
        "NULL",
        "N/A",
        "NA"
    }:
        return None, None, None

    acre_match = re.fullmatch(
        r"(\d+(?:\.\d+)?)\s*AC(?:RE|RES)?",
        normalized_value
    )

    if acre_match:

        try:

            acres = float(
                acre_match.group(1)
            )

            return (
                acres,
                acres * 43560,
                "acres"
            )

        except (
            TypeError,
            ValueError
        ):
            return None, None, None

    square_foot_match = re.fullmatch(
        r"(\d+(?:\.\d+)?)"
        r"(?:\s*(?:SF|SQ\.?\s*FT\.?|SQUARE\s*FEET))?",
        normalized_value
    )

    if square_foot_match:

        try:

            square_feet = float(
                square_foot_match.group(1)
            )

            return (
                square_feet / 43560,
                square_feet,
                "square_feet"
            )

        except (
            TypeError,
            ValueError
        ):
            return None, None, None

    return None, None, None


def add_unique(
    items: list[str],
    message: str
):

    if message not in items:
        items.append(message)


def get_habitat_display_extent(
    habitat: dict,
    habitat_value: str | None
) -> tuple[float | None, float | None]:

    breakdown = habitat.get(
        "habitat_breakdown"
    )

    if (
        isinstance(breakdown, list)
        and habitat_value
    ):

        for item in breakdown:

            if not isinstance(
                item,
                dict
            ):
                continue

            if item.get(
                "habitat_value"
            ) != habitat_value:
                continue

            return (
                item.get(
                    "parcel_percent"
                ),
                item.get(
                    "estimated_acres"
                )
            )

    return (
        habitat.get(
            "parcel_overlap_percent"
        ),
        habitat.get(
            "constrained_acres"
        )
    )


def build_feasibility_summary(
    parcel: dict
) -> dict:

    lot_size = parcel.get("lot_size") or {}
    zoning = parcel.get("zoning") or {}
    general_plan = parcel.get("general_plan") or {}
    flood_hazard = parcel.get("flood_hazard") or {}
    fire_hazard = parcel.get("fire_hazard") or {}
    terrain = parcel.get("terrain") or {}
    habitat = parcel.get("habitat") or {}
    wetlands = parcel.get("wetlands") or {}
    utilities = parcel.get("utilities") or {}
    road_access = parcel.get("road_access") or {}
    easements = parcel.get("easements") or {}
    permit_history = parcel.get("permit_history") or {}

    current_land_use = (
        parcel.get("current_land_use") or {}
    )

    jurisdiction_name = (
        zoning.get("jurisdiction")
        or general_plan.get("jurisdiction")
    )

    is_la_mesa = (
        jurisdiction_name
        == "City of La Mesa"
    )

    planning_authority_name = (
        "City of La Mesa"
        if is_la_mesa
        else "County of San Diego"
    )

    opportunities = []
    constraints = []
    missing_information = []
    recommended_next_steps = []

    actual_acres = lot_size.get("acreage")

    minimum_lot_designator = zoning.get(
        "minimum_lot_size"
    )

    (
        minimum_lot_acres,
        minimum_lot_square_feet,
        minimum_lot_unit_type
    ) = parse_minimum_lot_requirement(
        minimum_lot_designator
    )

    actual_square_feet = lot_size.get(
        "square_feet"
    )

    if (
        actual_square_feet is None
        and actual_acres is not None
    ):

        actual_square_feet = (
            actual_acres
            * 43560
        )

    estimated_units = general_plan.get(
        "estimated_maximum_units"
    )

    general_plan_estimate_status = general_plan.get(
        "estimate_status"
    )

    specific_plan_review_required = (
        general_plan_estimate_status
        == "specific_plan_review_required"
    )

    regional_general_plan_fallback = (
        general_plan_estimate_status
        == "regional_fallback_only"
    )

    zoning_code = zoning.get("code")

    general_plan_designation = general_plan.get(
        "designation"
    )

    current_use = (
        current_land_use.get("description")
        or current_land_use.get("category")
    )

    flood_risk = flood_hazard.get("risk_level")
    fire_risk = fire_hazard.get("risk_level")
    terrain_class = terrain.get("terrain_class")

    terrain_analysis_scope = terrain.get(
        "analysis_scope"
    )

    habitat_value = (
        habitat.get("dominant_habitat_value")
        or habitat.get("habitat_value")
    )

    habitat_constraint = habitat.get(
        "constraint_level"
    )

    habitat_status = habitat.get("status")

    habitat_analysis_scope = habitat.get(
        "analysis_scope"
    )

    (
        habitat_overlap_percent,
        habitat_constrained_acres
    ) = get_habitat_display_extent(
        habitat=habitat,
        habitat_value=habitat_value
    )

    wetlands_status = wetlands.get("status")

    mapped_wetland = wetlands.get(
        "mapped_wetland"
    )

    wetland_related_intersection = wetlands.get(
        "parcel_intersection_detected"
    )

    wetlands_constraint = wetlands.get(
        "constraint_level"
    )

    wetlands_analysis_scope = wetlands.get(
        "analysis_scope"
    )

    wetlands_overlap_percent = wetlands.get(
        "parcel_overlap_percent"
    )

    wetlands_constrained_acres = wetlands.get(
        "constrained_acres"
    )

    wetland_indicator = wetlands.get(
        "wetland_indicator"
    )

    vernal_pool_indicator = wetlands.get(
        "vernal_pool_indicator"
    )

    hydric_soils_indicator = wetlands.get(
        "hydric_soils_indicator"
    )

    utilities_status = utilities.get("status")

    utilities_constraint = utilities.get(
        "constraint_level"
    )

    inside_water_district = utilities.get(
        "inside_water_district"
    )

    water_district = utilities.get(
        "water_district"
    )

    inside_sanitation_district = utilities.get(
        "inside_sanitation_district"
    )

    sanitation_district = utilities.get(
        "sanitation_district"
    )

    wastewater_permit_found = utilities.get(
        "county_wastewater_permit_found"
    )

    road_status = road_access.get("status")

    road_constraint = road_access.get(
        "constraint_level"
    )

    nearest_road_name = road_access.get(
        "nearest_road_name"
    )

    nearest_road_type = road_access.get(
        "nearest_road_type"
    )

    nearest_road_distance = road_access.get(
        "nearest_road_distance_feet"
    )

    county_road_found = road_access.get(
        "county_maintained_road_found"
    )

    county_road_name = road_access.get(
        "county_maintained_road_name"
    )

    county_road_distance = road_access.get(
        "county_road_distance_feet"
    )

    nearest_road_is_county_maintained = (
        road_access.get(
            "nearest_road_is_county_maintained"
        )
    )

    direct_frontage_confirmed = road_access.get(
        "direct_frontage_confirmed"
    )

    frontage_edge_found = road_access.get(
        "frontage_edge_found"
    )

    frontage_confidence = road_access.get(
        "frontage_confidence"
    )

    frontage_road_name = road_access.get(
        "frontage_road_name"
    )

    legal_access_confirmed = road_access.get(
        "legal_access_confirmed"
    )

    easement_review_status = road_access.get(
        "easement_review_status"
    )

    easement_screening_status = easements.get(
        "status"
    )

    open_space_easement_screened = easements.get(
        "open_space_easement_screened"
    )

    open_space_easement_found = easements.get(
        "open_space_easement_found"
    )

    open_space_easement_count = easements.get(
        "open_space_easement_count"
    )

    wastewater_easement_screened = easements.get(
        "wastewater_easement_screened"
    )

    wastewater_easement_found = easements.get(
        "wastewater_easement_found"
    )

    wastewater_easement_count = easements.get(
        "wastewater_easement_count"
    )

    fire_drivable = road_access.get(
        "fire_drivable"
    )

    permit_status = permit_history.get("status")

    permit_history_level = permit_history.get(
        "permit_history_level"
    )

    permit_constraint = permit_history.get(
        "constraint_level"
    )

    discretionary_application_found = (
        permit_history.get(
            "discretionary_application_found"
        )
    )

    discretionary_application_count = (
        permit_history.get(
            "discretionary_application_count"
        )
    )

    building_permit_history_checked = (
        permit_history.get(
            "building_permit_history_checked"
        )
    )

    building_permit_records = (
        permit_history.get(
            "building_permit_records"
        )
        or []
    )

    building_permit_count = (
        permit_history.get(
            "building_permit_count"
        )
    )

    if building_permit_count is None:

        building_permit_count = len(
            building_permit_records
        )

    building_inspection_history_checked = (
        permit_history.get(
            "building_inspection_history_checked"
        )
    )

    building_inspection_records = (
        permit_history.get(
            "building_inspection_records"
        )
        or []
    )

    building_inspection_count = (
        permit_history.get(
            "building_inspection_count"
        )
    )

    if building_inspection_count is None:

        building_inspection_count = len(
            building_inspection_records
        )

    code_compliance_history_checked = (
        permit_history.get(
            "code_compliance_history_checked"
        )
    )

    code_compliance_research_status = (
        permit_history.get(
            "code_compliance_research_status"
        )
    )

    manual_permit_research_required = (
        permit_history.get(
            "manual_research_required"
        )
    )

    major_constraint_count = 0
    moderate_constraint_count = 0

    if actual_acres is not None:

        add_unique(
            opportunities,
            (
                f"The parcel contains approximately "
                f"{actual_acres:g} acres."
            )
        )

    else:

        add_unique(
            missing_information,
            "Actual parcel acreage was not available."
        )

    if (
        actual_acres is not None
        and minimum_lot_acres is not None
    ):

        if minimum_lot_unit_type == "square_feet":

            requirement_description = (
                f"{minimum_lot_square_feet:,.0f}-square-foot "
                "zoning minimum lot size"
            )

        else:

            requirement_description = (
                f"{minimum_lot_acres:g}-acre "
                "zoning minimum lot size"
            )

        if actual_acres >= minimum_lot_acres:

            parcel_size_description = ""

            if actual_square_feet is not None:

                parcel_size_description = (
                    f" The parcel contains approximately "
                    f"{actual_square_feet:,.0f} square feet."
                )

            add_unique(
                opportunities,
                (
                    f"The parcel is larger than the "
                    f"{requirement_description}."
                    f"{parcel_size_description}"
                )
            )

        else:

            parcel_size_description = ""

            if actual_square_feet is not None:

                parcel_size_description = (
                    f" The parcel contains approximately "
                    f"{actual_square_feet:,.0f} square feet."
                )

            add_unique(
                constraints,
                (
                    f"The parcel is smaller than the "
                    f"{requirement_description}."
                    f"{parcel_size_description}"
                )
            )

            major_constraint_count += 1

    elif minimum_lot_designator:

        add_unique(
            missing_information,
            (
                "The zoning minimum-lot-size value could not "
                "be interpreted as acres or square feet."
            )
        )

    if specific_plan_review_required:

        add_unique(
            missing_information,
            (
                "The parcel is within a Specific Plan Area. "
                "The County GIS provides an overall Specific Plan "
                "density, but a parcel-level additional-unit estimate "
                "cannot be reliably calculated from that density alone."
            )
        )

        add_unique(
            recommended_next_steps,
            (
                "Review the applicable Specific Plan, subdivision "
                "history, legal lot status, and prior approvals before "
                "estimating additional dwelling-unit potential."
            )
        )

    if estimated_units is not None:

        if estimated_units > 0:

            add_unique(
                opportunities,
                (
                    "The General Plan produces a preliminary "
                    f"gross-density estimate of up to "
                    f"{estimated_units} dwelling unit"
                    f"{'' if estimated_units == 1 else 's'}."
                )
            )

        else:

            add_unique(
                constraints,
                (
                    "The available General Plan information "
                    "did not produce a positive preliminary "
                    "unit estimate."
                )
            )

    elif not specific_plan_review_required:

        if regional_general_plan_fallback:

            add_unique(
                missing_information,
                (
                    "Only regional SANDAG planned-land-use "
                    "screening was available. It does not provide "
                    "a controlling City of La Mesa General Plan "
                    "designation or a reliable parcel-level unit "
                    "estimate."
                )
            )

        else:

            add_unique(
                missing_information,
                (
                    "A preliminary General Plan unit estimate "
                    "was not available."
                )
            )

    if flood_risk == "minimal":

        add_unique(
            opportunities,
            (
                "The parcel lookup point appears outside "
                "the mapped FEMA Special Flood Hazard Area."
            )
        )

    elif flood_risk == "moderate":

        add_unique(
            constraints,
            (
                "The parcel lookup point appears within a "
                "moderate FEMA flood-hazard area."
            )
        )

        moderate_constraint_count += 1

    elif flood_risk in {
        "high",
        "regulatory_floodway",
        "future_conditions"
    }:

        add_unique(
            constraints,
            (
                "The parcel lookup point is within a mapped "
                "FEMA flood-hazard area that may affect "
                "development."
            )
        )

        major_constraint_count += 1

    elif flood_risk in {
        "unknown",
        "undetermined",
        None
    }:

        add_unique(
            missing_information,
            (
                "Flood-hazard conditions require additional "
                "confirmation."
            )
        )

    if fire_risk == "very_high":

        add_unique(
            constraints,
            (
                "The parcel lookup point is within a Very "
                "High Fire Hazard Severity Zone."
            )
        )

        major_constraint_count += 1

    elif fire_risk == "high":

        add_unique(
            constraints,
            (
                "The parcel lookup point is within a High "
                "Fire Hazard Severity Zone."
            )
        )

        major_constraint_count += 1

    elif fire_risk == "moderate":

        add_unique(
            constraints,
            (
                "The parcel lookup point is within a Moderate "
                "Fire Hazard Severity Zone."
            )
        )

        moderate_constraint_count += 1

    elif fire_risk in {
        "unknown",
        None
    }:

        add_unique(
            missing_information,
            (
                "Fire-hazard conditions require additional "
                "confirmation."
            )
        )

    terrain_scope_label = (
        "The parcel-wide terrain sample"
        if terrain_analysis_scope == "parcel_wide_sample"
        else "The sampled location"
    )

    if terrain_class == "mostly_flat":

        add_unique(
            opportunities,
            (
                f"{terrain_scope_label} appears mostly flat, "
                "which may reduce preliminary grading concerns."
            )
        )

    elif terrain_class == "gentle_slope":

        add_unique(
            opportunities,
            (
                f"{terrain_scope_label} has a gentle slope "
                "and does not show a major preliminary "
                "terrain issue."
            )
        )

    elif terrain_class == "moderate_slope":

        add_unique(
            constraints,
            (
                f"{terrain_scope_label} has a moderate slope "
                "that may affect grading, drainage, access, "
                "or septic placement."
            )
        )

        moderate_constraint_count += 1

    elif terrain_class in {
        "steep",
        "very_steep"
    }:

        add_unique(
            constraints,
            (
                f"{terrain_scope_label} is steep and may create "
                "significant grading, access, drainage, or "
                "foundation constraints."
            )
        )

        major_constraint_count += 1

    else:

        add_unique(
            missing_information,
            (
                "Parcel terrain requires additional "
                "investigation."
            )
        )

    if habitat_status == "found":

        habitat_is_parcel_wide = (
            habitat_analysis_scope
            == "parcel_wide_sample"
        )

        if habitat_is_parcel_wide:

            habitat_area_description = (
                f"Approximately "
                f"{habitat_overlap_percent:g}% of the "
                "parcel sample"
                if habitat_overlap_percent is not None
                else "The parcel-wide habitat sample"
            )

            if habitat_constrained_acres is not None:

                habitat_area_description += (
                    f", or approximately "
                    f"{habitat_constrained_acres:g} acres,"
                )

        else:

            habitat_area_description = (
                "The parcel lookup point"
            )

        if habitat_constraint == "major":

            add_unique(
                constraints,
                (
                    f"{habitat_area_description} is mapped as "
                    f"{habitat_value or 'High or Very High'} "
                    "habitat value. Biological surveys, "
                    "avoidance, mitigation, reduced development "
                    "area, open-space preservation, or agency "
                    "consultation may be required."
                )
            )

            major_constraint_count += 1

        elif habitat_constraint == "moderate":

            add_unique(
                constraints,
                (
                    f"{habitat_area_description} contains "
                    f"{habitat_value or 'moderate-value'} "
                    "habitat conditions that may affect the "
                    "usable development area."
                )
            )

            moderate_constraint_count += 1

        elif habitat_constraint in {
            "low",
            "developed"
        }:

            add_unique(
                opportunities,
                (
                    f"{habitat_area_description} is primarily "
                    f"mapped as {habitat_value} habitat value, "
                    "although site-specific biological review "
                    "may still be required."
                )
            )

        elif habitat_constraint == "agricultural":

            add_unique(
                constraints,
                (
                    f"{habitat_area_description} is mapped as "
                    "Agriculture in the Habitat Evaluation Model. "
                    "Agricultural and biological-resource review "
                    "may still apply."
                )
            )

            moderate_constraint_count += 1

        else:

            add_unique(
                missing_information,
                (
                    "The habitat classification could not be "
                    "fully interpreted."
                )
            )

    else:

        add_unique(
            missing_information,
            (
                "A usable parcel-wide biological and "
                "sensitive-habitat screening result was not "
                "available."
            )
        )

    if (
        wetlands_status == "found"
        and wetland_related_intersection is True
    ):

        wetlands_is_parcel_wide = (
            wetlands_analysis_scope
            == "parcel_wide_sample"
        )

        indicator_labels = []

        if wetland_indicator is True:
            indicator_labels.append(
                "mapped wetland"
            )

        if vernal_pool_indicator is True:
            indicator_labels.append(
                "vernal-pool"
            )

        if hydric_soils_indicator is True:
            indicator_labels.append(
                "hydric-soil"
            )

        indicator_description = (
            ", ".join(indicator_labels)
            if indicator_labels
            else "wetland-related"
        )

        if wetlands_is_parcel_wide:

            wetlands_area_description = (
                f"Approximately "
                f"{wetlands_overlap_percent:g}% of the "
                "parcel sample"
                if wetlands_overlap_percent is not None
                else "The parcel-wide screening"
            )

            if wetlands_constrained_acres is not None:

                wetlands_area_description += (
                    f", or approximately "
                    f"{wetlands_constrained_acres:g} acres,"
                )

            wetlands_message = (
                f"{wetlands_area_description} has positive "
                f"{indicator_description} indicators. "
                "These mapped indicators do not by themselves "
                "confirm the presence or legal boundary of a "
                "wetland. Field review, delineation if warranted, "
                "buffers, drainage review, avoidance, mitigation, "
                "or agency permits may be required."
            )

        else:

            wetlands_message = (
                "The parcel lookup point has positive mapped "
                f"{indicator_description} indicators. These "
                "indicators do not by themselves confirm the "
                "presence or legal boundary of a wetland."
            )

        add_unique(
            constraints,
            wetlands_message
        )

        if wetlands_constraint == "major":

            major_constraint_count += 1

        elif wetlands_constraint == "moderate":

            moderate_constraint_count += 1

    elif wetlands_status == "not_confirmed":

        add_unique(
            missing_information,
            (
                "The wetlands screening did not confirm a "
                "positive mapped wetland, vernal-pool, or "
                "hydric-soil indicator, but unmapped wetlands, "
                "streams, drainage features, and jurisdictional "
                "waters have not been ruled out."
            )
        )

    elif wetlands_status == "not_found":

        if (
            wetlands_analysis_scope
            == "parcel_wide_sample"
        ):

            add_unique(
                missing_information,
                (
                    "The parcel-wide GIS screening did not "
                    "detect a positive mapped wetland, "
                    "vernal-pool, or hydric-soil indicator. "
                    "Unmapped wetlands, streams, drainage "
                    "features, and jurisdictional waters have "
                    "not been ruled out."
                )
            )

        else:

            add_unique(
                missing_information,
                (
                    "No County Wetlands RPO feature was "
                    "identified near the lookup point, but the "
                    "entire parcel has not been evaluated for "
                    "wetlands, streams, drainage features, or "
                    "jurisdictional waters."
                )
            )

    else:

        add_unique(
            missing_information,
            (
                "Wetland and drainage conditions require "
                "additional parcel-wide review."
            )
        )

    if utilities_status == "found":

        if (
            inside_water_district is True
            and water_district
        ):

            add_unique(
                opportunities,
                (
                    "The parcel lookup point is inside the mapped "
                    f"{water_district} service district."
                )
            )

        elif inside_water_district is False:

            add_unique(
                constraints,
                (
                    "The parcel lookup point was not identified "
                    "inside a mapped water district. A private "
                    "well or another water source may need to "
                    "be investigated."
                )
            )

            moderate_constraint_count += 1

        else:

            add_unique(
                missing_information,
                (
                    "Mapped water-district coverage could not "
                    "be confirmed."
                )
            )

        if utilities_constraint == "major":

            add_unique(
                constraints,
                (
                    "The preliminary utility screening identified "
                    "a major water, sewer, or onsite wastewater "
                    "constraint."
                )
            )

            major_constraint_count += 1

        elif utilities_constraint == "moderate":

            if (
                inside_sanitation_district is False
                and wastewater_permit_found is False
            ):

                add_unique(
                    constraints,
                    (
                        "The parcel lookup point was not identified "
                        "inside a mapped sanitation district, and "
                        "no County wastewater permit record was "
                        "found. Onsite septic feasibility may be "
                        "required."
                    )
                )

            else:

                add_unique(
                    constraints,
                    (
                        "The preliminary utility screening "
                        "identified a moderate water, sewer, "
                        "or septic issue requiring confirmation."
                    )
                )

            moderate_constraint_count += 1

        elif utilities_constraint == "unknown":

            add_unique(
                missing_information,
                (
                    "Water, sewer, and septic availability could "
                    "not be fully determined from the available "
                    "utility records."
                )
            )

        elif utilities_constraint == "low":

            if (
                inside_sanitation_district is True
                and sanitation_district
            ):

                add_unique(
                    opportunities,
                    (
                        "The parcel lookup point is inside the "
                        f"mapped {sanitation_district} sanitation "
                        "district."
                    )
                )

            if wastewater_permit_found is True:

                add_unique(
                    opportunities,
                    (
                        "County wastewater permit records were "
                        "identified for the parcel APN."
                    )
                )

    else:

        add_unique(
            missing_information,
            (
                "Water-district, sewer, and septic screening "
                "was not available."
            )
        )

    if road_status == "found":

        if road_constraint == "low":

            if (
                nearest_road_is_county_maintained is True
                and nearest_road_name
            ):

                add_unique(
                    opportunities,
                    (
                        f"The nearest mapped road, "
                        f"{nearest_road_name}, appears to match "
                        "a nearby County-maintained road."
                    )
                )

            else:

                add_unique(
                    opportunities,
                    (
                        "A mapped road was identified near the "
                        "parcel lookup point without a major "
                        "preliminary road-access concern."
                    )
                )

        elif road_constraint == "moderate":

            if nearest_road_type == "private":

                road_description = (
                    f"The nearest mapped road, "
                    f"{nearest_road_name or 'an unnamed road'}, "
                    "appears to be private"
                )

                if nearest_road_distance is not None:

                    road_description += (
                        f" and was identified within approximately "
                        f"{nearest_road_distance} feet"
                    )

                road_description += (
                    ". Recorded access rights, maintenance "
                    "responsibilities, driveway access, and "
                    "emergency-access compliance are not confirmed."
                )

                add_unique(
                    constraints,
                    road_description
                )

            else:

                add_unique(
                    constraints,
                    (
                        "The preliminary road screening identified "
                        "a moderate access issue. Parcel frontage, "
                        "driveway access, easements, road condition, "
                        "and emergency-access compliance require "
                        "confirmation."
                    )
                )

            moderate_constraint_count += 1

        elif road_constraint == "major":

            if nearest_road_type == "private":

                add_unique(
                    constraints,
                    (
                        "The nearest mapped road appears to be "
                        "private and was identified only at a "
                        "broader screening distance. Legal and "
                        "physical access may materially affect "
                        "development."
                    )
                )

            else:

                add_unique(
                    constraints,
                    (
                        "The preliminary road screening identified "
                        "a major access concern. A usable road "
                        "connection, legal access, and emergency "
                        "access have not been established."
                    )
                )

            major_constraint_count += 1

        elif road_constraint == "unknown":

            add_unique(
                missing_information,
                (
                    "The road screening found a mapped road, but "
                    "its maintenance status and development impact "
                    "could not be fully determined."
                )
            )

        if (
            county_road_found is True
            and county_road_name
            and nearest_road_is_county_maintained is False
        ):

            county_road_message = (
                f"A County-maintained road, {county_road_name}, "
                "was identified separately from the nearest "
                "mapped road"
            )

            if county_road_distance is not None:

                county_road_message += (
                    f" within approximately "
                    f"{county_road_distance} feet"
                )

            county_road_message += (
                ", but direct parcel frontage or legal access "
                "to that road has not been confirmed."
            )

            add_unique(
                missing_information,
                county_road_message
            )

        if fire_drivable is False:

            add_unique(
                constraints,
                (
                    "The nearest mapped road was not identified "
                    "as fire-drivable in the available road data. "
                    "Emergency-access requirements may create a "
                    "significant development issue."
                )
            )

            major_constraint_count += 1

        if direct_frontage_confirmed is not True:

            if frontage_edge_found is True:

                frontage_description = (
                    "Housing OS identified probable geometric "
                    "frontage"
                )

                if frontage_road_name:

                    frontage_description += (
                        f" along {frontage_road_name}"
                    )

                if frontage_confidence:

                    frontage_description += (
                        f" with {frontage_confidence} confidence"
                    )

                frontage_description += (
                    ", but legal frontage and the recorded "
                    "right-of-way relationship have not been "
                    "confirmed."
                )

                add_unique(
                    missing_information,
                    frontage_description
                )

            else:

                add_unique(
                    missing_information,
                    (
                        "Probable geometric parcel frontage on a "
                        "mapped road was not identified."
                    )
                )

        if legal_access_confirmed is not True:

            add_unique(
                missing_information,
                (
                    "A legal right of access to the parcel has "
                    "not been confirmed."
                )
            )

        if easement_screening_status == "found":

            if open_space_easement_found is True:

                easement_count = (
                    open_space_easement_count
                    if open_space_easement_count is not None
                    else 0
                )

                add_unique(
                    constraints,
                    (
                        f"{easement_count} mapped recorded "
                        "open-space or conservation-type easement "
                        f"feature{'' if easement_count == 1 else 's'} "
                        "intersect the parcel. The recorded "
                        "documents and exact development effect "
                        "require review."
                    )
                )

            elif open_space_easement_screened is True:

                add_unique(
                    missing_information,
                    (
                        "The County/SanGIS recorded open-space "
                        "easement layer did not identify a mapped "
                        "feature on the parcel, but that dataset is "
                        "incomplete and does not rule out other "
                        "recorded easements."
                    )
                )

            if wastewater_easement_found is True:

                wastewater_count = (
                    wastewater_easement_count
                    if wastewater_easement_count is not None
                    else 0
                )

                add_unique(
                    constraints,
                    (
                        f"{wastewater_count} mapped County "
                        "wastewater easement "
                        f"feature{'' if wastewater_count == 1 else 's'} "
                        "intersect the parcel. The document, "
                        "location, maintenance rights, and effect "
                        "on building placement require review."
                    )
                )

            elif wastewater_easement_screened is True:

                add_unique(
                    opportunities,
                    (
                        "No mapped County wastewater easement "
                        "feature was identified on the parcel in "
                        "the available GIS layer."
                    )
                )

            add_unique(
                missing_information,
                (
                    "Access, road, private utility, and other "
                    "title-recorded easements are not available "
                    "as a complete parcel-level GIS inventory. "
                    "A title report and recorded documents are "
                    "still required."
                )
            )

        elif easement_review_status != "reviewed":

            add_unique(
                missing_information,
                (
                    "Recorded access, utility, and road easements "
                    "have not been reviewed."
                )
            )

    else:

        add_unique(
            missing_information,
            (
                "Mapped road proximity and road-maintenance "
                "screening was not available."
            )
        )

        add_unique(
            missing_information,
            (
                "Legal access, road standards, easements, and "
                "emergency access have not been confirmed."
            )
        )

    if permit_status == "found":

        if permit_constraint == "moderate":

            add_unique(
                constraints,
                (
                    "One or more discretionary planning records "
                    "appear active, pending, or unresolved. Their "
                    "conditions, status, and effect on future "
                    f"development require direct {planning_authority_name} "
                    "review."
                )
            )

            moderate_constraint_count += 1

        elif permit_constraint == "major":

            add_unique(
                constraints,
                (
                    "The permit-history screening identified a "
                    "major unresolved planning or development "
                    "record that may materially affect the parcel."
                )
            )

            major_constraint_count += 1

        elif permit_history_level in {
            "permit_history_found",
            "discretionary_history_found"
        }:

            if building_permit_records:

                for permit_record in building_permit_records:

                    permit_number = (
                        permit_record.get(
                            "permit_number"
                        )
                        or "Unknown permit number"
                    )

                    permit_status_value = (
                        permit_record.get(
                            "status"
                        )
                        or "status unavailable"
                    )

                    permit_description = (
                        permit_record.get(
                            "description"
                        )
                    )

                    permit_applied_date = (
                        permit_record.get(
                            "applied_date"
                        )
                    )

                    permit_summary = (
                        f"County building permit "
                        f"{permit_number} was identified with "
                        f"status {permit_status_value}"
                    )

                    if permit_description:

                        permit_summary += (
                            f" for {permit_description}"
                        )

                    if permit_applied_date:

                        permit_summary += (
                            f", applied {permit_applied_date}"
                        )

                    permit_summary += (
                        ". The permit file, expiration history, "
                        "and any associated work should be "
                        "reviewed before relying on the existing "
                        "improvements."
                    )

                    add_unique(
                        missing_information,
                        permit_summary
                    )

            if building_inspection_records:

                for inspection_record in (
                    building_inspection_records
                ):

                    inspection_permit_number = (
                        inspection_record.get(
                            "permit_number"
                        )
                        or "Unknown permit number"
                    )

                    inspection_type = (
                        inspection_record.get(
                            "inspection_type"
                        )
                        or "Inspection"
                    )

                    inspection_status = (
                        inspection_record.get(
                            "status"
                        )
                        or "status unavailable"
                    )

                    inspection_date = (
                        inspection_record.get(
                            "inspection_date"
                        )
                    )

                    inspection_summary = (
                        f"County inspection {inspection_type} "
                        f"for permit "
                        f"{inspection_permit_number} was "
                        f"identified with result "
                        f"{inspection_status}"
                    )

                    if inspection_date:

                        inspection_summary += (
                            f" on {inspection_date}"
                        )

                    inspection_summary += "."

                    normalized_inspection_status = (
                        str(
                            inspection_status
                        ).strip().lower()
                    )

                    if normalized_inspection_status in {
                        "fail",
                        "failed",
                        "failure",
                        "not approved",
                        "correction required",
                        "corrections required"
                    }:

                        inspection_summary += (
                            " Because the inspection did not "
                            "pass, Housing OS cannot confirm "
                            "that the permitted work received "
                            "final approval or was completed "
                            "in compliance with the permit."
                        )

                    else:

                        inspection_summary += (
                            " The inspection record should be "
                            "reviewed with the permit file to "
                            "confirm the final disposition of "
                            "the permitted work."
                        )

                    add_unique(
                        missing_information,
                        inspection_summary
                    )

            if discretionary_application_found is True:

                record_count = (
                    discretionary_application_count
                    if discretionary_application_count
                    is not None
                    else 0
                )

                add_unique(
                    missing_information,
                    (
                        f"{record_count} discretionary planning "
                        f"record{'' if record_count == 1 else 's'} "
                        "were identified. Prior approvals, "
                        "conditions, expiration dates, recorded "
                        "documents, and project changes require "
                        "review."
                    )
                )

        elif permit_history_level in {
            "no_open_data_permit_records_found",
            "no_discretionary_records_found"
        }:

            add_unique(
                missing_information,
                (
                    "No matching discretionary planning "
                    f"application was found in the available "
                    f"{planning_authority_name} screening data. "
                    "This does not establish that the parcel has "
                    "no permits or development history."
                )
            )

        elif discretionary_application_found is True:

            add_unique(
                missing_information,
                (
                    "Discretionary planning records were found, "
                    "but their development impact could not be "
                    "fully interpreted."
                )
            )

        if building_permit_history_checked is not True:

            add_unique(
                missing_information,
                (
                    "Complete building-permit and inspection "
                    "history has not been checked."
                )
            )

        if code_compliance_history_checked is not True:

            if code_compliance_research_status == (
                "manual_official_research_required"
            ):

                add_unique(
                    missing_information,
                    (
                        "County Code Compliance history remains "
                        "unverified. The County directs property "
                        "research through Accela Citizen Access, "
                        "and Housing OS does not have a documented "
                        "parcel-level public API that can reliably "
                        "confirm a complete Code Compliance case "
                        "history."
                    )
                )

            else:

                add_unique(
                    missing_information,
                    (
                        "Code-compliance and enforcement history "
                        "has not been checked."
                    )
                )

        if manual_permit_research_required is True:

            add_unique(
                missing_information,
                (
                    f"Manual {planning_authority_name} permit and "
                    "document research is still required, including "
                    "archived and pre-digital records."
                )
            )

    else:

        add_unique(
            missing_information,
            (
                "Automated discretionary planning-history "
                "screening was not available."
            )
        )

        add_unique(
            missing_information,
            (
                "Building permits, inspections, code compliance, "
                "and archived development records have not been "
                "reviewed."
            )
        )

    if terrain_analysis_scope == "parcel_wide_sample":

        add_unique(
            missing_information,
            (
                "The parcel-wide terrain sample does not replace "
                "a licensed topographic survey and may miss "
                "localized steep areas, drainage features, or "
                "the final usable building area."
            )
        )

    else:

        add_unique(
            missing_information,
            (
                "Parcel-wide slope and usable building-area "
                "conditions have not been confirmed."
            )
        )

    add_unique(
        missing_information,
        (
            "Mapped utility-district coverage does not confirm "
            "water availability, meter capacity, connection "
            "rights, sewer capacity, or septic approval."
        )
    )

    add_unique(
        missing_information,
        (
            "Utility-line locations and legal utility-service "
            "rights have not been confirmed."
        )
    )

    add_unique(
        missing_information,
        (
            "Cultural resources, parcel-wide drainage, and other "
            "environmental overlays have not been fully reviewed."
        )
    )

    if zoning_code:

        add_unique(
            recommended_next_steps,
            (
                f"Confirm permitted residential and accessory "
                f"uses under zoning {zoning_code}."
            )
        )

    else:

        add_unique(
            missing_information,
            "A confirmed zoning classification was not available."
        )

    if general_plan_designation:

        if regional_general_plan_fallback:

            add_unique(
                recommended_next_steps,
                (
                    "Treat the SANDAG planned-land-use result "
                    f"({general_plan_designation}) as regional "
                    "screening only. Confirm the controlling "
                    "City of La Mesa General Plan designation "
                    "before using it for entitlement or unit "
                    "calculations."
                )
            )

        else:

            add_unique(
                recommended_next_steps,
                (
                    "Confirm that the proposed project is consistent "
                    f"with the {general_plan_designation} "
                    "General Plan designation."
                )
            )

    if current_use:

        add_unique(
            recommended_next_steps,
            (
                f"Confirm the legality and permit history of "
                f"the existing use identified as {current_use}."
            )
        )

    if fire_risk in {
        "very_high",
        "high",
        "moderate"
    }:

        add_unique(
            recommended_next_steps,
            (
                "Contact the applicable fire authority to confirm "
                "access, water supply, defensible-space, and "
                "wildland-urban interface requirements."
            )
        )

    if habitat_constraint in {
        "major",
        "moderate",
        "agricultural"
    }:

        add_unique(
            recommended_next_steps,
            (
                "Consult a qualified biologist to evaluate the "
                "entire parcel for sensitive habitat, species, "
                "wetlands, avoidance areas, and mitigation needs."
            )
        )

    if (
        wetlands_status == "found"
        and wetland_related_intersection is True
    ):

        add_unique(
            recommended_next_steps,
            (
                "Have a qualified wetland or biological "
                "professional review the mapped indicators and "
                "determine whether a formal wetland delineation, "
                "buffers, drainage analysis, avoidance, "
                "mitigation, or agency permits are required."
            )
        )

    elif (
        wetlands_analysis_scope
        == "parcel_wide_sample"
    ):

        add_unique(
            recommended_next_steps,
            (
                "Confirm unmapped streams, drainage features, "
                "wetlands, hydric soils, and jurisdictional "
                "waters through site-specific review before "
                "preparing a final development layout."
            )
        )

    else:

        add_unique(
            recommended_next_steps,
            (
                "Confirm parcel-wide wetlands, streams, drainage "
                "features, hydric soils, and jurisdictional waters "
                "before relying on the point-based screening."
            )
        )

    if inside_water_district is True:

        district_name = (
            water_district
            or "the mapped water district"
        )

        add_unique(
            recommended_next_steps,
            (
                f"Contact {district_name} to confirm water-service "
                "availability, meter requirements, capacity, "
                "connection fees, and fire-flow requirements."
            )
        )

    elif inside_water_district is False:

        add_unique(
            recommended_next_steps,
            (
                "Confirm whether a private well or another legal "
                "water source is available and obtain any required "
                "groundwater or well approvals."
            )
        )

    if inside_sanitation_district is True:

        district_name = (
            sanitation_district
            or "the applicable sanitation district"
        )

        add_unique(
            recommended_next_steps,
            (
                f"Contact {district_name} to confirm sewer capacity, "
                "connection rights, lateral location, fees, and "
                "permit requirements."
            )
        )

    else:

        add_unique(
            recommended_next_steps,
            (
                "Obtain an onsite wastewater feasibility review, "
                "including soils evaluation, percolation testing, "
                "septic layout, reserve area, setbacks, and "
                "applicable agency approval requirements."
            )
        )

    if terrain_analysis_scope == "parcel_wide_sample":

        add_unique(
            recommended_next_steps,
            (
                "Obtain a licensed boundary and topographic survey "
                "to confirm parcel-wide elevations, localized "
                "slopes, drainage, grading limits, and the usable "
                "building area."
            )
        )

    else:

        add_unique(
            recommended_next_steps,
            (
                "Obtain a parcel-wide boundary and topographic "
                "survey before relying on the local point-based "
                "terrain analysis."
            )
        )

    if road_status == "found":

        if nearest_road_type == "private":

            add_unique(
                recommended_next_steps,
                (
                    "Obtain a title report and recorded easement "
                    "documents to confirm legal access over the "
                    "private road and determine road-maintenance "
                    "rights and obligations."
                )
            )

        else:

            add_unique(
                recommended_next_steps,
                (
                    "Obtain a title report and recorded documents "
                    "to confirm direct legal frontage, any access "
                    "easement, road right-of-way, and private "
                    "utility or other easements affecting the "
                    "parcel."
                )
            )

        if (
            county_road_found is True
            and county_road_name
            and nearest_road_is_county_maintained is False
        ):

            add_unique(
                recommended_next_steps,
                (
                    f"Confirm whether the parcel can legally and "
                    f"physically connect to {county_road_name}; "
                    "the proximity screening alone does not "
                    "establish access."
                )
            )

        add_unique(
            recommended_next_steps,
            (
                "Confirm driveway permits, road width, surface, "
                "grade, turnaround, bridge or culvert conditions, "
                "and emergency-vehicle access with "
                f"{planning_authority_name} and the applicable "
                "fire authority."
            )
        )

    else:

        add_unique(
            recommended_next_steps,
            (
                "Confirm legal access, road standards, easements, "
                "driveway permits, and emergency access."
            )
        )

    if permit_status == "found":

        if discretionary_application_found is True:

            add_unique(
                recommended_next_steps,
                (
                    "Review each identified discretionary planning "
                    "record, including approvals, conditions, "
                    "expiration dates, staff reports, plans, and "
                    "recorded documents."
                )
            )

        else:

            if is_la_mesa:

                add_unique(
                    recommended_next_steps,
                    (
                        "Search City of La Mesa planning and "
                        "building records by address and APN for "
                        "permits, inspections, discretionary "
                        "approvals, and archived documents."
                    )
                )

            else:

                add_unique(
                    recommended_next_steps,
                    (
                        "Search County Citizen Access and the PDS "
                        "Document Library by APN and address for "
                        "building permits, inspections, planning "
                        "records, and archived documents."
                    )
                )

        if building_permit_records:

            permit_numbers = [
                str(
                    record.get(
                        "permit_number"
                    )
                )
                for record in building_permit_records
                if record.get(
                    "permit_number"
                )
            ]

            permit_reference = (
                ", ".join(
                    permit_numbers
                )
                if permit_numbers
                else "the identified building-permit record"
            )

            add_unique(
                recommended_next_steps,
                (
                    f"Review {permit_reference} in County "
                    "Citizen Access and available archived "
                    "records to confirm final disposition, "
                    "approved scope, and whether the associated "
                    "work was completed or abandoned."
                )
            )

        elif building_permit_history_checked is not True:

            add_unique(
                recommended_next_steps,
                (
                    "Confirm the building-permit and inspection "
                    "history for all existing structures and uses."
                )
            )

        if building_inspection_records:

            failed_inspections = [
                record
                for record in building_inspection_records
                if str(
                    record.get(
                        "status"
                    )
                    or ""
                ).strip().lower()
                in {
                    "fail",
                    "failed",
                    "failure",
                    "not approved",
                    "correction required",
                    "corrections required"
                }
            ]

            if failed_inspections:

                failed_permits = list(
                    dict.fromkeys(
                        str(
                            record.get(
                                "permit_number"
                            )
                        )
                        for record in failed_inspections
                        if record.get(
                            "permit_number"
                        )
                    )
                )

                failed_permit_reference = (
                    ", ".join(
                        failed_permits
                    )
                    if failed_permits
                    else "the identified permit"
                )

                add_unique(
                    recommended_next_steps,
                    (
                        "Resolve the failed inspection history "
                        f"associated with "
                        f"{failed_permit_reference}. Confirm "
                        "whether corrections were completed, "
                        "whether a later passing final inspection "
                        "exists outside the open dataset, and "
                        "whether any current permit or code issue "
                        "remains."
                    )
                )

        elif building_inspection_history_checked is not True:

            add_unique(
                recommended_next_steps,
                (
                    "Confirm the building-permit and inspection "
                    "history for all existing structures and uses."
                )
            )

        if code_compliance_history_checked is not True:

            if code_compliance_research_status == (
                "manual_official_research_required"
            ):

                add_unique(
                    recommended_next_steps,
                    (
                        "Research the parcel in County Accela "
                        "Citizen Access for open Code Compliance "
                        "cases and contact PDS Code Compliance if "
                        "a case, violation, or unresolved record "
                        "appears. For complete historical records, "
                        "request the relevant County file when "
                        "necessary."
                    )
                )

            else:

                add_unique(
                    recommended_next_steps,
                    (
                        "Check for open or historical "
                        "code-compliance and enforcement cases "
                        "affecting the parcel."
                    )
                )

    else:

        if is_la_mesa:

            add_unique(
                recommended_next_steps,
                (
                    "Complete manual permit-history research "
                    "through City of La Mesa planning, building, "
                    "and available public-record channels."
                )
            )

        else:

            add_unique(
                recommended_next_steps,
                (
                    "Complete manual permit-history research through "
                    "County Citizen Access, the PDS Document Library, "
                    "and available public-record channels."
                )
            )

    add_unique(
        recommended_next_steps,
        (
            "Confirm utility-line locations and recorded utility "
            "easements before preparing a development layout."
        )
    )

    add_unique(
        recommended_next_steps,
        (
            "Review environmental overlays and biological, "
            "cultural, drainage, wetland, and grading constraints."
        )
    )

    core_data_gaps = []

    if actual_acres is None:
        core_data_gaps.append(
            "parcel acreage"
        )

    if not zoning_code:
        core_data_gaps.append(
            "zoning"
        )

    if regional_general_plan_fallback:

        core_data_gaps.append(
            "official City of La Mesa General Plan designation"
        )

    elif not general_plan_designation:

        core_data_gaps.append(
            "General Plan designation"
        )

    if (
        estimated_units is None
        and not specific_plan_review_required
    ):
        core_data_gaps.append(
            "preliminary unit estimate"
        )

    buildable_area = parcel.get(
        "buildable_area"
    ) or {}

    setback_screening_status = (
        buildable_area.get(
            "setback_envelope_status"
        )
    )

    directional_setback_acres = (
        buildable_area.get(
            "directional_setback_screened_acres"
        )
    )

    setback_envelope_acres = (
        buildable_area.get(
            "directional_setback_screened_acres"
        )
    )

    setback_envelope_percent = (
        buildable_area.get(
            "directional_setback_screened_percent"
        )
    )

    if setback_envelope_acres is not None:

        if setback_envelope_percent is not None:

            add_unique(
                opportunities,
                (
                    "Housing OS identified approximately "
                    f"{setback_envelope_acres:g} acres, "
                    f"or {setback_envelope_percent:g}% of the parcel, "
                    "within the preliminary directional setback "
                    "envelope. This is not a final buildable-area "
                    "calculation."
                )
            )

        else:

            add_unique(
                opportunities,
                (
                    "Housing OS identified approximately "
                    f"{setback_envelope_acres:g} acres "
                    "within the preliminary directional setback "
                    "envelope. This is not a final buildable-area "
                    "calculation."
                )
            )

    minimum_setback_acres = (
        buildable_area.get(
            "minimum_setback_screened_acres"
        )
    )

    if (
        setback_screening_status not in {
            "found",
            "preliminary"
        }
        and directional_setback_acres is None
        and minimum_setback_acres is None
    ):

        core_data_gaps.append(
            "setback/buildable-area screening"
        )

    core_data_complete = (
        len(core_data_gaps) == 0
    )

    if not core_data_complete:

        overall_rating = "incomplete_data"

        readable_gaps = ", ".join(
            core_data_gaps
        )

        conclusion = (
            "Housing OS identified the parcel and completed "
            "some screening, but the property cannot be given "
            "a reliable overall development rating because "
            "important core data is missing: "
            f"{readable_gaps}. Available constraints and "
            "opportunities should be treated as partial results."
        )

    elif major_constraint_count >= 2:

        overall_rating = "high_constraint"

        conclusion = (
            "The property may have development potential, but "
            "multiple major constraints could significantly affect "
            "the usable development area, cost, design, or approval."
        )

    elif major_constraint_count == 1:

        overall_rating = (
            "potential_with_major_constraint"
        )

        conclusion = (
            "The property shows preliminary development "
            "potential, but at least one major constraint "
            "could materially affect cost, design, or approval."
        )

    elif moderate_constraint_count >= 2:

        overall_rating = "moderate_constraint"

        conclusion = (
            "The property shows preliminary development "
            "potential with several moderate issues that "
            "require further review."
        )

    else:

        overall_rating = "preliminarily_promising"

        conclusion = (
            "The available screening data does not show a "
            "major fatal flaw, but additional parcel-wide and "
            "agency review is still required."
        )

    return {
        "overall_rating": overall_rating,
        "conclusion": conclusion,
        "preliminary_unit_estimate": estimated_units,
        "estimate_status": general_plan.get(
            "estimate_status"
        ),
        "opportunities": opportunities,
        "constraints": constraints,
        "missing_information": missing_information,
        "recommended_next_steps": recommended_next_steps,
        "major_constraint_count": major_constraint_count,
        "moderate_constraint_count": (
            moderate_constraint_count
        ),
        "core_data_complete": core_data_complete,
        "core_data_gaps": core_data_gaps,
        "status": (
            "incomplete"
            if not core_data_complete
            else "preliminary"
        ),
        "disclaimer": (
            "This is an automated preliminary screening, not "
            "a legal entitlement determination, engineering "
            "analysis, biological survey, wetland delineation, "
            "septic approval, utility will-serve confirmation, "
            "title review, easement determination, legal-access "
            "opinion, complete permit-history review, code-"
            "compliance clearance, boundary survey, appraisal, "
            "or guarantee "
            "of what may be approved or built."
        )
    }
