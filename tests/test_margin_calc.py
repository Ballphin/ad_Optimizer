import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from margin_calc import Product  # noqa: E402


def simple(**kw):
    base = dict(name="t", channel="naver", price=10000, cogs=5000, vat_inclusive=False)
    base.update(kw)
    return Product(**base)


class MarginCalcTest(unittest.TestCase):
    def test_contribution_without_vat(self):
        p = simple(shipping=1000, fee_rate=0.10)
        # 10000 - 5000 - 1000 - 1000
        self.assertAlmostEqual(p.contribution, 3000)
        self.assertAlmostEqual(p.margin_rate, 0.30)

    def test_vat_approximation(self):
        p = simple(vat_inclusive=True)
        self.assertAlmostEqual(p.vat, 5000 / 11)

    def test_breakeven_roas(self):
        p = simple(fee_rate=0.25)  # margin 25%
        self.assertAlmostEqual(p.breakeven_roas(), 400)

    def test_breakeven_infinite_when_no_margin(self):
        p = simple(cogs=10000)
        self.assertEqual(p.breakeven_roas(), float("inf"))

    def test_target_roas(self):
        p = simple(fee_rate=0.20)  # margin 30%
        self.assertAlmostEqual(p.target_roas(0.10), 500)

    def test_max_cpc(self):
        p = simple(fee_rate=0.20)  # margin 30%, price 10000, cvr 2% -> 60
        self.assertAlmostEqual(p.max_cpc(0.02), 60)
        self.assertAlmostEqual(p.max_cpc(0.02, 0.10), 40)

    def test_profit_at_breakeven_is_zero(self):
        p = simple(fee_rate=0.25)
        self.assertAlmostEqual(p.profit_at_roas(400, 100000), 0)
        self.assertLess(p.profit_at_roas(300, 100000), 0)


class NetVatTest(unittest.TestCase):
    """사장님 시트 방식: 부가세·종소세는 '이익'에 붙으므로 손익분기점은 세전 공헌이익으로 정해진다."""

    def pillow(self, **kw):
        base = dict(name="필로우네이션", channel="coupang", price=59400, cogs=19510,
                    shipping=5150, fee_rate=0.10, vat_method="net", income_tax_rate=0.15)
        base.update(kw)
        return Product(**base)

    def test_contribution_excludes_vat(self):
        p = self.pillow()
        self.assertAlmostEqual(p.vat, 0)
        self.assertAlmostEqual(p.contribution, 28800)  # 59400-19510-5150-5940

    def test_breakeven_roas_from_pre_tax_contribution(self):
        self.assertAlmostEqual(self.pillow().breakeven_roas(), 59400 / 28800 * 100)

    def test_after_tax_profit_per_unit(self):
        p = self.pillow()
        # (28800 - 8200) * (1 - 1/11) * (1 - 0.15)
        self.assertAlmostEqual(p.after_tax_profit(8200), 20600 * (10 / 11) * 0.85)
        self.assertLess(p.after_tax_profit(30000), 0)

    def test_unit_ad_cost_to_roas(self):
        self.assertAlmostEqual(self.pillow().roas_from_unit_ad(8200), 59400 / 8200 * 100)


if __name__ == "__main__":
    unittest.main()
