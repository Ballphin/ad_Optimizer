# Phase 2 계획 — 돈이 새는 곳 찾기 (데이터 받는 즉시 실행)

목표: 2주 안에 **광고 후 순이익 기준으로 적자를 멈춘다**. 매출 확대는 그 다음.
근거: knowledge/playbook/*.md (영상 노트 출처 포함)

## Step 1. 손익분기 ROAS 확정 (사장님 숫자 필요)
- `data/products.json` 작성 → `python3 tools/margin_calc.py data/products.json`
- 채널별·옵션별 손익분기 ROAS, 목표 ROAS(순이익 10%) 확정.
- 확인: 쿠팡 권장 350%·"보통 300%" 같은 숫자 대신 이 값으로만 판단한다. (Pb_wwIoBFT4)

## Step 2. 네이버 — 진짜 ROAS 다시 계산
1. 광고센터에서 **검색어별 전환 보고서 30일** 다운로드 (캠페인/광고그룹/검색어 + 노출·클릭·총비용·**구매완료 전환매출액·구매완료 전환수**). (cYXEIQ5uKkk)
2. `python3 tools/ad_report.py <파일> --platform naver --breakeven <값> --out docs/diagnosis-YYYY-MM-DD-naver.md`
3. 지금까지 "총 전환" ROAS로 판단해 왔는지 확인 → 그렇다면 실제 ROAS와의 차이가 손실의 큰 원인일 수 있음.
4. 애드부스트 사용 여부/비중 확인 → 사용 중이면 7일 OFF 실험안 작성. (yiofBVzN_CE)
5. 예산 소진 시각 확인 (알림 설정) → 오전 소진 그룹은 입찰 하향안. (o6jYSyld1yg)

## Step 3. 쿠팡 — 지면/키워드/광고비 비율
1. 광고 보고서(전체 캠페인, 30일, 키워드·지면 포함) 다운로드.
2. `python3 tools/ad_report.py <파일> --platform coupang --breakeven <값>` → 검색 vs 비검색 ROAS, 제외 키워드 후보.
3. 전체 매출 대비 광고비 비율 계산 (목표 10~15%). (228C8VlKyys)
4. 상품효율지수 그래프, 메인 키워드 입찰 단가 캡처. (1sESZC1FSe8, 8GQfoYV_xVw)

## Step 4. 상품 경쟁력 점검 (광고로 못 고치는 부분)
- 메인 키워드 첫 화면: 우리 상품 광고 칸/자연 칸, 경쟁 상위 5개의 가격·리뷰 수·형태(H/U/일자)·썸네일. (YnOnfxOW5kw, 9PjRiDI9IWg)
- 클릭 대비 전환율 — 100클릭에 1건도 없으면 광고 확대 금지, 상세/썸네일부터. (908KbYMVL4s)

## Step 5. 1차 변경안 (승인 후, 한 번에 한 가지씩)
- 손실 키워드 제외/분리·입찰 하향 → `docs/changes/` 기록 → 7일 후 비교.
- 산출물: `docs/diagnosis-YYYY-MM-DD.md` — "어디서 얼마가 새는지" 금액으로.
