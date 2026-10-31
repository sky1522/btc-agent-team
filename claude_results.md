# 진행 결과 (최신 마일스톤으로 덮어쓰기)

## M3·M4 + 공개 배포 준비 — 2026-10-31 15:28 KST

### M3 텔레그램
- 플러그인 `telegram@claude-plugins-official` 프로젝트 범위 설치, 허용 도구 reply/react/edit_message
- `scripts/start-agent.ps1`: Bun·토큰 확인 후 `claude --channels plugin:telegram@claude-plugins-official`
- 승인 버튼: 플러그인이 권한 중계(Allow/Deny 인라인 버튼) 내장 확인(server.ts)
- 차단 실험: PowerShell curl·Invoke-WebRequest·irm, Bash curl 4건 모두 거부
- 샌드박스: Windows 네이티브 미지원(공식 문서) → deny + 정확한 명령 허용으로 확정
- **실기기 테스트 미확인**: 이 PC에 토큰 폴더(`~/.claude/channels/telegram/`)와 텔레그램 수신 세션 기록이 없음 → 응답 시간 측정 불가

### M4 대시보드
- `tools/build_dashboard.py` → `dashboard/index.html`(+ `data.json`): 예치형 순위(기본/보상 구분), 기본 APY 상위 5, 유형별 통계, AI 요약(`data/summary.json`, 오래되면 경고), 전일 대비, LP형 접힘
- 상단 고정 기준 시각·출처, 모바일 우선, 외부 라이브러리·스크립트 없음, CSP로 스크립트 차단, 같은 입력 → 같은 출력
- `tools/publish_dashboard.py`: 재생성 → 대시보드 파일만 커밋·push. main 외 브랜치, 다른 미push 커밋, 원격 앞섬이면 중단
- `.github/workflows/pages.yml`: dashboard/만 Pages 배포. Pages 소스는 이미 GitHub Actions
- 허용 목록: build/publish 명령 정확한 문자열. `Write/Edit(/dashboard/**)` 제거(보안 리뷰 반영), `PowerShell(git push*)` deny 추가
- 테스트 44개 통과

### 공개 저장소 검사
- 이력 전체: 운영 가이드(고객 이름·비용·강사 정보) 1건이 첫 커밋에 포함 → filter-branch로 전 이력에서 제거, reflog·gc 정리. 원본은 로컬 유지 + .gitignore
- 재검사(모든 커밋 파일·모든 blob·커밋 메시지): 고객 이름·연락처·비용·개인 경로 0건
- data/logs(커밋 제외): 개인 경로 36곳 `~`로 치환
- 커밋 작성자 이메일은 기존 공개 저장소에서도 이미 사용 중

### 다음에 내가 할 일
- 최초 push 1회 (`git push`는 에이전트 deny 규칙으로 막혀 있음)
- 텔레그램 토큰 등록·페어링 (M3 안내 단계)
