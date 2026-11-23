import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import rank_tracker as rt  # noqa: E402


class FindRankTest(unittest.TestCase):
    def test_finds_our_mall_positions(self):
        items = [{"mallName": "해피테일즈", "title": "임산부 바디필로우"},
                 {"mallName": "네이버", "title": "<b>필로우네이션</b> 텐셀 U자", "lprice": "60020", "productType": "1"},
                 {"mallName": "필로우네이션", "title": "프리미엄 텐셀", "lprice": "68900"}]
        hits = rt.find_rank(items)
        self.assertEqual([h["rank"] for h in hits], [2, 3])
        self.assertEqual(hits[0]["title"], "필로우네이션 텐셀 U자")

    def test_not_found(self):
        self.assertEqual(rt.find_rank([{"mallName": "x", "title": "y"}]), [])


if __name__ == "__main__":
    unittest.main()
