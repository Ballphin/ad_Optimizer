#!/usr/bin/env python3
"""YouTube 자막(스크립트) 수집기.

스마트스토어/쿠팡 전문 유튜버 영상의 한국어 자막을 받아
knowledge/transcripts/<채널>/<업로드일>_<영상ID>.md 로 저장한다.

사용법:
  python3 tools/yt_transcripts.py video <영상ID 또는 URL> [...]
  python3 tools/yt_transcripts.py channel <채널URL> [--limit 50] [--all]
  python3 tools/yt_transcripts.py search "<검색어>" [--limit 10] [--all]

  --all 을 주지 않으면 제목에 광고/노출/키워드 등 관련 단어가 있는 영상만 받는다.

  --cookies-from-browser chrome  : 본인 브라우저 로그인 쿠키 사용(선택)

참고: 클라우드 서버 IP는 YouTube가 봇으로 차단하는 경우가 많다.
이 스크립트는 차단을 우회하지 않는다. 본인 PC에서 실행하거나,
본인 계정 쿠키(--cookies-from-browser)를 사용해 정상 경로로 받는다.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "knowledge" / "transcripts"
INDEX = OUT / "INDEX.md"

RELEVANT = re.compile(
    r"광고|노출|키워드|수익률|ROAS|로아스|순위|상위|매출|클릭|전환|CPC|입찰|세팅|설정|"
    r"애드부스트|쇼핑검색|파워링크|브랜드|리뷰|상세페이지|썸네일|가격비교|알고리즘|"
    r"아이템위너|로켓그로스|판매자로켓|쿠팡|스마트스토어|플러스스토어|최적화|SEO",
    re.I,
)

YTDLP_BASE = ["yt-dlp", "--no-warnings"]


def run(cmd: list[str], timeout: int = 180) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.stdout


def list_videos(target: str, limit: int) -> list[dict]:
    """채널 URL 또는 ytsearch 문자열에서 영상 목록(id, title, channel)을 얻는다."""
    if target.startswith("http") and "/watch" not in target and not target.rstrip("/").endswith("/videos"):
        target = target.rstrip("/") + "/videos"
    out = run([
        "yt-dlp", "--flat-playlist", "--playlist-end", str(limit), "--no-warnings",
        "--print", "%(id)s\t%(title)s\t%(channel)s", target,
    ], timeout=300)
    vids = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0]:
            vids.append({"id": parts[0], "title": parts[1], "channel": parts[2] if len(parts) > 2 else ""})
    return vids


def vtt_to_text(vtt: str) -> str:
    """자동자막 VTT의 중복 줄을 제거하고 문단 텍스트로 만든다."""
    lines: list[str] = []
    for raw in vtt.splitlines():
        s = raw.strip()
        if not s or s == "WEBVTT" or "-->" in s or s.startswith(("Kind:", "Language:", "NOTE")):
            continue
        s = html.unescape(re.sub(r"<[^>]+>", "", s)).strip()
        if s and (not lines or lines[-1] != s):
            lines.append(s)
    # 연속된 겹침 제거
    dedup: list[str] = []
    for s in lines:
        if s not in dedup[-3:]:
            dedup.append(s)
    text = " ".join(dedup)
    # 대략 문장 단위 줄바꿈
    text = re.sub(r"(다\.|요\.|죠\.|니다\.|\?|!)\s+", r"\1\n", text)
    return text.strip()


def safe(name: str) -> str:
    return re.sub(r"[\\/:*?\"<>|\s]+", "_", name).strip("_")[:60] or "unknown"


def existing_ids() -> set[str]:
    ids = set()
    for p in OUT.rglob("*.md"):
        m = re.search(r"_([A-Za-z0-9_-]{11})\.md$", p.name)
        if m:
            ids.add(m.group(1))
    return ids


def fetch_one(vid: str) -> Path | None:
    with tempfile.TemporaryDirectory() as td:
        meta_raw = run(YTDLP_BASE + [
            "--skip-download", "--ignore-no-formats-error", "--write-auto-subs", "--write-subs",
            "--sub-langs", "ko", "--sub-format", "vtt",
            "--print", "%(.{id,title,channel,upload_date,duration,view_count,webpage_url})j",
            "--no-simulate", "-o", f"{td}/%(id)s", vid,
        ])
        try:
            meta = json.loads(meta_raw.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            print(f"  ! 메타데이터 실패: {vid}", file=sys.stderr)
            return None
        subs = sorted(Path(td).glob("*.vtt"))
        if not subs:
            print(f"  ! 자막 없음: {vid} {meta.get('title')}", file=sys.stderr)
            return None
        text = vtt_to_text(subs[0].read_text(encoding="utf-8", errors="ignore"))

    ch = safe(meta.get("channel") or "unknown")
    d = meta.get("upload_date") or "00000000"
    path = OUT / ch / f"{d}_{meta['id']}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    title = (meta.get("title") or "").replace('"', "'")
    path.write_text(
        "---\n"
        f"title: \"{title}\"\n"
        f"channel: \"{meta.get('channel')}\"\n"
        f"video_id: {meta['id']}\n"
        f"url: {meta.get('webpage_url') or 'https://youtu.be/' + meta['id']}\n"
        f"upload_date: {d}\n"
        f"duration_sec: {meta.get('duration')}\n"
        f"views: {meta.get('view_count')}\n"
        "source: youtube-auto-captions (ko)\n"
        "---\n\n"
        f"# {meta.get('title')}\n\n{text}\n",
        encoding="utf-8",
    )
    return path


def rebuild_index() -> None:
    rows = []
    for p in sorted(OUT.rglob("*.md")):
        if p == INDEX:
            continue
        head = p.read_text(encoding="utf-8").split("---")[1]
        meta = dict(
            (k.strip(), v.strip().strip('"'))
            for k, v in (l.split(":", 1) for l in head.strip().splitlines() if ":" in l)
        )
        rows.append((meta.get("upload_date", ""), meta.get("channel", ""), meta.get("title", ""), p.relative_to(OUT)))
    rows.sort(reverse=True)
    lines = ["# 수집된 유튜브 스크립트 목록", "", f"총 {len(rows)}개 (최신순)", "",
             "| 업로드일 | 채널 | 제목 | 파일 |", "|---|---|---|---|"]
    for d, ch, t, rel in rows:
        lines.append(f"| {d} | {ch} | {t.replace('|', '/')} | [{rel.name}]({rel.as_posix()}) |")
    INDEX.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["video", "channel", "search"])
    ap.add_argument("targets", nargs="+")
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--all", action="store_true", help="제목 필터 없이 전부 받기")
    ap.add_argument("--cookies-from-browser", dest="browser", help="예: chrome, edge, firefox")
    a = ap.parse_args()
    if a.browser:
        YTDLP_BASE.extend(["--cookies-from-browser", a.browser])

    have = existing_ids()
    todo: list[str] = []
    if a.mode == "video":
        for t in a.targets:
            m = re.search(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{11})", t)
            todo.append(m.group(1) if m else t)
    else:
        for t in a.targets:
            src = t if a.mode == "channel" else f"ytsearch{a.limit}:{t}"
            for v in list_videos(src, a.limit):
                if a.all or RELEVANT.search(v["title"]):
                    todo.append(v["id"])
                else:
                    print(f"  - 건너뜀(관련성 낮음): {v['title']}")

    for vid in dict.fromkeys(todo):
        if vid in have:
            print(f"  = 이미 있음: {vid}")
            continue
        p = fetch_one(vid)
        if p:
            print(f"  + 저장: {p.relative_to(ROOT)}")
    rebuild_index()


if __name__ == "__main__":
    main()
