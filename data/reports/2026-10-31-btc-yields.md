# BTC 디파이 예치 이자율 일일 보고

기준 2026-10-31 15:05 KST · 출처 DefiLlama Yields (풀 링크: https://defillama.com/yields/pool/<pool id>)

표기: APY·% 소수 2자리, TVL $M 1자리는 표시 형식 변환만 적용. 원값은 data/analysis.json 참조.

## 1. 예치형 APY 상위 10

| 순위 | 프로토콜 | 체인 | 심볼 | APY 합계 (기본/보상) | TVL ($M) | 비고 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | symbiotic | Ethereum | SOLVBTC | 7.79 (0.00/7.79) | 5.8 | Solv Protocol-Solv Protocol-SolvBTC · 보상 의존 |
| 2 | accountable | Monad | CBBTC | 3.81 (3.60/0.21) | 40.7 | Earn ACC Points |
| 3 | accountable | Citrea | WCBTC | 3.22 (3.22/없음) | 6.3 | - |
| 4 | mezo-earn | Mezo | BTC | 3.01 (0.05/2.96) | 61.9 | Locked veBTC · 보상 의존 |
| 5 | midas-rwa | Ethereum | BTC | 2.35 (2.35/없음) | 20.3 | mHyperBTC |
| 6 | symbiotic | Ethereum | UNIBTC | 2.05 (0.00/2.05) | 5.6 | 보상 의존 |
| 7 | symbiotic | Ethereum | LBTC | 1.96 (0.00/1.96) | 45.0 | Lombard-Flow Traders-LBTC · 보상 의존 |
| 8 | stackingdao | Stacks | STBTC | 1.83 (1.83/없음) | 48.8 | - |
| 9 | across | Ethereum | WBTC | 1.09 (0.12/0.97) | 8.3 | 보상 의존 |
| 10 | lombard-lbtc | Ethereum | LBTC | 0.82 (0.82/없음) | 545.9 | - |

## 2. 기본 APY 상위 5 (보상 제외 실제 이자)

| 순위 | 프로토콜 | 체인 | 심볼 | 기본 APY | (참고) APY 합계 | TVL ($M) | 비고 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | accountable | Monad | CBBTC | 3.60 | 3.81 | 40.7 | Earn ACC Points |
| 2 | accountable | Citrea | WCBTC | 3.22 | 3.22 | 6.3 | - |
| 3 | midas-rwa | Ethereum | BTC | 2.35 | 2.35 | 20.3 | mHyperBTC |
| 4 | stackingdao | Stacks | STBTC | 1.83 | 1.83 | 48.8 | - |
| 5 | lombard-lbtc | Ethereum | LBTC | 0.82 | 0.82 | 545.9 | - |

## 3. 예치형 통계 요약 (stats.예치형)

- 풀 수 20 · TVL 합계 $1,503.4M
- APY 평균 1.44% · 중앙값 0.50% · TVL 가중 평균 0.77%
- 기본 비중 44.61% · 보상 비중 55.39%
- 보상 의존 5건

## 4. 어제 대비 변화

자체 전일 비교 불가(이전 날짜 스냅샷 없음, 2026-11-01 수집부터 가능). 신규·이탈도 "비교 데이터 없음".

DefiLlama 제공 1일 APY 변화 참고치 상위 5 (자체 비교 아님, apy_pct_1d_source, 변화폭 절대값 기준, 값이 없는 예치형 3건 제외):

| 순위 | 프로토콜 | 체인 | 심볼 | APY 합계 | 1일 변화 (%p) | TVL ($M) |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | symbiotic | Ethereum | SOLVBTC | 7.79 | +0.12 | 5.8 |
| 2 | lombard-lbtc | Ethereum | LBTC | 0.82 | -0.11 | 545.9 |
| 3 | across | Ethereum | WBTC | 1.09 | +0.08 | 8.3 |
| 4 | fluid-lending | Ethereum | CBBTC | 0.04 | -0.06 | 5.7 |
| 5 | accountable | Citrea | WCBTC | 3.22 | -0.05 | 6.3 |

예치형 1일 변화폭은 모두 0.13%p 미만으로 급변 신호 없음.

## 5. 리스크 메모

- 보상 의존 5건: symbiotic SOLVBTC·UNIBTC·LBTC, mezo-earn BTC, across WBTC. 보상 비중 55.39%.
- APY 합계 순위표 1위 symbiotic SOLVBTC는 기본 0.00 · 보상 7.79 · TVL $5.8M. 보상이 끝나면 이자가 사라지는 구조.
- 소형 TVL 풀(약 $5.4M~5.8M): symbiotic UNIBTC, bancor-v3 WBTC, fluid-lending CBBTC, symbiotic SOLVBTC. 이자율·유동성 변동 위험이 상대적으로 큼.
- accountable Monad CBBTC(APY 합계 순위표 2위, 기본 APY 순위표 1위)는 "Earn ACC Points" 풀로, 포인트 성격의 수익 포함 여부 확인 필요.
- 평균(1.44)과 중앙값(0.50)의 차이는 소수 고APY 풀의 영향.

## 6. 특이사항

- 전일 비교 데이터 없음: 오늘 스냅샷 4회(14:50, 14:54, 14:55, 15:05 KST)만 존재.
- APY 합계 상위 10 중 보상 의존 5건. 기본 APY 순위표 1위는 accountable Monad CBBTC(기본 3.60).
- LP형 참고: uniswap-v3 WBTC-CBBTC의 DefiLlama 1일 변화 -9.21%p(참고치, 자체 비교 아님).

본 보고는 참고 자료이며 투자 판단이 아니다.
