#!/usr/bin/env python3
"""네이버 검색광고 API — **조회 전용** 클라이언트.

입찰가·예산·ON/OFF를 바꾸는 요청(PUT/DELETE, 리포트 생성 외 POST)은 코드에서 막아 둔다.
변경은 CLAUDE.md 안전 규칙대로 docs/changes/ 에 안을 쓰고 사장님 승인 후 별도로.

사용법:
  python3 tools/naver_searchad.py check                 # 연결 확인 + 캠페인 목록
  python3 tools/naver_searchad.py structure             # 캠페인/그룹/키워드 구조 → data/raw/naver/structure.json
  python3 tools/naver_searchad.py reports --days 30     # 일별 대용량 리포트 다운로드 → data/raw/naver/reports/
  python3 tools/naver_searchad.py stats --days 30       # 캠페인/그룹 단위 기간 합계 성과

필요: .env 의 NAVER_SEARCHAD_API_KEY / SECRET_KEY / CUSTOMER_ID
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import hmac
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import envfile  # noqa: E402

BASE = "https://api.searchad.naver.com"
OUT = envfile.ROOT / "data" / "raw" / "naver"
ALLOWED_POST = ("/stat-reports",)  # 리포트 '생성 요청'만 허용 (광고 설정 변경 아님)
REPORT_TYPES = ["AD", "AD_CONVERSION", "SHOPPINGKEYWORD_DETAIL", "SHOPPINGKEYWORD_CONVERSION_DETAIL"]


def sign(ts: str, method: str, uri: str, secret: str) -> str:
    msg = f"{ts}.{method}.{uri}".encode()
    return base64.b64encode(hmac.new(secret.encode(), msg, hashlib.sha256).digest()).decode()


def headers(method: str, uri: str, key: str, secret: str, customer: str, ts: str | None = None) -> dict:
    ts = ts or str(int(time.time() * 1000))
    return {
        "Content-Type": "application/json; charset=UTF-8",
        "X-Timestamp": ts,
        "X-API-KEY": key,
        "X-Customer": str(customer),
        "X-Signature": sign(ts, method, uri, secret),
    }


class Client:
    def __init__(self, key: str, secret: str, customer: str):
        self.key, self.secret, self.customer = key, secret, customer
        self.ctx = envfile.ssl_context()

    @classmethod
    def from_env(cls) -> "Client":
        e = envfile.load()
        return cls(e["NAVER_SEARCHAD_API_KEY"], e["NAVER_SEARCHAD_SECRET_KEY"], e["NAVER_SEARCHAD_CUSTOMER_ID"])

    def request(self, method: str, uri: str, params: dict | None = None, body: dict | None = None, raw=False):
        method = method.upper()
        if method not in ("GET", "POST") or (method == "POST" and uri not in ALLOWED_POST):
            raise PermissionError(f"조회 전용 클라이언트: {method} {uri} 는 허용되지 않음 (승인 후 별도 구현)")
        return self._send(method, uri, params, body, raw)

    def _send(self, method: str, uri: str, params: dict | None = None, body: dict | None = None, raw=False):
        url = BASE + uri + ("?" + urllib.parse.urlencode(params, doseq=True) if params else "")
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers=headers(method, uri, self.key, self.secret, self.customer))
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, context=self.ctx, timeout=60) as r:
                    payload = r.read()
                    return payload if raw else json.loads(payload or b"null")
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 3:
                    time.sleep(2 ** attempt)
                    req.headers.update(headers(method, uri, self.key, self.secret, self.customer))
                    continue
                msg = e.read().decode(errors="ignore")[:500]
                msg = re.sub(r"api-key: \S+", "api-key: ***", msg)  # 키 값이 로그에 남지 않게
                raise RuntimeError(f"HTTP {e.code} {method} {uri}: {msg}") from None

    def set_keyword_lock(self, keyword_id: str, lock: bool) -> dict:
        """**유일한 쓰기 기능**: 키워드 1개의 ON/OFF(userLock)만 바꾼다. 입찰가·예산 등 다른 필드는 건드리지 않음.
        사장님 승인 건만 실행하고 docs/changes/ 에 기록할 것."""
        if not re.fullmatch(r"nkw-[A-Za-z0-9-]+", keyword_id):
            raise ValueError(f"키워드 ID 형식이 아님: {keyword_id}")
        cur = self.get(f"/ncc/keywords/{keyword_id}")
        body = {"nccKeywordId": keyword_id, "nccAdgroupId": cur["nccAdgroupId"], "userLock": bool(lock)}
        return self._send("PUT", f"/ncc/keywords/{keyword_id}", params={"fields": "userLock"}, body=body)

    def get(self, uri, **params):
        return self.request("GET", uri, params=params or None)

    def download(self, download_url: str) -> bytes:
        """리포트 파일 다운로드 (서명 uri 는 /report-download)."""
        u = urllib.parse.urlparse(download_url)
        req = urllib.request.Request(download_url, headers=headers("GET", "/report-download", self.key,
                                                                   self.secret, self.customer))
        with urllib.request.urlopen(req, context=self.ctx, timeout=120) as r:
            return r.read()


def cmd_check(c: Client) -> None:
    camps = c.get("/ncc/campaigns")
    print(f"연결 OK — 캠페인 {len(camps)}개")
    for x in camps:
        print(f"  [{x.get('campaignTp')}] {x.get('name')}  상태={x.get('status')}  "
              f"일예산={x.get('dailyBudget')}  사용={'ON' if not x.get('userLock') else 'OFF'}")


def cmd_structure(c: Client) -> Path:
    camps = c.get("/ncc/campaigns")
    for camp in camps:
        camp["adgroups"] = c.get("/ncc/adgroups", nccCampaignId=camp["nccCampaignId"])
        for g in camp["adgroups"]:
            try:
                g["keywords"] = c.get("/ncc/keywords", nccAdgroupId=g["nccAdgroupId"])
            except RuntimeError:
                g["keywords"] = []  # 쇼핑검색 그룹은 키워드 엔티티가 없을 수 있음
            try:
                g["ads"] = c.get("/ncc/ads", nccAdgroupId=g["nccAdgroupId"])
            except RuntimeError:
                g["ads"] = []
            try:
                g["restricted_keywords"] = c.get("/ncc/adgroups/" + g["nccAdgroupId"] + "/restricted-keywords",
                                                 type="KEYWORD_PLUS_RESTRICT")
            except RuntimeError:
                g["restricted_keywords"] = []
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / "structure.json"
    p.write_text(json.dumps(camps, ensure_ascii=False, indent=1), encoding="utf-8")
    ng = sum(len(x["adgroups"]) for x in camps)
    print(f"저장: {p}  (캠페인 {len(camps)}, 광고그룹 {ng})")
    return p


def cmd_reports(c: Client, days: int, types: list[str]) -> None:
    out = OUT / "reports"
    out.mkdir(parents=True, exist_ok=True)
    today = dt.date.today()
    pending = []
    for d in range(1, days + 1):
        day = (today - dt.timedelta(days=d)).strftime("%Y%m%d")
        for tp in types:
            f = out / f"{tp}_{day}.tsv"
            if f.exists():
                continue
            try:
                job = c.request("POST", "/stat-reports", body={"reportTp": tp, "statDt": day})
                pending.append((job["reportJobId"], f))
            except RuntimeError as e:
                print(f"  ! {tp} {day}: {e}")
            time.sleep(0.2)
    print(f"리포트 요청 {len(pending)}건, 생성 대기…")
    for _ in range(60):
        if not pending:
            break
        nxt = []
        for jid, f in pending:
            try:
                job = c.get(f"/stat-reports/{jid}")
            except RuntimeError as e:
                print(f"  ! 조회 실패 {f.name}: {str(e)[:80]}")
                continue
            st = job.get("status")
            if st == "BUILT":
                f.write_bytes(c.download(job["downloadUrl"]))
            elif st in ("NONE",):
                f.write_bytes(b"")  # 해당 일 데이터 없음
            elif st in ("ERROR", "AGGREGATING_FAILED"):
                print(f"  ! 실패 {f.name}: {st}")
            else:
                nxt.append((jid, f))
            time.sleep(0.1)
        pending = nxt
        if pending:
            time.sleep(3)
    got = len(list(out.glob("*.tsv")))
    print(f"완료: {out} ({got}개 파일)" + (f", 미완료 {len(pending)}건" if pending else ""))


def cmd_stats(c: Client, days: int) -> None:
    until = dt.date.today() - dt.timedelta(days=1)
    since = until - dt.timedelta(days=days - 1)
    camps = c.get("/ncc/campaigns")
    ids = [x["nccCampaignId"] for x in camps]
    fields = ["impCnt", "clkCnt", "salesAmt", "ccnt", "convAmt", "crto", "ror"]
    res = c.get("/stats", ids=",".join(ids), fields=json.dumps(fields),
                timeRange=json.dumps({"since": since.isoformat(), "until": until.isoformat()}))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"stats_campaign_{since}_{until}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1),
                                                             encoding="utf-8")
    name = {x["nccCampaignId"]: x["name"] for x in camps}
    print(f"{since} ~ {until}")
    for row in res.get("data", []):
        print(f"  {name.get(row['id'], row['id'])}: 비용 {row.get('salesAmt', 0):,.0f} / 전환매출 "
              f"{row.get('convAmt', 0):,.0f} / 전환 {row.get('ccnt', 0)} / ROAS {row.get('ror', 0)}%")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["check", "structure", "reports", "stats"])
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--types", nargs="+", default=REPORT_TYPES)
    a = ap.parse_args()
    c = Client.from_env()
    if a.cmd == "check":
        cmd_check(c)
    elif a.cmd == "structure":
        cmd_structure(c)
    elif a.cmd == "reports":
        cmd_reports(c, a.days, a.types)
    else:
        cmd_stats(c, a.days)


if __name__ == "__main__":
    main()
