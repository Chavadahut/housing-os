from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class PropertyLookupRequest(BaseModel):
    address: str


class Jurisdiction(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    zoning_connector: Optional[str] = None
    status: Optional[str] = None


class LotSize(BaseModel):
    acreage: Optional[float] = None
    square_feet: Optional[float] = None
    status: Optional[str] = None
    source: Optional[str] = None
    message: Optional[str] = None


class LandUseBreakdown(BaseModel):
    code: Optional[int] = None
    category: Optional[str] = None
    description: Optional[str] = None
    parcel_percent: Optional[float] = None
    estimated_acres: Optional[float] = None


class CurrentLandUse(BaseModel):
    code: Optional[int] = None
    category: Optional[str] = None
    description: Optional[str] = None
    dominant_code: Optional[int] = None
    dominant_category: Optional[str] = None
    dominant_description: Optional[str] = None
    land_use_breakdown: list[LandUseBreakdown] = Field(
        default_factory=list
    )
    mixed_land_use: Optional[bool] = None
    parcel_overlap_percent: Optional[float] = None
    status: Optional[str] = None
    source: Optional[str] = None
    message: Optional[str] = None
    lookup_method: Optional[str] = None
    search_distance_feet: Optional[int] = None


class FloodHazard(BaseModel):
    zone: Optional[str] = None
    zone_subtype: Optional[str] = None
    special_flood_hazard_area: Optional[bool] = None
    risk_level: Optional[str] = None
    annual_chance: Optional[str] = None
    base_flood_elevation: Optional[float] = None
    depth: Optional[float] = None
    length_unit: Optional[str] = None
    development_warning: Optional[str] = None
    status: Optional[str] = None
    source: Optional[str] = None
    message: Optional[str] = None
    lookup_method: Optional[str] = None


class FireHazard(BaseModel):
    hazard_class: Optional[str] = None
    hazard_code: Optional[int] = None
    description: Optional[str] = None
    risk_level: Optional[str] = None
    development_warning: Optional[str] = None
    dataset_note: Optional[str] = None
    status: Optional[str] = None
    source: Optional[str] = None
    message: Optional[str] = None
    lookup_method: Optional[str] = None


class Terrain(BaseModel):
    center_elevation_feet: Optional[float] = None
    minimum_sample_elevation_feet: Optional[float] = None
    maximum_sample_elevation_feet: Optional[float] = None
    elevation_change_feet: Optional[float] = None
    estimated_slope_percent: Optional[float] = None
    estimated_slope_degrees: Optional[float] = None
    terrain_class: Optional[str] = None
    development_warning: Optional[str] = None
    sample_distance_feet: Optional[int] = None
    analysis_scope: Optional[str] = None
    slope_sample_count: Optional[int] = None
    slope_sample_geojson: Optional[
        dict[str, Any]
    ] = None
    slope_zone_count: Optional[int] = None
    slope_zone_geojson: Optional[
        dict[str, Any]
    ] = None
    status: Optional[str] = None
    source: Optional[str] = None
    message: Optional[str] = None


class HabitatBreakdown(BaseModel):
    habitat_value: Optional[str] = None
    sample_count: Optional[int] = None
    parcel_percent: Optional[float] = None
    estimated_acres: Optional[float] = None
    constraint_level: Optional[str] = None


class Habitat(BaseModel):
    habitat_value: Optional[str] = None
    dominant_habitat_value: Optional[str] = None
    grid_code: Optional[float] = None
    habitat_id: Optional[float] = None

    habitat_breakdown: list[
        HabitatBreakdown
    ] = Field(
        default_factory=list
    )

    parcel_overlap_percent: Optional[float] = None
    constrained_acres: Optional[float] = None
    unconstrained_acres: Optional[float] = None
    intersecting_feature_count: Optional[int] = None
    sample_count: Optional[int] = None
    successful_sample_count: Optional[int] = None

    constraint_level: Optional[str] = None
    development_warning: Optional[str] = None
    status: Optional[str] = None
    source: Optional[str] = None
    message: Optional[str] = None
    lookup_method: Optional[str] = None
    search_distance_feet: Optional[int] = None
    analysis_scope: Optional[str] = None


class Wetlands(BaseModel):
    mapped_wetland: Optional[bool] = None
    parcel_intersection_detected: Optional[bool] = None
    wetland_type: Optional[str] = None

    wetland_types: list[str] = Field(
        default_factory=list
    )

    description: Optional[str] = None
    holland_code: Optional[str] = None
    wetland_indicator: Optional[bool] = None
    vernal_pool_indicator: Optional[bool] = None
    hydric_soils_indicator: Optional[bool] = None

    parcel_overlap_percent: Optional[float] = None
    constrained_acres: Optional[float] = None
    unconstrained_acres: Optional[float] = None
    intersecting_feature_count: Optional[int] = None
    sample_count: Optional[int] = None
    successful_sample_count: Optional[int] = None

    constraint_level: Optional[str] = None
    development_warning: Optional[str] = None
    status: Optional[str] = None
    source: Optional[str] = None
    message: Optional[str] = None
    lookup_method: Optional[str] = None
    search_distance_feet: Optional[int] = None
    analysis_scope: Optional[str] = None


class Utilities(BaseModel):
    water_district: Optional[str] = None
    water_district_fund: Optional[int] = None
    inside_water_district: Optional[bool] = None
    water_screening: Optional[str] = None

    sanitation_district: Optional[str] = None
    sanitation_district_fund: Optional[int] = None
    inside_sanitation_district: Optional[bool] = None

    county_wastewater_permit_found: Optional[bool] = None
    wastewater_permits: list[str] = Field(
        default_factory=list
    )

    sewer_screening: Optional[str] = None
    septic_screening: Optional[str] = None
    constraint_level: Optional[str] = None
    development_warning: Optional[str] = None

    status: Optional[str] = None
    source: Optional[str] = None
    message: Optional[str] = None
    analysis_scope: Optional[str] = None


class Easements(BaseModel):
    open_space_easement_screened: Optional[bool] = None
    open_space_easement_found: Optional[bool] = None
    open_space_easement_count: Optional[int] = None

    open_space_easements: list[
        dict[str, Any]
    ] = Field(
        default_factory=list
    )

    wastewater_easement_screened: Optional[bool] = None
    wastewater_easement_found: Optional[bool] = None
    wastewater_easement_count: Optional[int] = None

    wastewater_easements: list[
        dict[str, Any]
    ] = Field(
        default_factory=list
    )

    access_easement_screened: Optional[bool] = None
    access_easement_found: Optional[bool] = None
    legal_access_confirmed: Optional[bool] = None
    title_review_required: Optional[bool] = None

    constraint_level: Optional[str] = None
    status: Optional[str] = None
    source: Optional[str] = None
    message: Optional[str] = None
    analysis_scope: Optional[str] = None


class RoadAccess(BaseModel):
    nearest_road_name: Optional[str] = None
    nearest_road_type: Optional[str] = None
    road_segment_status: Optional[str] = None
    road_dedication_status: Optional[str] = None
    fire_drivable: Optional[bool] = None
    parcel_center_to_road_feet: Optional[float] = None
    parcel_edge_to_road_feet: Optional[float] = None
    mapped_road_found: Optional[bool] = None

    county_maintained_road_found: Optional[bool] = None
    county_maintained_road_name: Optional[str] = None
    county_road_jurisdiction: Optional[str] = None
    county_road_asset_status: Optional[str] = None
    county_road_distance_feet: Optional[int] = None

    nearest_road_is_county_maintained: Optional[bool] = None
    direct_frontage_confirmed: Optional[bool] = None

    frontage_edge_found: Optional[bool] = None
    frontage_road_name: Optional[str] = None
    frontage_length_feet: Optional[float] = None
    frontage_confidence: Optional[str] = None
    frontage_detection_method: Optional[str] = None
    frontage_edge_index: Optional[int] = None
    rear_edge_index: Optional[int] = None
    rear_edge_length_feet: Optional[float] = None

    nearest_road_lookup_status: Optional[str] = None
    maintained_road_lookup_status: Optional[str] = None
    frontage_lookup_status: Optional[str] = None
    partial_results: Optional[bool] = None

    preliminary_access_level: Optional[str] = None
    constraint_level: Optional[str] = None
    development_warning: Optional[str] = None

    legal_access_confirmed: Optional[bool] = None
    easement_review_status: Optional[str] = None

    status: Optional[str] = None
    source: Optional[str] = None
    message: Optional[str] = None
    analysis_scope: Optional[str] = None


class DiscretionaryApplication(BaseModel):
    record_number: Optional[str] = None
    record_type: Optional[str] = None
    status: Optional[str] = None
    project_name: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None
    apn: Optional[str] = None
    opened_date: Optional[str] = None
    completed_date: Optional[str] = None
    applicant: Optional[str] = None
    assigned_staff: Optional[str] = None


class PermitHistory(BaseModel):
    discretionary_application_found: Optional[bool] = None
    discretionary_application_count: Optional[int] = None

    discretionary_applications: list[
        DiscretionaryApplication
    ] = Field(
        default_factory=list
    )

    building_permit_history_checked: Optional[bool] = None
    building_permit_found: Optional[bool] = None
    building_permit_count: Optional[int] = None

    building_permit_records: list[dict[str, Any]] = Field(
        default_factory=list
    )

    building_inspection_history_checked: Optional[bool] = None
    building_inspection_count: Optional[int] = None

    building_inspection_records: list[dict[str, Any]] = Field(
        default_factory=list
    )

    code_compliance_history_checked: Optional[bool] = None

    code_compliance_records: list[dict[str, Any]] = Field(
        default_factory=list
    )

    code_compliance_research_status: Optional[str] = None
    code_compliance_search_url: Optional[str] = None
    code_compliance_source: Optional[str] = None
    code_compliance_message: Optional[str] = None

    permit_history_level: Optional[str] = None
    constraint_level: Optional[str] = None
    development_warning: Optional[str] = None
    manual_research_required: Optional[bool] = None

    citizen_access_url: Optional[str] = None
    public_records_url: Optional[str] = None

    status: Optional[str] = None
    source: Optional[str] = None
    message: Optional[str] = None
    analysis_scope: Optional[str] = None


class GeneralPlan(BaseModel):
    designation: Optional[str] = None
    designation_code: Optional[Any] = None
    description: Optional[str] = None

    raw_density: Optional[Any] = None
    raw_potential_units: Optional[Any] = None

    maximum_density: Optional[float] = None
    gross_acres_per_unit: Optional[float] = None
    estimated_maximum_units: Optional[int] = None
    estimate_status: Optional[str] = None

    mixed_use: Optional[str] = None
    mixed_use_name: Optional[str] = None
    general_plan_code: Optional[Any] = None
    case_number: Optional[str] = None
    adoption_date: Optional[Any] = None

    jurisdiction: Optional[str] = None
    status: Optional[str] = None
    source: Optional[str] = None
    message: Optional[str] = None
    warning: Optional[str] = None

    lookup_method: Optional[str] = None
    search_distance_feet: Optional[int] = None

    @field_validator("mixed_use", mode="before")
    @classmethod
    def normalize_mixed_use(cls, value):
        if value is None:
            return None

        if isinstance(value, bool):
            return "YES" if value else "NO"

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if value == 1:
                return "YES"
            if value == 0:
                return "NO"

        if isinstance(value, str):
            cleaned = value.strip()

            if not cleaned:
                return None

            normalized = cleaned.upper()

            if normalized in {"YES", "Y", "TRUE", "T", "1"}:
                return "YES"

            if normalized in {"NO", "N", "FALSE", "F", "0"}:
                return "NO"

            return cleaned

        return str(value)

    @field_validator("maximum_density", mode="before")
    @classmethod
    def normalize_maximum_density(cls, value):
        if value is None:
            return None

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)

        if isinstance(value, str):
            cleaned = value.strip()

            if not cleaned:
                return None

            try:
                return float(cleaned)
            except ValueError:
                return None

        return None


