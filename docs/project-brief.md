# 프로젝트 브리프: BTC 디파이 예치 이자율

도메인 지식은 이 파일에만 둔다. 주제를 바꾸면 이 파일과 `tools/`만 교체한다.

## 목표
- 디파이 프로토콜별 BTC 계열 토큰 예치 이자율(APY)을 매일 수집·비교한다.
- 변화가 큰 풀과 리스크 신호를 짧게 보고한다.
- 결과는 텔레그램 보고 + 정적 대시보드로 본다.

## 대상 사용자
- 비개발자 1인. 텔레그램으로 지시하고 숫자 위주 요약을 받는다.
- 투자 판단은 사용자가 직접 한다. 에이전트는 공개 데이터 조회·분석·보고만 한다.

## 데이터
- 출처: DefiLlama Yields API `https://yields.llama.fi/pools` (무료, 키 없음)
- 출처 표기: `DefiLlama Yields` + 풀 링크 `https://defillama.com/yields/pool/<pool id>`
- 시각: 수집 시각을 KST로 기록

## 데이터 갱신
- 명령: `uv run python tools/defillama_btc.py` (M1에서 확정)
- 출력: `data/yields.json`(최신 스냅샷), `data/history.jsonl`(수집 1회당 1줄 누적)

## BTC 계열 풀 필터 기준
M1에서 실제 API 응답을 확인한 뒤 확정한다.
- 후보 토큰: WBTC, cbBTC, tBTC, BTCB, LBTC, SolvBTC 등 BTC 래핑·스테이킹 토큰
- 노이즈 제거 기준(TVL 하한 등)은 설정값으로 분리

## 핵심 지표
| 지표 | 정의 |
| --- | --- |
| APY 합계 | 기본 APY + 보상 APY (%) |
| 기본 APY | 프로토콜 자체 수익 (%) |
| 보상 APY | 토큰 보상 등 인센티브 (%). 비중이 크면 지속성 낮음 |
| TVL | 예치 총액 (USD) |
| 1일 변화 | 전일 대비 APY 변화 (%p) |

## 리스크 메모 기준 (analyst 참고)
- 보상 APY 비중이 50% 이상이면 "보상 의존" 표시
- TVL이 작을수록 이자율 변동·유동성 리스크 큼
- 하루 APY 변화가 크면 일시적 이벤트 가능성 표시

## 보고 형식 (reporter 참고)
- 첫 줄: 기준 시각(KST) · 출처
- 표: 순위, 프로토콜, 체인, 심볼, APY(기본/보상), TVL
- 마지막: 특이사항 3줄 이내
