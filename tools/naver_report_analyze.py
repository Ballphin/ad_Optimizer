#!/usr/bin/env python3
"""네이버 StatReport(TSV, 헤더 없음) → 캠페인/그룹/키워드별 비용과 **구매완료** 성과.

입력: data/raw/naver/reports/*.tsv (tools/naver_searchad.py reports), data/raw/naver/structure.json
출력: 표준출력 마크다운 (+ --csv 로 키워드 표 저장 → tools/ad_report.py 입력 가능)

컬럼(네이버 API 문서 기준):
  AD: 0 date,1 customer,2 campaign,3 adgroup,4 keyword_id,5 ad_id,6 bizch,7 media,8 pc/m,9 imp,10 clk,11 cost,12 rank_sum,13 view
  AD_CONVERSION: ... 7 media,8 pc/m,9 method(1직접/2간접),10 type(purchase/add_to_cart/..),11 count,12 sales
  SHOPPINGKEYWORD_DETAIL: 4 search_keyword, ... 11 imp,12 clk,13 cost
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "naver"


def rows(prefix: str):
    for f in sorted((RAW / "reports").glob(f"{prefix}_2*.tsv")):
        for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.strip():
                yield line.split("\t")


def n(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def names():
    st = json.loads((RAW / "structure.json").read_text(encoding="utf-8"))
    camp, grp, kw = {}, {}, {}
    for c in st:
        camp[c["nccCampaignId"]] = c["name"]
        for g in c["adgroups"]:
            grp[g["nccAdgroupId"]] = g["name"]
            for k in g.get("keywords") or []:
                kw[k["nccKeywordId"]] = k["keyword"]
    return camp, grp, kw


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="키워드별 표 CSV 저장 경로 (ad_report.py 입력용)")
    a = ap.parse_args()
    camp, grp, kw = names()

    g = defaultdict(lambda: {"imp": 0, "clk": 0, "cost": 0, "buy": 0, "buy_amt": 0, "cart": 0, "cart_amt": 0})
    k = defaultdict(lambda: {"imp": 0, "clk": 0, "cost": 0, "buy": 0, "buy_amt": 0})
    days = set()
    for r in rows("AD"):
        if len(r) < 12:
            continue
        days.add(r[0])
        key = (camp.get(r[2], r[2]), grp.get(r[3], r[3]))
        for f, i in (("imp", 9), ("clk", 10), ("cost", 11)):
            g[key][f] += n(r[i])
        if r[4] and r[4] != "-":
            kk = key + (kw.get(r[4], r[4]),)
            for f, i in (("imp", 9), ("clk", 10), ("cost", 11)):
                k[kk][f] += n(r[i])
    for r in rows("AD_CONVERSION"):
        if len(r) < 13:
            continue
        key = (camp.get(r[2], r[2]), grp.get(r[3], r[3]))
        if r[10] == "purchase":
            g[key]["buy"] += n(r[11]); g[key]["buy_amt"] += n(r[12])
            if r[4] and r[4] != "-":
                kk = key + (kw.get(r[4], r[4]),)
                k[kk]["buy"] += n(r[11]); k[kk]["buy_amt"] += n(r[12])
        elif r[10] == "add_to_cart":
            g[key]["cart"] += n(r[11]); g[key]["cart_amt"] += n(r[12])

    # 쇼핑검색 실제 검색어
    sk = defaultdict(lambda: {"imp": 0, "clk": 0, "cost": 0, "buy": 0, "buy_amt": 0})
    for r in rows("SHOPPINGKEYWORD_DETAIL"):
        if len(r) < 14:
            continue
        kk = (camp.get(r[2], r[2]), grp.get(r[3], r[3]), r[4])
        for f, i in (("imp", 11), ("clk", 12), ("cost", 13)):
            sk[kk][f] += n(r[i])
    for r in rows("SHOPPINGKEYWORD_CONVERSION_DETAIL"):
        if len(r) >= 13 and r[10] == "purchase":
            kk = (camp.get(r[2], r[2]), grp.get(r[3], r[3]), r[4])
            sk[kk]["buy"] += n(r[11]); sk[kk]["buy_amt"] += n(r[12])

    d = sorted(days)
    print(f"# 네이버 광고 실적 (구매완료 기준) {d[0] if d else ''} ~ {d[-1] if d else ''}, 데이터 있는 날 {len(d)}일\n")
    tot = {f: sum(v[f] for v in g.values()) for f in ("imp", "clk", "cost", "buy", "buy_amt", "cart", "cart_amt")}
    roas = tot["buy_amt"] / tot["cost"] * 100 if tot["cost"] else 0
    print(f"- 총 광고비 **{tot['cost']:,.0f}원** · 클릭 {tot['clk']:,.0f} · 구매 **{tot['buy']:.0f}건 / {tot['buy_amt']:,.0f}원** "
          f"· 구매완료 ROAS **{roas:.0f}%**")
    print(f"- 참고: 장바구니 담기 {tot['cart']:.0f}건 / {tot['cart_amt']:,.0f}원 (네이버 '총 전환'에는 이게 섞여 있음)\n")
    print("| 캠페인 | 광고그룹 | 노출 | 클릭 | 광고비 | 구매 | 구매매출 | ROAS | 장바구니 |")
    print("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for (c, gr), v in sorted(g.items(), key=lambda kv: -kv[1]["cost"]):
        r_ = v["buy_amt"] / v["cost"] * 100 if v["cost"] else 0
        print(f"| {c} | {gr} | {v['imp']:,.0f} | {v['clk']:,.0f} | {v['cost']:,.0f} | {v['buy']:.0f} | "
              f"{v['buy_amt']:,.0f} | {r_:.0f}% | {v['cart']:.0f} |")

    def top(title, dd, lim=25):
        items = [(kk, v) for kk, v in dd.items() if v["cost"] > 0 or v["buy"] > 0]
        if not items:
            return
        print(f"\n## {title} (광고비 상위 {lim})\n")
        print("| 캠페인 | 그룹 | 키워드 | 노출 | 클릭 | 광고비 | 평균CPC | 구매 | 구매매출 |")
        print("|---|---|---|---:|---:|---:|---:|---:|---:|")
        for (c, gr, kwd), v in sorted(items, key=lambda kv: -kv[1]["cost"])[:lim]:
            cpc = v["cost"] / v["clk"] if v["clk"] else 0
            print(f"| {c} | {gr} | {kwd} | {v['imp']:,.0f} | {v['clk']:,.0f} | {v['cost']:,.0f} | {cpc:,.0f} | "
                  f"{v['buy']:.0f} | {v['buy_amt']:,.0f} |")

    top("파워링크 키워드", k)
    top("쇼핑검색 실제 검색어", sk)

    if a.csv:
        with open(a.csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["캠페인", "광고그룹", "검색어", "노출수", "클릭수", "총비용", "구매완료 전환매출액", "구매완료 전환수"])
            for dd in (k, sk):
                for (c, gr, kwd), v in dd.items():
                    w.writerow([c, gr, kwd, v["imp"], v["clk"], v["cost"], v["buy_amt"], v["buy"]])
        print(f"\nCSV 저장: {a.csv}")


if __name__ == "__main__":
    main()
