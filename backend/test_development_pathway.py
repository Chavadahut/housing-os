import unittest

from development_pathway import build_development_pathway


class DevelopmentPathwayTests(unittest.TestCase):
    def test_two_home_constrained_pathway(self):
        result = build_development_pathway({
            "zoning": {"status": "found", "use_regulation": "Single-family residential"},
            "current_land_use": {"description": "Residential"},
            "development_scenario": {"density": {"preliminary_max_units": 2}},
            "fire_hazard": {"status": "found", "risk_level": "very_high"},
            "habitat": {"status": "found", "constraint_level": "high", "constrained_acres": 1},
            "wetlands": {"status": "found", "hydric_soils_indicator": True},
            "utilities": {"water_district": "Test Water District", "inside_sanitation_district": False},
            "road_access": {"legal_access_confirmed": False},
            "easements": {"title_review_required": True},
        })
        self.assertEqual(result["scenario_name"], "2 Single-Family Homes")
        self.assertIn("Minor Subdivision", result["entitlements"])
        self.assertEqual(result["approval_complexity"], "HIGH")
        self.assertEqual(result["biggest_unknown"], "Wastewater feasibility")
        self.assertIn("Biological resources survey", result["studies_likely_required"])
        self.assertTrue(result["concept_eligibility"]["eligible"])
        option_ids = [option["id"] for option in result["concept_eligibility"]["options"]]
        self.assertEqual(option_ids, ["one_home", "two_homes", "lot_subdivision", "home_plus_adu", "custom_project"])

    def test_concept_creation_is_gated_without_supported_use(self):
        result = build_development_pathway({
            "zoning": {"status": "found", "use_regulation": "Commercial"},
            "current_land_use": {"description": "Retail store"},
            "development_scenario": {"density": {"preliminary_max_units": 8}},
        })
        eligibility = result["concept_eligibility"]
        self.assertFalse(eligibility["eligible"])
        self.assertEqual(eligibility["options"], [])
        self.assertEqual(eligibility["status"], "incompatible")
        self.assertFalse(eligibility["bypass_allowed"])

    def test_vacant_use_is_neutral_when_plan_supports_residential(self):
        result = build_development_pathway({
            "zoning": {"status": "found", "code": "RMV4"},
            "general_plan": {"designation": "Village Residential (VR-20)"},
            "current_land_use": {"description": "Vacant and Undeveloped Land"},
            "development_scenario": {"density": {"preliminary_max_units": 15}},
        })
        eligibility = result["concept_eligibility"]
        self.assertTrue(eligibility["eligible"])
        self.assertEqual(eligibility["determination"], "supported")

    def test_unknown_zoning_allows_assumption_path(self):
        result = build_development_pathway({
            "zoning": {"status": "manual_review_required"},
            "general_plan": {"designation": "Residential"},
            "current_land_use": {"description": "Vacant"},
            "development_scenario": {"density": {"preliminary_max_units": 2}},
        })
        eligibility = result["concept_eligibility"]
        self.assertFalse(eligibility["eligible"])
        self.assertEqual(eligibility["status"], "assumption_required")
        self.assertTrue(eligibility["bypass_allowed"])

    def test_concept_options_never_exceed_density_screen(self):
        result = build_development_pathway({
            "zoning": {"status": "found", "use_regulation": "Multifamily residential"},
            "current_land_use": {"description": "Residential"},
            "development_scenario": {"density": {"preliminary_max_units": 7}},
        })
        options = result["concept_eligibility"]["options"]
        self.assertEqual(options[-1]["units"], 7)
        self.assertTrue(all(option["units"] <= 7 for option in options))


if __name__ == "__main__":
    unittest.main()
