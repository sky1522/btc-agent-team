# 진행 결과 (최신 마일스톤으로 덮어쓰기)

## M0. 환경 점검·뼈대 — 완료 (2026-10-31)

### 환경
| 도구 | 버전 | 비고 |
| --- | --- | --- |
| git | 2.54.0 | user: sky1522 |
| Python | 3.11.9 | 가이드 권장 3.12지만 3.11로 충분. `requires-python >=3.11` |
| uv | 0.13.5 | |
| Node | 24.15.0 | |
| Bun | 1.4.4 | **새로 설치** (`~/.bun/bin`, 새 터미널부터 PATH 반영) |
| Claude Code | 2.1.316 | 채널 요구 2.1.80 이상 충족 |
| ruff / pytest | 0.17.3 / 9.2.0 | uv dev 그룹 |

### 만든 것
- `CLAUDE.md`: 총괄 역할·배정표·운영 규칙·기록 규칙 (도메인 무관). `@MEMORY.md` import로 기억 자동 로드
- `docs/project-brief.md`: BTC 이자율 도메인 목표·지표·리스크·보고 형식 (필터 기준은 M1에서 확정)
- `.claude/agents/`: researcher·analyst(sonnet), developer(inherit), reporter(sonnet). 도메인 지식은 브리프 참조
- `.claude/settings.json`: 허용 목록 초안 (M3에서 텔레그램 도구 추가)
- `pyproject.toml`(uv, ruff, pytest), `.gitignore`

### 구조 조정 (제안 대비)
- 기존 문서 4개 → `docs/`로 이동. 통화 전사·연락처 메모·녹음(m4a)은 `.gitignore` 처리. 운영 가이드는 커밋 대상
- `data/reports/` 추가: reporter 산출물 위치를 data/logs(커밋 제외)와 분리
- 하위 에이전트 모델: 구독 한도 절약 위해 조사·분석·보고는 sonnet, 개발만 총괄과 동일

### 확인 결과
- ruff 통과, pytest 0건(테스트는 M1부터)
- git status에서 통화 문서·녹음 미추적 확인

### 다음에 내가 할 일
- 없음. M1 진행 승인만
