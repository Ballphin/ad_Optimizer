# ad_Optimizer — 프로젝트 지침 (Claude가 매 세션 읽는 파일)

## 목적
네이버 스마트스토어(플러스스토어) + 쿠팡 윙에서 판매 중인 **임산부 베개**의
광고 수익률(ROAS)과 매출을 올려 **순이익을 극대화**한다.
현재 누적 손실이 약 1억 원 규모이므로, "매출"보다 **"광고 후 순이익"이 최우선 지표**다.

## 작업 방식 (Superpowers)
- 이 레포는 [obra/superpowers](https://github.com/obra/superpowers) 플러그인을 사용한다 (`.claude/settings.json`).
- 큰 작업은 항상: `brainstorming` → `writing-plans` (docs/plans/에 저장) → `executing-plans` → `verification-before-completion`.
- 코드(계산기, 수집기, API 연동)는 `test-driven-development` 로 작성하고 `python3 -m unittest discover -s tests` 로 검증.
- 광고 변경 제안은 반드시 **근거(데이터 + 지식베이스 출처 파일)** 를 붙인다.

## 안전 규칙 (돈이 걸린 일)
1. 실제 광고 계정의 입찰가/예산/ON·OFF 변경은 **사용자 승인 후에만** 실행한다. 먼저 `docs/changes/` 에 변경안을 쓴다.
2. 한 번에 바꾸는 변수는 최소화 (캠페인 단위 A/B). 변경 전후 7일 데이터를 비교 기록한다.
3. API 키, 로그인 정보, 쿠키는 **절대 커밋하지 않는다** (`.env`, `secrets/` 는 .gitignore).
4. 가구매·어뷰징·리뷰 조작 등 플랫폼 정책 위반 전략은 제안하지 않는다 (계정 정지 = 전 재산 손실).

## 핵심 판단 기준
- **네이버 2026-03 개편 이후 "총 전환" 지표는 장바구니·중복 포함 → 절대 성과 판단에 쓰지 않는다. 구매완료 기준만.** (notes/20260421_cYXEIQ5uKkk)
- `tools/margin_calc.py` 로 상품·채널별 **손익분기 ROAS** 를 먼저 계산한다.
  - ROAS < 손익분기 → 키워드/소재 단위로 축소 또는 OFF
  - ROAS > 목표 ROAS → 예산·입찰 확대 후보
- 광고비에는 VAT 10%가 붙는다(매입세액 공제 가능). 리포트 비교 시 기준을 통일한다.

## 폴더 구조
- `knowledge/transcripts/` — 유튜버 영상 자막 원문 (`tools/yt_transcripts.py` 로 수집, `INDEX.md` 목록). **원문은 저작권 때문에 .gitignore — 로컬(사장님 Mac)에만 존재**
- `knowledge/notes/` — 자막을 직접 요약한 영상별 노트 (`<업로드일>_<영상ID>.md`, 커밋 대상). 플레이북의 출처
- `tools/ad_report.py` — 네이버/쿠팡 광고 리포트 → 키워드별 실 ROAS vs 손익분기, 제외·하향·확대 후보
- `knowledge/video_queue.md` — 수집 대기 영상 목록 (채널별)
- `knowledge/sources.md` — 참고 유튜버/채널 목록
- `knowledge/playbook/` — 자막에서 추출·정리한 실행 지침 (네이버 광고, 쿠팡 광고, 상위노출)
  - 각 항목에 출처(영상 ID)를 단다. 출처 없는 항목은 `[검증필요]` 표시.
- `data/` — 상품 원가/가격 (실데이터 `products.json` 은 사용자 결정에 따라 커밋 여부 결정), 광고 리포트 CSV
- `docs/plans/` — superpowers 계획서, `docs/changes/` — 광고 변경 기록, `docs/owner-questions.md` — 사장님께 받을 정보

## 지식베이스 갱신 루틴
0. 환경 (사장님 Mac): `python3 -m venv .venv && .venv/bin/pip install yt-dlp certifi openpyxl` 후 `export PATH="$PWD/.venv/bin:$PATH"`.
   수집기는 certifi로 SSL 오류를 자동 처리. 클라우드 세션은 YouTube가 IP를 차단하므로 수집은 Mac에서만.
1. 새 영상 → `python3 tools/yt_transcripts.py video <ID>` / 여러 개는 `--ids-file ids.txt` ('-'로 시작하는 ID 때문)
2. 자막 읽고 → `knowledge/notes/<업로드일>_<ID>.md` 노트 작성(요약은 직접 문장으로, 원문 복붙 금지) → `knowledge/playbook/*.md` 해당 섹션에 출처 ID와 함께 반영. 충돌하면 최신 날짜 우선하되 둘 다 기록
3. 긴 자막은 앞 2/3 + 끝 1/3만 읽어도 결론은 대부분 잡힌다. 홍보성(강의/단톡방) 주장 수치는 그대로 믿지 말 것
3. 플랫폼 로직은 자주 바뀐다 (예: 2025 플러스스토어 개편, 애드부스트 출시). 항상 업로드일을 확인한다.
