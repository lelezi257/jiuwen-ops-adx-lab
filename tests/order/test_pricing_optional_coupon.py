import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'apps/order_api'))
from pricing import total_cents
class OptionalCouponTests(unittest.TestCase):
 def test_none_coupon_uses_list_price(self):self.assertEqual(total_cents(1,None),10000)
 def test_empty_coupon_uses_list_price(self):self.assertEqual(total_cents(3,''),30000)
 def test_whitespace_coupon_uses_list_price(self):self.assertEqual(total_cents(2,'   '),20000)
 def test_lowercase_coupon_is_normalized(self):self.assertEqual(total_cents(2,' save10 '),18000)
 def test_unknown_coupon_rejected(self):
  with self.assertRaises(ValueError):total_cents(1,'BOGUS')
