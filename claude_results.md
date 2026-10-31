# 진행 결과 (최신 마일스톤으로 덮어쓰기)

## 대시보드 고객 관점 개편 — 2026-10-31 16:05 KST

### 공개 주소
https://sky1522.github.io/btc-agent-team/

### 바뀐 것
- 상단 KPI 카드 4개: 실제 이자 1위(기본 APY), 대형 풀 1위(TVL 1억 달러 이상), 예치형 풀 수·TVL 합계, 보상 의존 비중
- "오늘의 결론" 3줄 (reporter가 `data/summary.json`에 작성, 생성 시각은 도구가 파일 수정 시각으로 기록)
- 순위: 기본 APY 내림차순, 기본·보상 2구간 막대, 1 BTC 연 이자(BTC), TVL $M, 리스크 배지, DefiLlama 원본 링크. 데스크톱은 표, 760px 이하는 카드
- 리스크 분류(`tools/risk_map.toml`): 락업 / 보상 형태 / BTC 형태 / 체인 성숙도(출시 24개월 미만=신생). 근거 없으면 "확인 필요"
- 중복 "기본 APY 상위 5" 표 삭제, poolMeta 중복 정리, pool ID는 화면에서 숨김(동일 이름 풀은 "동일 이름 i/n")
- 면책 문구 삭제 및 재발 방지 규칙(CLAUDE.md, reporter)
- LP형 접힘 섹션에 실제 8행 표시 확인, 유형별 통계 맨 아래
- 라이트·다크, tabular-nums, CSP 유지, 스크립트·외부 폰트 없음

### 자동 갱신
- `.github/workflows/dashboard.yml`: 매일 08:00 KST 수집→분석→생성→커밋→Pages 배포(Claude 호출 없음). dashboard/ push 시 배포만
- AI 요약은 마지막 수동본 유지, 생성 시각 별도 표시
- `data/history.jsonl` merge=union: 로컬 게시와 자동 갱신 이력이 충돌 없이 합쳐짐. publish는 원격 자동 갱신 커밋을 받아 합친 뒤 다시 생성
- data/yields.json, data/analysis.json은 추적 해제(매번 재생성)

### 검증
- 테스트 52개 통과
- 실제 Pages 캡처: 데스크톱 1280 / 모바일 390 / 다크 390 — 가로 스크롤 없음, 넘침 요소 0, LP 8행
- 공개 파일 검사: 개인 정보·파일 경로·내부 설정 0건 (하단 문구의 저장소 경로 1건 발견 → 제거 후 재게시)
- CLI "대시보드 갱신해줘": 49초, 거부 0

### 다음에 내가 할 일
- 이 커밋 push 1회 (`! git push`) → 그 뒤 자동 갱신 워크플로 수동 실행으로 이력 누적 확인
