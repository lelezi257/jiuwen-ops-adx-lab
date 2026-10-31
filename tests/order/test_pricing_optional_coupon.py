import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'apps/order_api'))
from pricing import total_cents
class OptionalCouponTests(unittest.TestCase):
 def test_none_coupon(self):self.assertEqual(total_cents(3,None),30000)
 def test_blank_coupon(self):self.assertEqual(total_cents(1,'   '),10000)
 def test_valid_coupon_with_padding(self):self.assertEqual(total_cents(2,' save10 '),18000)
 def test_invalid_coupon_still_rejected(self):
  with self.assertRaises(ValueError):total_cents(1,'FREESHIP')
