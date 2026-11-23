#!/usr/bin/env python3
"""네이버 쇼핑 키워드 순위 추적 — **네이버 공식 검색 API**(developers.naver.com) 사용.

쿠팡은 공식 검색 API가 없고 자동 조회를 차단하므로 추적하지 않는다(우회 금지). 쿠팡은 광고 보고서로 판단.

사용법:
  python3 tools/rank_tracker.py naver                # 기본 키워드 순위 → data/raw/rank/naver_YYYY-MM-DD.json + 기록 CSV
  python3 tools/rank_tracker.py naver --kw 수유쿠션 --kw 옆잠베개

필요: .env 의 NAVER_OPENAPI_CLIENT_ID / NAVER_OPENAPI_CLIENT_SECRET
  ⚠️ 2026년 네이버 오픈API가 네이버 클라우드 'NAVER API HUB'로 이관됨.
  - API HUB 공식 검색 API 목록에 **쇼핑 검색(shop.json)이 없음** → HUB 키로는 이 도구가 동작하지 않는다.
  - 2026-07 이전에 developers.naver.com 에서 만든 기존 앱 키만 openapi.naver.com/v1/search/shop.json 호출 가능
    (제3자 정리 기준 2027-06-30까지 — 공식 확인 필요).
  - 출처: https://api.ncloud-docs.com/docs/naver-api-hub-overview , https://guide.ncloud-docs.com/docs/apihub-migration
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import envfile  # noqa: E402

OUT = envfile.ROOT / "data" / "raw" / "rank"
DEFAULT_KW = ["임산부바디필로우", "임산부 바디필로우", "임산부베개", "U자바디필로우", "바디필로우",
              "수유쿠션", "임산부쿠션", "옆잠베개", "몰카탐지기", "몰래카메라탐지기"]
OURS = ("필로우네이션", "pillownation", "랜드가드", "landguard")


def find_rank(items: list[dict], ours=OURS) -> list[dict]:
    """검색 결과 items(순서대로)에서 우리 상품 위치를 찾는다. 1부터 시작."""
    hits = []
    for i, it in enumerate(items, start=1):
        text = f"{it.get('mallName', '')} {it.get('title', '')} {it.get('brand', '')}".lower()
        if any(o.lower() in text for o in ours):
            hits.append({"rank": i, "mall": it.get("mallName"), "title": it.get("title", "").replace("<b>", "").replace("</b>", ""),
                         "price": it.get("lprice"), "productId": it.get("productId"), "productType": it.get("productType")})
    return hits


def search(cid: str, sec: str, kw: str, display: int = 100, start: int = 1) -> list[dict]:
    q = urllib.parse.urlencode({"query": kw, "display": display, "start": start, "sort": "sim"})
    req = urllib.request.Request("https://openapi.naver.com/v1/search/shop.json?" + q,
                                 headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": sec})
    with urllib.request.urlopen(req, context=envfile.ssl_context(), timeout=30) as r:
        return json.loads(r.read()).get("items", [])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("channel", choices=["naver"])
    ap.add_argument("--kw", action="append")
    a = ap.parse_args()
    e = envfile.load()
    cid, sec = e.get("NAVER_OPENAPI_CLIENT_ID"), e.get("NAVER_OPENAPI_CLIENT_SECRET")
    if not cid or not sec:
        sys.exit(".env 에 NAVER_OPENAPI_CLIENT_ID / NAVER_OPENAPI_CLIENT_SECRET 필요 (developers.naver.com)")
    today = dt.date.today().isoformat()
    res = {}
    for kw in a.kw or DEFAULT_KW:
        items = search(cid, sec, kw, 100, 1) + search(cid, sec, kw, 100, 101)  # 상위 200위
        res[kw] = find_rank(items)
        best = res[kw][0]["rank"] if res[kw] else None
        print(f"{kw}: {best if best else '200위 밖'}" + (f"  ({res[kw][0]['mall']}, {res[kw][0]['price']}원)" if best else ""))
        time.sleep(0.2)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"naver_{today}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    log = OUT / "naver_history.csv"
    new = not log.exists()
    with log.open("a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "keyword", "best_rank", "mall"])
        for kw, hits in res.items():
            w.writerow([today, kw, hits[0]["rank"] if hits else "", hits[0]["mall"] if hits else ""])


if __name__ == "__main__":
    main()
