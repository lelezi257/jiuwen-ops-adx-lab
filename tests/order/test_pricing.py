import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'apps/order_api'))
from pricing import total_cents
class HistoricalTests(unittest.TestCase):
 def test_valid_coupon(self):self.assertEqual(total_cents(2,'SAVE10'),18000)
