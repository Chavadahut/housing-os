import unittest

from development_scenario import (
    _estimate_zoning_units,
    _minimum_lot_size_square_feet,
)


class MinimumLotSizeTests(unittest.TestCase):
    def test_acres_are_converted_to_square_feet(self):
        minimum = _minimum_lot_size_square_feet("2AC")

        self.assertEqual(minimum, 87_120)
        self.assertEqual(
            _estimate_zoning_units(226_512, minimum),
            2,
        )

    def test_spaced_acre_value_is_supported(self):
        self.assertEqual(
            _minimum_lot_size_square_feet("2 acres"),
            87_120,
        )

    def test_square_feet_are_not_converted(self):
        self.assertEqual(
            _minimum_lot_size_square_feet("6,000 SF"),
            6_000,
        )

    def test_unknown_value_returns_none(self):
        self.assertIsNone(
            _minimum_lot_size_square_feet("-")
        )


if __name__ == "__main__":
    unittest.main()