class Zoning(BaseModel):
    code: Optional[str] = None
    use_regulation: Optional[str] = None
    density: Optional[str] = None
    minimum_lot_size: Optional[str] = None
    building_type: Optional[str] = None
    maximum_floor_area: Optional[str] = None
    floor_area_ratio: Optional[str] = None
    height: Optional[str] = None
    coverage: Optional[str] = None
    setback: Optional[str] = None
    open_space: Optional[str] = None
    animal_regulations: Optional[str] = None
    special_regulations: Optional[str] = None
    ordinance: Optional[str] = None
    case_number: Optional[str] = None
    implementation_date: Optional[Any] = None
    jurisdiction: Optional[str] = None
    status: Optional[str] = None
    source: Optional[str] = None
    message: Optional[str] = None
    lookup_method: Optional[str] = None
    search_distance_feet: Optional[int] = None


class BuildableArea(BaseModel):
    parcel_acres: Optional[float] = None
    parcel_geometry_acres: Optional[float] = None
    acreage_difference_percent: Optional[float] = None
    acreage_consistency_status: Optional[str] = None
    acreage_warning: Optional[str] = None

    setback_designator: Optional[str] = None
    front_setback_centerline_feet: Optional[float] = None
    interior_side_setback_feet: Optional[float] = None
    exterior_side_setback_centerline_feet: Optional[float] = None
    rear_setback_feet: Optional[float] = None

    minimum_uniform_setback_feet: Optional[float] = None
    minimum_setback_screened_acres: Optional[float] = None
    minimum_setback_screened_percent: Optional[float] = None

    habitat_review_acres: Optional[float] = None
    wetland_indicator_acres: Optional[float] = None

    preliminary_buildable_acres: Optional[float] = None
    buildable_percent: Optional[float] = None

    frontage_identified: Optional[bool] = None
    frontage_road_name: Optional[str] = None
    frontage_length_feet: Optional[float] = None
    parcel_edge_to_road_feet: Optional[float] = None
    frontage_confidence: Optional[str] = None

    front_setback_applied_feet: Optional[float] = None
    rear_setback_applied_feet: Optional[float] = None

    directional_setback_screened_acres: Optional[float] = None
    directional_setback_screened_percent: Optional[float] = None

    setback_envelope_geojson: Optional[
        dict[str, Any]
    ] = None
    setback_envelope_status: Optional[str] = None
    setback_envelope_message: Optional[str] = None

    exact_setback_envelope_available: Optional[bool] = None

    constraint_level: Optional[str] = None
    development_warning: Optional[str] = None

    status: Optional[str] = None
    source: Optional[str] = None
    message: Optional[str] = None
    analysis_scope: Optional[str] = None


