#!/usr/bin/env python3
"""네이버 쇼핑인사이트 키워드별 클릭 추이 — NAVER API HUB (네이버 클라우드, 조회 전용).

  python3 tools/naver_trend.py --kw 임산부바디필로우 --kw U자바디필로우 --from 2025-01-01 --unit month
  → data/raw/naver/trend_<날짜>.json + 표 출력 (ratio: 기간 중 최댓값=100인 상대값, 절대 클릭수 아님)

카테고리 기본값 50000276 = 출산/육아 > 임산부용품 > 임산부바디필로우 (네이버쇼핑 cat_id).
필요: .env NAVER_OPENAPI_CLIENT_ID / SECRET = API HUB 앱의 Client ID/Secret (쇼핑인사이트 API 추가된 앱)
문서: https://api.ncloud-docs.com/docs/naver-api-hub-shopping-insight-keywords
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import envfile  # noqa: E402

BASE = "https://naverapihub.apigw.ntruss.com"


def keyword_trend(cid: str, sec: str, category: str, keywords: list[str], start: str, end: str, unit: str) -> dict:
    body = {"startDate": start, "endDate": end, "timeUnit": unit, "category": category,
            "keyword": [{"name": k, "param": [k]} for k in keywords[:5]]}
    req = urllib.request.Request(BASE + "/shopping/v1/category/keywords", data=json.dumps(body).encode(), method="POST",
                                 headers={"X-NCP-APIGW-API-KEY-ID": cid, "X-NCP-APIGW-API-KEY": sec,
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, context=envfile.ssl_context(), timeout=30) as r:
        return json.loads(r.read())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kw", action="append", required=True)
    ap.add_argument("--category", default="50000276")
    ap.add_argument("--from", dest="start", default="2025-01-01")
    ap.add_argument("--to", dest="end", default=dt.date.today().isoformat())
    ap.add_argument("--unit", choices=["date", "week", "month"], default="month")
    a = ap.parse_args()
    e = envfile.load()
    r = keyword_trend(e["NAVER_OPENAPI_CLIENT_ID"], e["NAVER_OPENAPI_CLIENT_SECRET"], a.category, a.kw, a.start, a.end, a.unit)
    out = envfile.ROOT / "data" / "raw" / "naver"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"trend_{dt.date.today()}.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    for res in r.get("results", []):
        print(res["title"], " ".join(f"{d['period'][:7]}:{d['ratio']:.0f}" for d in res["data"]))


if __name__ == "__main__":
    main()
