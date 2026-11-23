#!/usr/bin/env python3
"""네이버 커머스 API — **조회 전용** (주문). 스마트스토어 실제 판매 개수·결제금액 추출.

사용법:
  python3 tools/naver_commerce.py orders --from 2026-08-23 --to 2026-11-22
    → data/raw/naver/commerce_orders_<from>_<to>.json + 월별·상품별 요약 출력

필요: .env 의 NAVER_COMMERCE_CLIENT_ID / CLIENT_SECRET, 커머스API센터에 이 PC의 IP 등록, pip install bcrypt
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
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

BASE = "https://api.commerce.naver.com/external"
OUT = envfile.ROOT / "data" / "raw" / "naver"
KST = dt.timezone(dt.timedelta(hours=9))
CANCELED = {"CANCELED", "RETURNED", "CANCELED_BY_NOPAYMENT", "EXCHANGED"}


class Client:
    def __init__(self, cid: str, secret: str):
        self.cid, self.secret, self.ctx, self.token = cid, secret, envfile.ssl_context(), None

    @classmethod
    def from_env(cls) -> "Client":
        e = envfile.load()
        return cls(e["NAVER_COMMERCE_CLIENT_ID"], e["NAVER_COMMERCE_CLIENT_SECRET"])

    def auth(self) -> None:
        import bcrypt
        ts = str(int(time.time() * 1000))
        sign = base64.b64encode(bcrypt.hashpw(f"{self.cid}_{ts}".encode(), self.secret.encode())).decode()
        data = urllib.parse.urlencode({"client_id": self.cid, "timestamp": ts, "client_secret_sign": sign,
                                       "grant_type": "client_credentials", "type": "SELF"}).encode()
        with urllib.request.urlopen(urllib.request.Request(BASE + "/v1/oauth2/token", data=data, method="POST"),
                                    context=self.ctx, timeout=30) as r:
            self.token = json.loads(r.read())["access_token"]

    def call(self, method: str, path: str, params: dict | None = None, body: dict | None = None):
        # 조회 전용: GET + 주문 상세 조회(POST /product-orders/query)만 허용
        if not (method == "GET" or (method == "POST" and path.endswith("/product-orders/query"))):
            raise PermissionError(f"조회 전용: {method} {path}")
        if not self.token:
            self.auth()
        url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
        req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body else None,
                                     headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, context=self.ctx, timeout=60) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 4:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise RuntimeError(f"HTTP {e.code} {path}: {e.read().decode(errors='ignore')[:300]}") from None


def changed_ids(c: Client, start: dt.date, end: dt.date) -> list[str]:
    ids: set[str] = set()
    d = dt.datetime.combine(start, dt.time(), KST)
    stop = dt.datetime.combine(end + dt.timedelta(days=1), dt.time(), KST)
    while d < stop:
        to = min(d + dt.timedelta(hours=24) - dt.timedelta(milliseconds=1), stop)
        params = {"lastChangedFrom": d.isoformat(timespec="milliseconds"),
                  "lastChangedTo": to.isoformat(timespec="milliseconds")}
        while True:
            r = c.call("GET", "/v1/pay-order/seller/product-orders/last-changed-statuses", params)
            data = r.get("data") or {}
            for x in data.get("lastChangeStatuses") or []:
                ids.add(x["productOrderId"])
            more = data.get("more")
            if not more:
                break
            params["lastChangedFrom"] = more["moreFrom"]
            params["moreSequence"] = more["moreSequence"]
            time.sleep(0.3)
        d += dt.timedelta(hours=24)
        time.sleep(0.3)
    return sorted(ids)


def details(c: Client, ids: list[str]) -> list[dict]:
    out = []
    for i in range(0, len(ids), 300):
        r = c.call("POST", "/v1/pay-order/seller/product-orders/query", body={"productOrderIds": ids[i:i + 300]})
        out += r.get("data") or []
        time.sleep(0.3)
    return out


def summarize(rows: list[dict], start: dt.date, end: dt.date) -> None:
    agg = defaultdict(lambda: defaultdict(lambda: {"qty": 0, "pay": 0, "cancel_qty": 0}))
    for x in rows:
        po = x.get("productOrder") or {}
        od = x.get("order") or {}
        pay = (od.get("paymentDate") or od.get("orderDate") or "")[:10]
        if not pay or not (start.isoformat() <= pay <= end.isoformat()):
            continue
        k = (po.get("productName") or "?")[:40]
        m = agg[k][pay[:7]]
        q = po.get("quantity") or 0
        if po.get("productOrderStatus") in CANCELED:
            m["cancel_qty"] += q
        else:
            m["qty"] += q
            m["pay"] += po.get("totalPaymentAmount") or 0
    for k, ms in agg.items():
        print(k)
        for mo in sorted(ms):
            v = ms[mo]
            avg = v["pay"] / v["qty"] if v["qty"] else 0
            print(f"   {mo}: {v['qty']}개 (취소·반품 {v['cancel_qty']}) 결제 {v['pay']:,.0f}원 평균 {avg:,.0f}원")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["orders"])
    ap.add_argument("--from", dest="start", required=True)
    ap.add_argument("--to", dest="end", required=True)
    a = ap.parse_args()
    start, end = dt.date.fromisoformat(a.start), dt.date.fromisoformat(a.end)
    c = Client.from_env()
    # 결제 후 상태가 바뀐 주문까지 잡기 위해 조회 구간을 뒤로 14일 더 본다
    ids = changed_ids(c, start, min(end + dt.timedelta(days=14), dt.date.today()))
    rows = details(c, ids)
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / f"commerce_orders_{start}_{end}.json"
    f.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    print(f"상품주문 {len(rows)}건 저장: {f}")
    summarize(rows, start, end)


if __name__ == "__main__":
    main()
