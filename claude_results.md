# 진행 결과 (최신 마일스톤으로 덮어쓰기)

## M1. 데이터 수집 도구 — 완료 (2026-10-31 14:45 KST)

### 한 것
- DefiLlama `https://yields.llama.fi/pools` 실제 호출로 구조 확인: `{status, data[]}`, 풀 15,920개, 풀당 28개 필드
  (사용 필드: pool, project, chain, symbol, poolMeta, apy, apyBase, apyReward, tvlUsd, apyPct1D, outlier, exposure)
- `tools/defillama_btc.py`: 수집 → `data/yields.json`(스냅샷) + `data/history.jsonl`(1회 1줄 누적). 실패 시 기존 파일 보존
- `tools/analyze_yields.py`: 이력 → `data/analysis.json` (상위 N, 전일 대비 변화, 신규·이탈, 보상 의존 표시). 하루치만 있으면 "비교 데이터 없음"
- `tools/config.toml`: 인자 대신 설정 파일 (TVL 하한, APY 하한, 이상치 제외, BTC 토큰 목록, top_n 등)
- 필터 기준을 `docs/project-brief.md`에 확정 기록
- `.claude/settings.json`: 허용 명령 2개 정확한 문자열로 추가, curl·wget·Invoke-WebRequest·iwr·Invoke-RestMethod·irm 차단(Bash·PowerShell 양쪽)

### 확인 결과
- ruff 통과, pytest 19개 통과 (fixture: `tests/fixtures/pools_sample.json` 실제 레코드 기반 10건, `history_multi_day.jsonl` 3일치 샘플)
- 실제 수집: BTC 계열 풀 77개 (BTC 포함 심볼 1,172개 중 필터 통과)
- deny 규칙 동작 확인: 이 세션에서도 `curl` 호출이 차단됨
- Windows 출력 한글 깨짐(cp949) → 스크립트에서 UTF-8 고정으로 해결

### 실제 수집 상위 10개 (기준 2026-10-31 14:45 KST · 출처 DefiLlama Yields)
| # | 프로토콜 | 체인 | 심볼 | APY | 기본 | 보상 | TVL($M) | 비고 |
|---|---|---|---|---|---|---|---|---|
| 1 | orca-dex | Solana | CBBTC-WBTC | 10.95 | 10.95 | 0.00 | 1.2 | |
| 2 | liminal-basis | Hyperliquid L1 | XBTC | 10.22 | 10.22 | - | 1.2 | |
| 3 | chainflip-amm | Bitcoin | BTC | 9.75 | 9.75 | - | 4.9 | |
| 4 | ekubo | Starknet | SOLVBTC-STRKBTC | 8.32 | 0.00 | 8.32 | 1.4 | 보상 의존 |
| 5 | stackingdao | Stacks | STSTXBTC | 7.90 | 7.90 | - | 8.7 | |
| 6 | symbiotic | Ethereum | SOLVBTC | 7.79 | 0.00 | 7.79 | 5.8 | 보상 의존 |
| 7 | ekubo | Starknet | WBTC-STRKBTC | 7.09 | 0.37 | 6.72 | 5.3 | 보상 의존 |
| 8 | uniswap-v3 | Arbitrum | WBTC-CBBTC | 7.06 | 7.06 | - | 1.2 | |
| 9 | uniswap-v4 | Ethereum | WBTC-CBBTC | 5.36 | 5.36 | - | 3.8 | |
| 10 | symbiotic | Ethereum | SOLVBTC | 5.17 | 0.00 | 5.17 | 2.9 | 보상 의존 |

### 남은 확인
- `PowerShell(...)` deny 규칙 문법이 유효한지 M2의 `claude -p` 실행 때 경고 여부로 확인

### 다음에 내가 할 일
- 필터 결과 판단: 상위권이 TVL $1~5M 소형 풀 위주. 데모용으로 TVL 하한을 $5M로 올릴지 결정 (`tools/config.toml` 1줄)
- M2 진행 승인