class FeasibilitySummary(BaseModel):
    overall_rating: Optional[str] = None
    conclusion: Optional[str] = None
    preliminary_unit_estimate: Optional[int] = None
    estimate_status: Optional[str] = None

    opportunities: list[str] = Field(
        default_factory=list
    )

    constraints: list[str] = Field(
        default_factory=list
    )

    missing_information: list[str] = Field(
        default_factory=list
    )

    recommended_next_steps: list[str] = Field(
        default_factory=list
    )

    major_constraint_count: Optional[int] = None
    moderate_constraint_count: Optional[int] = None
    status: Optional[str] = None
    disclaimer: Optional[str] = None


class MapGeometry(BaseModel):
    simplified_parcel_boundary: Optional[
        dict[str, Any]
    ] = None
    parcel_center: Optional[dict[str, Any]] = None
    frontage_edge: Optional[dict[str, Any]] = None
    rear_edge: Optional[dict[str, Any]] = None
    setback_envelope: Optional[dict[str, Any]] = None
    slope_samples: Optional[dict[str, Any]] = None
    slope_zones: Optional[dict[str, Any]] = None
    bounds: Optional[list[float]] = None
    status: Optional[str] = None
    source: Optional[str] = None
    message: Optional[str] = None
    disclaimer: Optional[str] = None


