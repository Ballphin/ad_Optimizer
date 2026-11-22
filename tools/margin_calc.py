#!/usr/bin/env python3
"""마진 / 손익분기 ROAS / 최대 허용 CPC 계산기.

광고 최적화의 출발점: "이 상품은 ROAS 몇 %부터 돈을 버는가?"
이 숫자를 모르면 광고를 켤지 끌지 판단할 수 없다.

사용법:
  python3 tools/margin_calc.py data/products.json
  python3 -m unittest discover -s tests

ROAS 정의: 광고 매출 / 광고비 × 100 (%) — 네이버/쿠팡 광고센터와 동일.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field


@dataclass
class Product:
    name: str
    channel: str                 # "naver" | "coupang"
    price: float                 # 고객 결제가 (배송비 별도 수취분 제외, VAT 포함)
    cogs: float                  # 제품 원가 (매입가, VAT 포함)
    shipping: float = 0.0        # 판매자 부담 택배비/풀필먼트비 (1건당)
    packaging: float = 0.0       # 포장재·사은품 등
    fee_rate: float = 0.0        # 플랫폼 수수료율 합계 (예: 0.0563 = 5.63%)
    other_cost: float = 0.0      # 반품충당·기타 1건당 비용
    vat_inclusive: bool = True   # True면 부가세(매출세액-매입세액)를 비용으로 반영
    extra: dict = field(default_factory=dict)

    # ---- 1건당 손익 ----
    @property
    def fee(self) -> float:
        return self.price * self.fee_rate

    @property
    def vat(self) -> float:
        """간이 계산: (매출 - 원가) / 11. 과세사업자 기준 납부 부가세 근사치."""
        if not self.vat_inclusive:
            return 0.0
        return max(self.price - self.cogs, 0) / 11

    @property
    def contribution(self) -> float:
        """광고비 차감 전 1건당 공헌이익(원)."""
        return (self.price - self.cogs - self.shipping - self.packaging
                - self.fee - self.other_cost - self.vat)

    @property
    def margin_rate(self) -> float:
        """광고비 차감 전 공헌이익률 (판매가 대비)."""
        return self.contribution / self.price

    # ---- 광고 판단 기준 ----
    def breakeven_roas(self) -> float:
        """광고비 = 공헌이익이 되는 ROAS(%). 이보다 낮으면 팔수록 손해."""
        if self.margin_rate <= 0:
            return float("inf")
        return 100.0 / self.margin_rate

    def target_roas(self, profit_rate: float) -> float:
        """광고 후 판매가 대비 profit_rate 만큼 남기기 위한 목표 ROAS(%)."""
        room = self.margin_rate - profit_rate
        if room <= 0:
            return float("inf")
        return 100.0 / room

    def max_cpc(self, cvr: float, profit_rate: float = 0.0) -> float:
        """전환율(cvr, 0.02=2%)일 때 profit_rate를 지키며 쓸 수 있는 최대 클릭당 비용(원)."""
        return max(self.price * cvr * (self.margin_rate - profit_rate), 0.0)

    def profit_at_roas(self, roas_pct: float, ad_spend: float) -> float:
        """주어진 ROAS와 광고비에서의 순이익(원). 광고 매출만 고려."""
        revenue = ad_spend * roas_pct / 100
        return revenue * self.margin_rate - ad_spend


def report(p: Product, cvr: float = 0.02) -> str:
    lines = [
        f"■ {p.name} [{p.channel}]",
        f"  판매가 {p.price:,.0f}원 / 원가 {p.cogs:,.0f} / 배송 {p.shipping:,.0f} / 수수료 {p.fee:,.0f} ({p.fee_rate:.2%}) / 부가세 {p.vat:,.0f}",
        f"  광고 전 공헌이익 {p.contribution:,.0f}원  (이익률 {p.margin_rate:.1%})",
        f"  손익분기 ROAS  {p.breakeven_roas():,.0f}%",
        f"  목표 ROAS(순이익 10%) {p.target_roas(0.10):,.0f}%  / (순이익 15%) {p.target_roas(0.15):,.0f}%",
        f"  최대 CPC (전환율 {cvr:.1%}, 손익분기) {p.max_cpc(cvr):,.0f}원  / (순이익 10%) {p.max_cpc(cvr, 0.10):,.0f}원",
    ]
    return "\n".join(lines)


def load(path: str) -> list[Product]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [Product(**d) for d in data["products"]]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    for prod in load(sys.argv[1]):
        print(report(prod))
        print()
