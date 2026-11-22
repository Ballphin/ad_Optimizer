import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import ad_report as ar  # noqa: E402

NAVER_CSV = (
    "검색어별 전환 보고서 30일,(2026.10.01~2026.10.30)\n"
    "캠페인,광고그룹,검색어,노출수,클릭수,\"평균클릭비용(VAT포함,원)\",\"총비용(VAT포함,원)\","
    "총 전환매출액(원),구매완료 전환매출액(원),구매완료 전환수\n"
    "쇼핑,임산부베개,임산부베개,10000,200,\"1,800\",\"360,000\",\"1,500,000\",\"637,000\",13\n"
    "쇼핑,임산부베개,바디필로우 임산부,3000,40,\"125\",\"5,000\",\"40,000\",\"29,800\",1\n"
    "쇼핑,임산부베개,베개,8000,60,\"1,000\",\"60,000\",\"90,000\",0,0\n"
    "쇼핑,임산부베개,u자 바디필로우,500,5,\"900\",\"4,500\",0,0,0\n"
)

COUPANG_CSV = (
    "캠페인명,광고그룹,광고 노출 지면,키워드,노출수,클릭수,광고비,총 주문수(14일),총 전환매출액(14일)\n"
    "매출최적화,기본,검색 영역,임산부베개,5000,100,\"100,000\",8,\"400,000\"\n"
    "매출최적화,기본,비검색 영역,-,9000,150,\"150,000\",3,\"150,000\"\n"
)


def write(text, suffix=".csv"):
    f = tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False, encoding="utf-8-sig")
    f.write(text)
    f.close()
    return f.name


class ParseTest(unittest.TestCase):
    def test_num(self):
        self.assertEqual(ar.num("1,234"), 1234.0)
        self.assertEqual(ar.num("-"), 0.0)
        self.assertEqual(ar.num(""), 0.0)
        self.assertEqual(ar.num("12.5%"), 12.5)

    def test_naver_skips_title_row_and_prefers_purchase_revenue(self):
        rows, warnings = ar.load_rows(write(NAVER_CSV), platform="naver")
        self.assertEqual(len(rows), 4)
        first = rows[0]
        self.assertEqual(first.keyword, "임산부베개")
        self.assertEqual(first.cost, 360000)
        # 장바구니 포함 '총 전환매출액'(1,500,000)이 아니라 구매완료(637,000)를 써야 한다
        self.assertEqual(first.revenue, 637000)
        self.assertEqual(first.orders, 13)
        self.assertEqual(warnings, [])

    def test_naver_warns_when_only_total_conversion_present(self):
        csv = ("캠페인,광고그룹,검색어,클릭수,\"총비용(VAT포함,원)\",총 전환매출액(원)\n"
               "a,b,c,10,\"1,000\",\"5,000\"\n")
        rows, warnings = ar.load_rows(write(csv), platform="naver")
        self.assertEqual(rows[0].revenue, 5000)
        self.assertTrue(any("장바구니" in w for w in warnings))

    def test_coupang_columns_and_placement(self):
        rows, _ = ar.load_rows(write(COUPANG_CSV), platform="coupang")
        self.assertEqual(rows[0].placement, "검색 영역")
        self.assertEqual(rows[1].revenue, 150000)
        self.assertEqual(rows[1].orders, 3)


class ClassifyTest(unittest.TestCase):
    def setUp(self):
        rows, _ = ar.load_rows(write(NAVER_CSV), platform="naver")
        self.result = ar.analyze(rows, breakeven=250, target=350, min_clicks=30)
        self.by_kw = {r.keyword: r for r in self.result.rows}

    def test_actions(self):
        self.assertEqual(self.by_kw["임산부베개"].action, ar.CUT)        # 177% < 250%
        self.assertEqual(self.by_kw["바디필로우 임산부"].action, ar.GROW)  # 596%
        self.assertEqual(self.by_kw["베개"].action, ar.EXCLUDE)          # 60클릭 전환 0
        self.assertEqual(self.by_kw["u자 바디필로우"].action, ar.WAIT)    # 5클릭

    def test_totals_and_loss(self):
        r = self.result
        self.assertEqual(r.total_cost, 429500)
        self.assertEqual(r.total_revenue, 666800)
        # 공헌이익률 = 100/250 = 40%. 임산부베개 손실 = 360,000 - 637,000*0.4 = 105,200
        # 베개 손실 = 60,000. 합계 165,200
        self.assertAlmostEqual(r.loss_from_bad, 165200)

    def test_markdown_mentions_actions(self):
        md = ar.to_markdown(self.result, title="t")
        self.assertIn("제외", md)
        self.assertIn("임산부베개", md)


class PlacementTest(unittest.TestCase):
    def test_coupang_placement_summary(self):
        rows, _ = ar.load_rows(write(COUPANG_CSV), platform="coupang")
        summary = ar.placement_summary(rows)
        self.assertAlmostEqual(summary["검색 영역"]["roas"], 400.0)
        self.assertAlmostEqual(summary["비검색 영역"]["roas"], 100.0)


if __name__ == "__main__":
    unittest.main()