class DevelopmentScenarioParcel(BaseModel):
    lot_acres: Optional[float] = None
    lot_square_feet: Optional[float] = None
    buildable_acres: Optional[float] = None
    buildable_square_feet: Optional[float] = None
    buildable_percent: Optional[float] = None
    setback_envelope_acres: Optional[float] = None
    setback_envelope_square_feet: Optional[float] = None
    setback_envelope_percent: Optional[float] = None


class DevelopmentScenarioDensity(BaseModel):
    general_plan_max_units: Optional[int] = None
    zoning_lot_size_screen_units: Optional[int] = None
    preliminary_max_units: Optional[int] = None
    minimum_lot_size_square_feet: Optional[float] = None


class LikelyDevelopment(BaseModel):
    primary_use: Optional[str] = None
    estimated_units: Optional[int] = None
    adu_potential: Optional[str] = None
    lot_split_potential: Optional[str] = None


class DevelopmentSiteConstraints(BaseModel):
    flood: Optional[str] = None
    fire: Optional[str] = None
    slope: Optional[str] = None
    habitat: Optional[str] = None
    wetlands: Optional[str] = None
    access: Optional[str] = None
    utilities: Optional[str] = None
    easements: Optional[str] = None


class DevelopmentScenario(BaseModel):
    scenario: Optional[str] = None
    confidence: Optional[str] = None
    parcel: Optional[DevelopmentScenarioParcel] = None
    density: Optional[DevelopmentScenarioDensity] = None
    likely_development: Optional[LikelyDevelopment] = None
    site_constraints: Optional[DevelopmentSiteConstraints] = None

    major_flags: list[str] = Field(
        default_factory=list
    )

    next_steps: list[str] = Field(
        default_factory=list
    )

    reasoning: list[str] = Field(
        default_factory=list
    )

    status: Optional[str] = None
    disclaimer: Optional[str] = None


