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
- 명령: `uv run python tools/defillama_btc.py` (인자 없음. 설정은 `tools/config.toml`)
- 출력: `data/yields.json`(최신 스냅샷), `data/history.jsonl`(수집 1회당 1줄 누적)
- 소요: 약 5~10초 (전체 풀 약 1.6만 개 응답을 받아 필터)

## 분석 명령
- 명령: `uv run python tools/analyze_yields.py` (인자 없음. 설정은 `tools/config.toml [analyze]`)
- 입력: `data/history.jsonl` / 출력: `data/analysis.json`
- 내용: 예치형 APY 상위 N개(`top`, 보상 의존 표시), 기본 APY 상위 5개(`top_by_base`), 유형별 요약 통계(`stats`), 예치형 전일 대비 APY 변화 상위 N개(`change`), 신규·이탈 풀, LP형 상위 N개(별도 섹션 `secondary`)
- `stats.<유형>`: count, tvl_usd_sum, apy_mean, apy_median, apy_tvl_weighted(TVL 가중 평균), base_share_pct·reward_share_pct(APY 합계 중 기본/보상 비중 %), reward_dependent_count
- 에이전트는 이 값만 인용한다. 직접 계산 금지
- 전일 = 최신 스냅샷의 KST 날짜보다 이전 날짜 중 가장 최근 스냅샷. 없으면 "비교 데이터 없음"
- 위 두 명령 외 계산이 필요하면 developer에게 도구 추가를 맡긴다(임의 코드 실행 금지)

## 데이터 필드 (data/yields.json `pools[]`)
| 필드 | 원본(DefiLlama) | 의미 |
| --- | --- | --- |
| type | exposure | 예치형 / LP형 (아래 "풀 유형") |
| project, chain, symbol | project, chain, symbol | 프로토콜, 체인, 심볼 |
| pool_meta, note | poolMeta | 풀 부가 설명 / 표시용 비고 (아래 "비고 규칙") |
| il_risk | ilRisk | 비영구 손실 위험 여부 |
| apy / apy_base / apy_reward | apy / apyBase / apyReward | APY 합계 / 기본 / 보상 (%, null = 해당 없음) |
| tvl_usd | tvlUsd | 예치 총액 USD |
| apy_pct_1d_source | apyPct1D | DefiLlama 제공 1일 APY 변화(%p), 참고용 |
| url | pool | `https://defillama.com/yields/pool/<pool>` |

## BTC 계열 풀 필터 기준 (설정: `tools/config.toml [collect]`)
2026-10-31 실제 응답 확인 후 확정. BTC 문자열 포함 심볼 1,172개 중 아래 기준 통과분만 사용(14:50 기준 28개).
1. **토큰**: 심볼을 `-`로 나눈 구성 토큰이 **모두** BTC 계열 목록(`btc_tokens`)에 있어야 한다(대소문자 무시).
   - 포함 예: `WBTC`, `cbBTC`, `WBTC-CBBTC`(BTC끼리 LP) / 제외 예: `WBTC-USDC`(가격 변동 노출), `BTCBULL`(목록 밖)
   - 목록: BTC, WBTC(.E/.B), BTC.B, CBBTC, WCBTC, TBTC, BTCB, LBTC, SOLVBTC, XSOLVBTC, UBTC, XBTC, KBTC, FBTC, EBTC, UNIBTC, ENZOBTC, PUMPBTC, STBTC, STRKBTC, HEMIBTC
   - **제외 토큰**: `STSTXBTC` — 기초자산이 STX(DefiLlama underlyingTokens `coingecko:blockstack`). BTC가 아닌 자산을 맡기고 sBTC로 보상받는 상품이라 "BTC를 맡기는 곳"이 아님
   - `STBTC`는 유지 — StackingDAO·Zest는 sBTC 기반, Dolomite는 Lorenzo stBTC(BTC 스테이킹 토큰)
2. **TVL 하한**: `min_tvl_usd = 5,000,000` USD
3. **APY 하한**: `min_apy = 0.01` % (이자 거의 없는 빈 대출 풀 제외)
4. **이상치**: DefiLlama `outlier = true` 제외
5. APY 또는 TVL이 null이면 제외

## 풀 유형 (설정: `tools/config.toml [collect.type_by_exposure]`)
| 유형 | DefiLlama `exposure` | 의미 | 사용처 |
| --- | --- | --- | --- |
| 예치형 | single | 토큰 1개를 맡김 (렌딩·스테이킹·리스테이킹) | **기본 순위표·변화 분석**. "BTC를 맡기면 이자 주는 곳"의 본 답 |
| LP형 | multi | 토큰 2개 이상 유동성 공급 | `analysis.json`의 `secondary` 섹션에만 |
- `ilRisk`는 `il_risk` 필드로 저장만 한다(BTC끼리 풀이라 현재 전부 `no`).

## 비고(note) 규칙
- 기본값: DefiLlama `poolMeta` (마켓 이름 등)
- 같은 프로토콜·체인·심볼이 여러 줄이면 구분되게: poolMeta가 서로 다르면 poolMeta, 아니면 pool id 앞 8자리를 붙인다(예: `946c7197`)

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
- 표: 순위, 프로토콜, 체인, 심볼, APY(기본/보상), TVL, 비고 — **예치형만**. LP형은 요청 시에만 별도 표
- 보고서에는 **기본 APY 기준 상위 5** 표를 별도로 넣는다(보상·포인트 의존 수익과 실제 이자 구분)
- 마지막: 특이사항 3줄 이내
