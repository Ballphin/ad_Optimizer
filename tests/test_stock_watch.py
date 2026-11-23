import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import stock_watch as sw  # noqa: E402


class DailyRateTest(unittest.TestCase):
    def test_average_over_window_counts_missing_days_as_zero(self):
        daily = {"2026-11-20": 4, "2026-11-22": 2}
        self.assertAlmostEqual(sw.daily_rate(daily, dt.date(2026, 11, 22), window=3), 2.0)

    def test_stockout_days_excluded_when_flagged(self):
        # 재고 0이라 못 판 날은 수요가 아니므로 제외 옵션
        daily = {"2026-11-20": 4, "2026-11-21": 0, "2026-11-22": 2}
        self.assertAlmostEqual(sw.daily_rate(daily, dt.date(2026, 11, 22), window=3, skip=["2026-11-21"]), 3.0)


class AssessTest(unittest.TestCase):
    def test_days_left_and_alert(self):
        r = sw.assess(stock=53, rate=3.7, lead_days=21, today=dt.date(2026, 11, 24))
        self.assertEqual(r["days_left"], 14)
        self.assertEqual(r["stockout_date"], "2026-12-08")
        self.assertTrue(r["alert"])
        # 리드타임 + 안전재고 7일 동안 팔 양 - 현재 재고
        self.assertEqual(r["reorder_qty"], round(3.7 * (21 + 7)) - 53)

    def test_no_alert_when_enough(self):
        r = sw.assess(stock=200, rate=3.0, lead_days=21, today=dt.date(2026, 11, 24))
        self.assertFalse(r["alert"])
        self.assertEqual(r["reorder_qty"], 0)

    def test_zero_rate(self):
        r = sw.assess(stock=5, rate=0, lead_days=21, today=dt.date(2026, 11, 24))
        self.assertIsNone(r["days_left"])
        self.assertFalse(r["alert"])


if __name__ == "__main__":
    unittest.main()
