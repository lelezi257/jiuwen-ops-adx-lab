import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'apps/order_api'))
from pricing import total_cents
class MissingCouponRegressionTests(unittest.TestCase):
 def test_missing_coupon_is_accepted(self):self.assertEqual(total_cents(2,None),20000)
 def test_blank_and_padded_coupon(self):
  self.assertEqual(total_cents(1,''),10000)
  self.assertEqual(total_cents(1,'  '),10000)
  self.assertEqual(total_cents(1,' save10 '),9000)
 def test_invalid_coupon_still_rejected(self):
  with self.assertRaises(ValueError):total_cents(1,'BOGUS')
