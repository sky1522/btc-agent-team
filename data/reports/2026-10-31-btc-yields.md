기준: 2026-10-31 14:55 KST · 출처: DefiLlama Yields

## 요약
- 예치형 20개, TVL 합계 약 1,503.4M USD, APY 범위 0.010~7.79%, 중앙값 약 0.50% (LP형 8개는 제외).
- 전일 스냅샷 없음: 전일 대비 비교 불가. 신규·이탈 판정도 불가.
- 보상 의존(보상 APY 비중 50% 이상) 5개: symbiotic SOLVBTC·UNIBTC·LBTC(100%), mezo-earn BTC(98.4%), across WBTC(89.1%).

## 표 1. 예치형 APY 상위 10
TVL 단위: 백만 USD

| 순위 | 프로토콜 | 체인 | 심볼 | APY 합계 (기본/보상, %) | TVL | 비고 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | symbiotic | Ethereum | SOLVBTC | 7.79 (0/7.79) | 5.85 | 보상 의존 · Solv Protocol-Solv Protocol-SolvBTC |
| 2 | accountable | Monad | CBBTC | 3.81 (3.60/0.21) | 40.70 | Earn ACC Points |
| 3 | accountable | Citrea | WCBTC | 3.22 (3.22/-) | 6.31 | - |
| 4 | mezo-earn | Mezo | BTC | 3.01 (0.05/2.96) | 61.90 | 보상 의존 · Locked veBTC |
| 5 | midas-rwa | Ethereum | BTC | 2.35 (2.35/-) | 20.27 | mHyperBTC |
| 6 | symbiotic | Ethereum | UNIBTC | 2.05 (0/2.05) | 5.59 | 보상 의존 |
| 7 | symbiotic | Ethereum | LBTC | 1.96 (0/1.96) | 44.96 | 보상 의존 · Lombard-Flow Traders-LBTC |
| 8 | stackingdao | Stacks | STBTC | 1.83 (1.83/-) | 48.85 | - |
| 9 | across | Ethereum | WBTC | 1.09 (0.12/0.97) | 8.33 | 보상 의존 |
| 10 | lombard-lbtc | Ethereum | LBTC | 0.82 (0.82/-) | 545.91 | - |

## 표 2. 예치형 1일 변화 상위 10 (절댓값 기준)
전일 스냅샷 없음 → DefiLlama 제공 apy_pct_1d_source 참고값, 자체 스냅샷 비교 아님.

| 순위 | 프로토콜 | 체인 | 심볼 | 현재 APY (%) | 1일 변화 (%p) | TVL (백만 USD) | 비고 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | symbiotic | Ethereum | SOLVBTC | 7.79 | +0.12 | 5.85 | 보상 의존 |
| 2 | lombard-lbtc | Ethereum | LBTC | 0.82 | -0.11 | 545.91 | - |
| 3 | across | Ethereum | WBTC | 1.09 | +0.08 | 8.33 | 보상 의존 |
| 4 | fluid-lending | Ethereum | CBBTC | 0.04 | -0.06 | 5.66 | - |
| 5 | accountable | Citrea | WCBTC | 3.22 | -0.05 | 6.31 | - |
| 6 | mezo-earn | Mezo | BTC | 3.01 | +0.04 | 61.90 | 보상 의존 |
| 7 | hyperlend-pooled | Hyperliquid L1 | UBTC | 0.19 | -0.04 | 9.03 | - |
| 8 | fluid-lending | Ethereum | WBTC | 0.09 | +0.03 | 24.76 | 946c7197 |
| 9 | fluid-lending | Ethereum | WBTC | 0.09 | +0.03 | 15.23 | 7c4da504 |
| 10 | symbiotic | Ethereum | UNIBTC | 2.05 | +0.03 | 5.59 | 보상 의존 |

예치형 변화는 전부 ±0.12%p 이내. aave-v3 3개(OP Mainnet·Arbitrum·Polygon)는 변화값 null.

## 특이사항
- 보상 의존 5개 중 symbiotic 3개(SOLVBTC·UNIBTC·LBTC)는 기본 APY 0이라 APY 전부가 보상. 보상 지속 여부에 따라 변동 가능.
- TVL 10M 미만 4개(상위 10 중): UNIBTC 5.59M, SOLVBTC 5.85M, Citrea WCBTC 6.31M, across WBTC 8.33M. accountable Monad CBBTC는 포인트 보상(ACC Points)이 APY에 미반영됐을 수 있음(analyst 의견).
- LP형 큰 변동(참고, 순위 대상 아님): uniswap-v3 WBTC-CBBTC 1.59% (-9.21%p), uniswap-v4 LBTC-CBBTC 0.82% (-4.71%p), fluid-dex WBTC-CBBTC 3.32% (-2.21%p), uniswap-v3 WBTC-KBTC 0.21% (-1.14%p).

## 원본 대조 차이
- 입력 B의 표 2는 fluid-lending WBTC를 1개(24.8M)만 올렸으나, yields.json에는 +0.03%p 풀이 2개(24.76M, 15.23M)이고 둘 다 UNIBTC(+0.0297)보다 큼. 원본 기준으로 8·9위에 두 풀을 넣고 ether.fi-stake EBTC(-0.02, 11위)는 제외함.
- 입력 B의 "TVL 10M 미만 5개"는 원본 기준 4개(위 특이사항). 나머지 수치는 원본과 일치.
- TVL 합계·중앙값은 입력 A 값을 그대로 옮김(원본 풀 값과 대조해 일치 확인).

참고 자료이며 투자 권유가 아님. 전일 대비 비교는 2026-11-01 수집분부터 가능.
