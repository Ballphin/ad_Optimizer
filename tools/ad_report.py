#!/usr/bin/env python3
"""광고 리포트 분석기 — "어떤 키워드가 돈을 태우고 있나?"

네이버 검색광고(검색어별 전환 보고서) / 쿠팡 광고 보고서(키워드·지면별)를 읽어
키워드별 실제 ROAS를 손익분기 ROAS와 비교하고 조치(제외·입찰하향·확대·대기)를 제안한다.

사용법:
  python3 tools/ad_report.py data/raw/naver_검색어_30일.csv --platform naver --breakeven 250
  python3 tools/ad_report.py data/raw/coupang_키워드.xlsx --platform coupang --breakeven 300 --target 400
  옵션: --min-clicks 30 (이보다 클릭 적으면 '데이터 부족'), --out docs/diagnosis-YYYY-MM-DD.md

손익분기 ROAS는 tools/margin_calc.py 로 먼저 구한다.

⚠️ 네이버(2026-03 개편 이후): '총 전환매출액'은 장바구니 담기 + 다중 광고 중복 집계가 포함되어
   실제보다 크게 잡힌다. 반드시 '구매완료 전환매출액'으로 보고서를 받을 것 (출처: 동비TV cYXEIQ5uKkk).
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

EXCLUDE = "제외 키워드 등록 (전환 0)"
CUT = "입찰 하향 / 별도 그룹 분리 (손익분기 미만)"
HOLD = "유지 (손익분기~목표 사이)"
GROW = "입찰·예산 확대 후보 (목표 이상)"
WAIT = "데이터 부족 (관찰)"

# 컬럼 별칭: 앞에 있을수록 우선. 공백 제거 후 '포함' 매칭.
ALIASES = {
    "campaign": ["캠페인명", "캠페인이름", "캠페인"],
    "group": ["광고그룹명", "광고그룹"],
    "keyword": ["검색어", "키워드"],
    "placement": ["광고노출지면", "노출지면", "지면"],
    "impressions": ["노출수"],
    "clicks": ["클릭수"],
    "cost": ["총비용", "광고비", "집행광고비", "비용"],
    "revenue_naver": ["구매완료전환매출액"],
    "orders_naver": ["구매완료전환수"],
    "revenue_coupang": ["총전환매출액(14일)", "전환매출액(14일)", "총전환매출액(1일)", "총전환매출액"],
    "orders_coupang": ["총주문수(14일)", "주문수(14일)", "총주문수(1일)", "총주문수", "전환수"],
    "revenue_fallback": ["총전환매출액", "전환매출액"],
    "orders_fallback": ["총전환수", "전환수"],
}
# 이 단어가 들어간 컬럼은 해당 필드로 쓰지 않는다
NEVER = {
    "cost": ["평균", "클릭당"],
    "clicks": ["클릭률", "클릭당"],
    "impressions": ["순위"],
    "keyword": ["제외"],
}


def num(v) -> float:
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "").replace("%", "").replace("원", "")
    if s in ("", "-", "--"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _norm(h) -> str:
    return re.sub(r"\s+", "", str(h or ""))


@dataclass
class Row:
    campaign: str = ""
    group: str = ""
    keyword: str = ""
    placement: str = ""
    impressions: float = 0.0
    clicks: float = 0.0
    cost: float = 0.0
    revenue: float = 0.0
    orders: float = 0.0
    action: str = ""

    @property
    def roas(self) -> float:
        return self.revenue / self.cost * 100 if self.cost else 0.0

    @property
    def cvr(self) -> float:
        return self.orders / self.clicks * 100 if self.clicks else 0.0


def _read_table(path: str) -> list[list]:
    p = Path(path)
    if p.suffix.lower() in (".xlsx", ".xlsm"):
        try:
            import openpyxl
        except ImportError:
            sys.exit("xlsx 읽기에는 openpyxl 필요: .venv/bin/pip install openpyxl (또는 CSV로 저장)")
        wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
        return [list(r) for r in wb.active.iter_rows(values_only=True)]
    raw = p.read_bytes()
    for enc in ("utf-8-sig", "cp949", "utf-16"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        sys.exit(f"인코딩을 알 수 없음: {path}")
    dialect = "excel-tab" if text.count("\t") > text.count(",") else "excel"
    return list(csv.reader(io.StringIO(text), dialect=dialect))


def _find_col(headers: list[str], keys: list[str], field_name: str) -> int | None:
    bad = NEVER.get(field_name, [])
    for k in keys:
        for i, h in enumerate(headers):
            if k in h and not any(b in h for b in bad):
                return i
    return None


def load_rows(path: str, platform: str) -> tuple[list[Row], list[str]]:
    table = _read_table(path)
    warnings: list[str] = []
    # 헤더 행 찾기: 클릭수 + (검색어|키워드|캠페인) 이 들어간 첫 행
    hi = next((i for i, r in enumerate(table[:30])
               if any("클릭수" in _norm(c) for c in r)
               and any(k in _norm(c) for c in r for k in ("검색어", "키워드", "캠페인"))), None)
    if hi is None:
        sys.exit("헤더 행을 찾지 못했습니다 (클릭수/검색어 컬럼이 있는 보고서인지 확인)")
    headers = [_norm(h) for h in table[hi]]

    col = {f: _find_col(headers, ALIASES[f], f) for f in
           ("campaign", "group", "keyword", "placement", "impressions", "clicks", "cost")}
    if platform == "naver":
        col["revenue"] = _find_col(headers, ALIASES["revenue_naver"], "revenue")
        col["orders"] = _find_col(headers, ALIASES["orders_naver"], "orders")
        if col["revenue"] is None:
            col["revenue"] = _find_col(headers, ALIASES["revenue_fallback"], "revenue")
            col["orders"] = _find_col(headers, ALIASES["orders_fallback"], "orders")
            if col["revenue"] is not None:
                warnings.append("구매완료 전환매출액 컬럼이 없어 '총 전환매출액'을 사용했습니다. "
                                "네이버 '총' 지표는 장바구니·중복 집계가 포함되어 ROAS가 부풀려집니다. "
                                "보고서를 '구매완료 전환매출액/전환수'로 다시 받으세요.")
    else:
        col["revenue"] = _find_col(headers, ALIASES["revenue_coupang"], "revenue")
        col["orders"] = _find_col(headers, ALIASES["orders_coupang"], "orders")
    if col["cost"] is None or col["revenue"] is None:
        sys.exit(f"비용/매출 컬럼을 찾지 못했습니다. 헤더: {headers}")

    def get(r, f):
        i = col.get(f)
        return r[i] if i is not None and i < len(r) else None

    rows = []
    for r in table[hi + 1:]:
        if not r or all(c in (None, "") for c in r):
            continue
        first = str(r[0] or "")
        if first.startswith(("합계", "총계", "전체")):
            continue
        rows.append(Row(
            campaign=str(get(r, "campaign") or ""),
            group=str(get(r, "group") or ""),
            keyword=str(get(r, "keyword") or "").strip(),
            placement=str(get(r, "placement") or "").strip(),
            impressions=num(get(r, "impressions")),
            clicks=num(get(r, "clicks")),
            cost=num(get(r, "cost")),
            revenue=num(get(r, "revenue")),
            orders=num(get(r, "orders")),
        ))
    return rows, warnings


@dataclass
class Result:
    rows: list[Row]
    breakeven: float
    target: float
    min_clicks: int
    warnings: list[str] = field(default_factory=list)

    @property
    def total_cost(self) -> float:
        return sum(r.cost for r in self.rows)

    @property
    def total_revenue(self) -> float:
        return sum(r.revenue for r in self.rows)

    @property
    def margin_rate(self) -> float:
        return 100.0 / self.breakeven

    def profit(self, r: Row) -> float:
        """광고 매출의 공헌이익 - 광고비 (자연매출 효과 제외)."""
        return r.revenue * self.margin_rate - r.cost

    @property
    def loss_from_bad(self) -> float:
        return -sum(self.profit(r) for r in self.rows if r.action in (CUT, EXCLUDE) and self.profit(r) < 0)


def analyze(rows: list[Row], breakeven: float, target: float | None = None,
            min_clicks: int = 30, warnings: list[str] | None = None) -> Result:
    target = target or breakeven * 1.3
    for r in rows:
        if r.clicks < min_clicks:
            r.action = WAIT
        elif r.orders == 0 and r.revenue == 0:
            r.action = EXCLUDE
        elif r.roas < breakeven:
            r.action = CUT
        elif r.roas >= target:
            r.action = GROW
        else:
            r.action = HOLD
    return Result(rows, breakeven, target, min_clicks, warnings or [])


def placement_summary(rows: list[Row]) -> dict:
    agg: dict = defaultdict(lambda: {"cost": 0.0, "revenue": 0.0})
    for r in rows:
        if r.placement:
            agg[r.placement]["cost"] += r.cost
            agg[r.placement]["revenue"] += r.revenue
    for v in agg.values():
        v["roas"] = v["revenue"] / v["cost"] * 100 if v["cost"] else 0.0
    return dict(agg)


def _won(x: float) -> str:
    return f"{x:,.0f}"


def to_markdown(res: Result, title: str) -> str:
    total_roas = res.total_revenue / res.total_cost * 100 if res.total_cost else 0
    out = [f"# {title}", ""]
    for w in res.warnings:
        out += [f"> ⚠️ {w}", ""]
    out += [
        f"- 손익분기 ROAS **{res.breakeven:.0f}%** (공헌이익률 {res.margin_rate:.1%}) / 확대 기준 {res.target:.0f}% / 최소 클릭 {res.min_clicks}",
        f"- 총 광고비 {_won(res.total_cost)}원 · 광고 매출 {_won(res.total_revenue)}원 · ROAS **{total_roas:.0f}%**",
        f"- 광고 매출 기준 손익: **{_won(sum(res.profit(r) for r in res.rows))}원** (자연매출 효과 제외)",
        f"- 제외/하향 대상 키워드에서 난 손실: **{_won(res.loss_from_bad)}원**",
        "",
    ]
    ps = placement_summary(res.rows)
    if ps:
        out += ["## 지면별 (쿠팡: 검색 vs 비검색)", "", "| 지면 | 광고비 | 매출 | ROAS |", "|---|---:|---:|---:|"]
        for k, v in sorted(ps.items(), key=lambda kv: -kv[1]["cost"]):
            out.append(f"| {k} | {_won(v['cost'])} | {_won(v['revenue'])} | {v['roas']:.0f}% |")
        out.append("")
    for action in (EXCLUDE, CUT, GROW, HOLD, WAIT):
        group = sorted((r for r in res.rows if r.action == action), key=lambda r: -r.cost)
        if not group:
            continue
        out += [f"## {action} — {len(group)}개, 광고비 {_won(sum(r.cost for r in group))}원", "",
                "| 키워드 | 그룹 | 클릭 | 광고비 | 매출 | ROAS | 전환율 | 손익 |",
                "|---|---|---:|---:|---:|---:|---:|---:|"]
        for r in group[:50]:
            out.append(f"| {r.keyword or '-'} | {r.group} | {r.clicks:.0f} | {_won(r.cost)} | {_won(r.revenue)} "
                       f"| {r.roas:.0f}% | {r.cvr:.1f}% | {_won(res.profit(r))} |")
        if len(group) > 50:
            out.append(f"| … 외 {len(group) - 50}개 | | | | | | | |")
        out.append("")
    out += ["---", "변경은 승인 후 `docs/changes/` 에 기록하고 7일 뒤 전후 비교 (CLAUDE.md 안전 규칙)."]
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("report")
    ap.add_argument("--platform", choices=["naver", "coupang"], required=True)
    ap.add_argument("--breakeven", type=float, required=True, help="손익분기 ROAS %% (margin_calc.py)")
    ap.add_argument("--target", type=float, help="확대 기준 ROAS %% (기본: 손익분기×1.3)")
    ap.add_argument("--min-clicks", type=int, default=30)
    ap.add_argument("--out", help="마크다운 저장 경로")
    a = ap.parse_args()
    rows, warnings = load_rows(a.report, a.platform)
    res = analyze(rows, a.breakeven, a.target, a.min_clicks, warnings)
    md = to_markdown(res, f"{a.platform} 광고 진단 — {Path(a.report).name}")
    if a.out:
        Path(a.out).write_text(md, encoding="utf-8")
        print(f"저장: {a.out}")
    else:
        print(md)


if __name__ == "__main__":
    main()
