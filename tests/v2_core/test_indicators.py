import math
import unittest

import v2_helpers  # noqa: F401  (blocks network)
from v2_core.indicators import rsi_wilder, shd_by_date, sma_running


class IndicatorTests(unittest.TestCase):
    def test_rsi_hand_values(self):
        # n=2, a=[10,11,10,12]: i=1 g=.5 l=0; i=2 g=.5 l=.5 -> 50; i=3 g=1.25 l=.25 -> 100-100/6
        out = rsi_wilder([10.0, 11.0, 10.0, 12.0], n=2)
        self.assertIsNone(out[0])
        self.assertIsNone(out[1])
        self.assertEqual(out[2], 50.0)
        self.assertAlmostEqual(out[3], 100 - 100 / 6, places=12)

    def test_rsi_flat_and_monotonic(self):
        self.assertEqual(rsi_wilder([5.0] * 20)[14], 50.0)
        self.assertEqual(rsi_wilder([float(i) for i in range(1, 25)])[14], 100.0)
        self.assertEqual(rsi_wilder([5.0] * 20)[13], None)

    def test_sma_running_hand_values(self):
        out = sma_running([1.0, 2.0, 3.0, 4.0, 5.0], window=3)
        self.assertEqual(out[:2], [None, None])
        self.assertEqual(out[2:], [2.0, 3.0, 4.0])

    def test_shd_uses_common_sessions_and_missing_is_none(self):
        dates = ["2024-01-%02d" % d for d in range(1, 8)]
        spy = {d: 100.0 + i for i, d in enumerate(dates)}
        ief = {d: 50.0 for d in dates}
        out = shd_by_date(dates, spy, ief, set(dates), lookback=2)
        self.assertIsNone(out[dates[0]])
        self.assertIsNone(out[dates[1]])
        # d[2]: 100*((102/100) - (50/50)) = 2.0
        self.assertAlmostEqual(out[dates[2]], 2.0, places=12)
        spy[dates[4]] = None                      # blank value is missing, not 0
        out2 = shd_by_date(dates, spy, ief, set(dates), lookback=2)
        self.assertIsNone(out2[dates[4]])
        self.assertIsNone(out2[dates[6]])         # uses dates[4] as the base
        self.assertTrue(all(v is None or math.isfinite(v) for v in out2.values()))


if __name__ == "__main__":
    unittest.main()
