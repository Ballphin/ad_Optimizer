#!/usr/bin/env python3
"""쿠팡 로켓그로스 재고 경보 — **조회 전용**. 품절은 쿠팡 순위를 한 번에 무너뜨린다(notes/20260827_OJAyWYCIWyU).

사용법:
  python3 tools/stock_watch.py                 # 판매 중인 옵션별 남은 일수, 품절 예상일, 재발주 수량
  python3 tools/stock_watch.py --lead 24       # 리드타임(제작+배대지 운송+로켓그로스 입고 처리, 일)

판매 속도: data/raw/coupang/rg_daily_units.json 이 있으면 최근 14일 평균, 없으면 API의 최근 30일 판매 수 ÷ 30.
경보 기준: 남은 일수 < 리드타임 + 안전재고 7일.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import envfile  # noqa: E402

SAFETY_DAYS = 7
OUT = envfile.ROOT / "data" / "raw" / "coupang"


def daily_rate(daily: dict, end: dt.date, window: int = 14, skip: list[str] | None = None) -> float:
    days = [(end - dt.timedelta(i)).isoformat() for i in range(window)]
    days = [d for d in days if d not in set(skip or [])]
    return sum(daily.get(d, 0) for d in days) / len(days) if days else 0.0


def assess(stock: int, rate: float, lead_days: int, today: dt.date) -> dict:
    if rate <= 0:
        return {"days_left": None, "stockout_date": None, "alert": False, "reorder_qty": 0}
    days_left = int(stock / rate)
    need = round(rate * (lead_days + SAFETY_DAYS))
    return {"days_left": days_left,
            "stockout_date": (today + dt.timedelta(days=days_left)).isoformat(),
            "alert": days_left < lead_days + SAFETY_DAYS,
            "reorder_qty": max(0, need - stock)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lead", type=int, default=24, help="리드타임 일수 (기본 24 = 제작 14 + 운송 7 + 입고 3)")
    a = ap.parse_args()
    from coupang_api import Client
    c = Client.from_env()
    inv = c.get(f"/v2/providers/rg_open_api/apis/api/v1/vendors/{c.vendor}/rg/inventory/summaries")
    today = dt.date.today()
    (OUT / f"rg_inventory_{today}.json").write_text(json.dumps(inv, ensure_ascii=False), encoding="utf-8")
    daily_file = OUT / "rg_daily_units.json"
    daily = json.loads(daily_file.read_text()) if daily_file.exists() else None
    selling = [x for x in inv.get("data", []) if (x.get("salesCountMap") or {}).get("SALES_COUNT_LAST_THIRTY_DAYS")]
    for item in selling:
        stock = (item.get("inventoryDetails") or {}).get("totalOrderableQuantity", 0)
        rate = item["salesCountMap"]["SALES_COUNT_LAST_THIRTY_DAYS"] / 30
        if daily and len(selling) == 1:  # 일별 파일은 옵션 구분이 없으므로 판매 옵션이 1개일 때만 사용
            rate = max(rate, daily_rate(daily, today - dt.timedelta(1)))
        r = assess(stock, rate, a.lead, today)
        flag = "🚨 재발주 필요" if r["alert"] else "OK"
        print(f"[{flag}] 옵션 {item['vendorItemId']}: 재고 {stock}개 / 하루 {rate:.2f}개 → {r['days_left']}일 남음 "
              f"(품절 예상 {r['stockout_date']}), 리드타임 {a.lead}+{SAFETY_DAYS}일을 버틸 최소 발주 {r['reorder_qty']}개")


if __name__ == "__main__":
    main()