class PathwayFinding(BaseModel):
    label: str
    status: str
    detail: Optional[str] = None


class SiteConceptOption(BaseModel):
    id: str
    label: str
    description: Optional[str] = None
    units: Optional[int] = None


class ConceptEligibility(BaseModel):
    eligible: bool = False
    status: Optional[str] = None
    screened_max_units: Optional[int] = None
    options: list[SiteConceptOption] = Field(default_factory=list)
    assumption_options: list[SiteConceptOption] = Field(default_factory=list)
    bypass_allowed: bool = False
    blockers: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    determination: Optional[str] = None
    basis: Optional[str] = None


class DevelopmentPathway(BaseModel):
    title: Optional[str] = None
    scenario_label: Optional[str] = None
    scenario_name: Optional[str] = None
    likely_entitlement: Optional[str] = None
    entitlements: list[str] = Field(default_factory=list)
    planning_findings: list[PathwayFinding] = Field(default_factory=list)
    environmental_findings: list[PathwayFinding] = Field(default_factory=list)
    studies_likely_required: list[str] = Field(default_factory=list)
    infrastructure_findings: list[PathwayFinding] = Field(default_factory=list)
    approval_complexity: Optional[str] = None
    preconstruction_timeline: Optional[str] = None
    confidence_percent: Optional[int] = None
    biggest_unknown: Optional[str] = None
    concept_eligibility: Optional[ConceptEligibility] = None
    status: Optional[str] = None
    disclaimer: Optional[str] = None


class Parcel(BaseModel):
    apn: Optional[str] = None
    address: Optional[str] = None
    zip: Optional[str] = None
    community: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    lot_size: Optional[LotSize] = None
    current_land_use: Optional[CurrentLandUse] = None
    general_plan: Optional[GeneralPlan] = None
    flood_hazard: Optional[FloodHazard] = None
    fire_hazard: Optional[FireHazard] = None
    terrain: Optional[Terrain] = None
    habitat: Optional[Habitat] = None
    wetlands: Optional[Wetlands] = None
    utilities: Optional[Utilities] = None
    road_access: Optional[RoadAccess] = None
    easements: Optional[Easements] = None
    permit_history: Optional[PermitHistory] = None
    zoning: Optional[Zoning] = None
    buildable_area: Optional[BuildableArea] = None
    map_geometry: Optional[MapGeometry] = None

    feasibility_summary: Optional[
        FeasibilitySummary
    ] = None

    development_scenario: Optional[
        DevelopmentScenario
    ] = None
    development_pathway: Optional[DevelopmentPathway] = None


class PropertySearchResponse(BaseModel):
    address: str
    parcel_count: int
    parcels: list[Parcel]
    source: str
    status: Optional[str] = None
    message: Optional[str] = None
    jurisdiction: Optional[Jurisdiction] = None
