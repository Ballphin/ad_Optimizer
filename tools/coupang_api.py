#!/usr/bin/env python3
"""쿠팡 Open API — **조회 전용** (주문·상품). 광고 성과는 공개 API가 없어 엑셀 업로드 방식.

사용법:
  python3 tools/coupang_api.py orders --days 30     # 주문(발주서) → data/raw/coupang/orders_*.json + 상품별 합계
  python3 tools/coupang_api.py products             # 등록 상품 목록

필요: .env 의 COUPANG_ACCESS_KEY / SECRET_KEY / VENDOR_ID
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import envfile  # noqa: E402

BASE = "https://api-gateway.coupang.com"
OUT = envfile.ROOT / "data" / "raw" / "coupang"
ORDER_STATUSES = ["ACCEPT", "INSTRUCT", "DEPARTURE", "DELIVERING", "FINAL_DELIVERY"]


def authorization(method: str, path: str, query: str, access: str, secret: str, signed_date: str | None = None) -> str:
    signed_date = signed_date or dt.datetime.now(dt.timezone.utc).strftime("%y%m%dT%H%M%SZ")
    msg = signed_date + method + path + query
    sig = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return f"CEA algorithm=HmacSHA256, access-key={access}, signed-date={signed_date}, signature={sig}"


class Client:
    def __init__(self, access: str, secret: str, vendor: str):
        self.access, self.secret, self.vendor = access, secret, vendor
        self.ctx = envfile.ssl_context()

    @classmethod
    def from_env(cls) -> "Client":
        e = envfile.load()
        return cls(e["COUPANG_ACCESS_KEY"], e["COUPANG_SECRET_KEY"], e["COUPANG_VENDOR_ID"])

    def get(self, path: str, params: dict | None = None):
        query = urllib.parse.urlencode(params or {})
        req = urllib.request.Request(BASE + path + ("?" + query if query else ""), method="GET", headers={
            "Authorization": authorization("GET", path, query, self.access, self.secret),
            "Content-Type": "application/json;charset=UTF-8",
            "X-Requested-By": self.vendor,
        })
        try:
            with urllib.request.urlopen(req, context=self.ctx, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            body = e.read()
            if body[:2] == b"\x1f\x8b":
                import gzip
                body = gzip.decompress(body)
            raise RuntimeError(f"HTTP {e.code} GET {path}: {body.decode(errors='ignore')[:500]}") from None


def cmd_orders(c: Client, days: int) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = f"/v2/providers/openapi/apis/api/v4/vendors/{c.vendor}/ordersheets"
    end = dt.date.today()
    orders = []
    # API는 조회 기간 최대 31일 → 구간 분할
    start = end - dt.timedelta(days=days)
    while start < end:
        chunk_end = min(start + dt.timedelta(days=30), end)
        for st in ORDER_STATUSES:
            token = ""
            while True:
                p = {"createdAtFrom": start.isoformat(), "createdAtTo": chunk_end.isoformat(),
                     "status": st, "maxPerPage": 50}
                if token:
                    p["nextToken"] = token
                res = c.get(path, p)
                orders += res.get("data") or []
                token = res.get("nextToken") or ""
                time.sleep(0.15)
                if not token:
                    break
        start = chunk_end
    f = OUT / f"orders_{end - dt.timedelta(days=days)}_{end}.json"
    f.write_text(json.dumps(orders, ensure_ascii=False, indent=1), encoding="utf-8")
    agg = defaultdict(lambda: {"qty": 0, "amount": 0})
    for o in orders:
        for it in o.get("orderItems", []):
            k = it.get("sellerProductName") or it.get("vendorItemName") or "?"
            agg[k]["qty"] += it.get("shippingCount", 0) or 0
            agg[k]["amount"] += (it.get("orderPrice") or 0)
    print(f"주문 {len(orders)}건 저장: {f}")
    for k, v in sorted(agg.items(), key=lambda kv: -kv[1]["amount"]):
        print(f"  {k[:40]}: {v['qty']}개 / {v['amount']:,.0f}원")
    print("※ 로켓그로스 주문은 이 API(판매자배송 발주서)에 안 잡힐 수 있음 — 윙 통계와 비교 필요")


def cmd_products(c: Client) -> None:
    path = "/v2/providers/seller_api/apis/api/v1/marketplace/seller-products"
    res = c.get(path, {"vendorId": c.vendor, "maxPerPage": 100})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "products.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    for p in res.get("data") or []:
        print(f"  {p.get('sellerProductId')}  {p.get('sellerProductName')}  상태={p.get('statusName')}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["orders", "products"])
    ap.add_argument("--days", type=int, default=30)
    a = ap.parse_args()
    c = Client.from_env()
    cmd_orders(c, a.days) if a.cmd == "orders" else cmd_products(c)


if __name__ == "__main__":
    main()
