import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'apps/order_api'))
from pricing import total_cents


class CouponNoneRegressionTests(unittest.TestCase):
    """Regression: omitted/None coupon must not raise AttributeError (500)."""

    def test_none_coupon_is_allowed(self):
        self.assertEqual(total_cents(3, None), 30000)

    def test_none_coupon_with_single_item(self):
        self.assertEqual(total_cents(1, None), 10000)

    def test_empty_coupon_is_allowed(self):
        self.assertEqual(total_cents(2, ''), 20000)

    def test_whitespace_coupon_is_allowed(self):
        self.assertEqual(total_cents(2, '   '), 20000)

    def test_lowercase_coupon_is_normalized(self):
        self.assertEqual(total_cents(2, ' save10 '), 18000)

    def test_invalid_coupon_still_rejected(self):
        with self.assertRaises(ValueError):
            total_cents(1, 'BOGUS')

    def test_none_coupon_matches_empty_coupon(self):
        for quantity in (1, 5, 100):
            self.assertEqual(total_cents(quantity, None), total_cents(quantity, ''))


if __name__ == '__main__':
    unittest.main()
