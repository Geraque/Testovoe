import unittest
from decimal import Decimal

from common import decimal_number, wagon_count


class NumberTests(unittest.TestCase):
    def test_supported_decimal_representations(self):
        for value in ("15,90", " 15.9 ", Decimal("15.900"), 15.9):
            with self.subTest(value=value):
                self.assertEqual(decimal_number(value), Decimal("15.9"))

    def test_invalid_and_nonfinite_numbers_rejected(self):
        for value in ("NaN", "Infinity", "-Infinity", "text", "", None, True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    decimal_number(value)

    def test_wagon_count_is_strictly_integer(self):
        self.assertEqual(wagon_count(1), 1)
        self.assertEqual(wagon_count(0, allow_zero=True), 0)
        for value in (0, -1, 1.0, "1", True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    wagon_count(value)
