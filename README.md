# ad_Optimizer
Optimizing Advertisement for Naver and Coupang — 임산부 베개 광고 수익률/매출 최적화

- 프로젝트 지침: [CLAUDE.md](CLAUDE.md)
- 로드맵: [docs/plans/2026-11-22-roadmap.md](docs/plans/2026-11-22-roadmap.md)
- 필요한 정보: [docs/owner-questions.md](docs/owner-questions.md)
- 지식베이스: [knowledge/](knowledge/) — [플레이북](knowledge/playbook/), [영상 노트](knowledge/notes/README.md), [채널 목록](knowledge/sources.md)
- 다음 할 일: [Phase 2 진단 계획](docs/plans/2026-11-22-phase2-diagnosis.md)

## 빠른 시작
```bash
# 손익분기 ROAS 계산
cp data/products.example.json data/products.json   # 실제 값으로 수정
python3 tools/margin_calc.py data/products.json

# 광고 리포트 진단 (손익분기 ROAS 250%일 때)
python3 tools/ad_report.py data/raw/naver_검색어_30일.csv --platform naver --breakeven 250
python3 tools/ad_report.py data/raw/coupang_광고보고서.xlsx --platform coupang --breakeven 250

# 테스트
python3 -m unittest discover -s tests

# 유튜브 자막 수집 (사장님 Mac에서)
python3 -m venv .venv && .venv/bin/pip install yt-dlp certifi openpyxl
export PATH="$PWD/.venv/bin:$PATH"
python3 tools/yt_transcripts.py video o6jYSyld1yg
python3 tools/yt_transcripts.py video --ids-file ids.txt
python3 tools/yt_transcripts.py channel https://www.youtube.com/channel/UCHxNQtE_YwvWWxJ_7fVVOrg --limit 100
```

Claude Code에서 superpowers 플러그인은 `.claude/settings.json` 으로 자동 설정됩니다.
