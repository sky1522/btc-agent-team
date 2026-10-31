"""대시보드 산출물만 커밋하고 push한다. 에이전트가 push하는 유일한 경로.

실행: uv run python tools/publish_dashboard.py
설정: tools/config.toml [publish]

안전장치
- main 브랜치에서만 동작
- 아직 push 안 된 커밋 중 대시보드 파일 외 다른 파일을 바꾼 커밋이 있으면 중단(사람이 직접 push)
- 원격에 로컬에 없는 커밋이 있으면 중단(덮어쓰지 않음)
- 커밋은 [publish] files 경로만 (`git commit -- <files>`), 다른 스테이징 변경은 건드리지 않음
- 게시 직전에 build_dashboard로 다시 생성 → 누가 index.html을 직접 고쳤어도 렌더 결과만 게시
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import build_dashboard
from common import ROOT, load_config, resolve, utf8_stdout


class PublishError(RuntimeError):
    pass


def git(*args: str, root: Path = ROOT, check: bool = True) -> str:
    r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise PublishError(f"git {' '.join(args)} 실패: {(r.stderr or r.stdout).strip()}")
    return r.stdout.strip()


def unpushed_foreign_commits(remote_ref: str, allowed: set[str], root: Path) -> list[str]:
    """push 안 된 커밋 중 허용 파일 외를 바꾼 커밋 목록."""
    bad = []
    for sha in git("rev-list", f"{remote_ref}..HEAD", root=root).split():
        changed = set(git("diff-tree", "--no-commit-id", "--name-only", "-r", sha,
                          root=root).splitlines())
        if changed - allowed:
            bad.append(f"{sha[:7]} {sorted(changed - allowed)[:3]}")
    return bad


def run(config: dict | None = None, root: Path = ROOT) -> dict:
    config = config or load_config()
    pub = config["publish"]
    remote, branch, files = pub["remote"], pub["branch"], list(pub["files"])
    allowed = set(files)

    current = git("rev-parse", "--abbrev-ref", "HEAD", root=root)
    if current != branch:
        raise PublishError(f"현재 브랜치 {current}. {branch}에서만 게시한다")
    try:
        build_dashboard.run(config, root=root)  # 직접 수정된 산출물이 있어도 렌더 결과로 덮어씀
    except RuntimeError as ex:
        raise PublishError(str(ex)) from ex

    git("fetch", "--quiet", remote, branch, root=root)
    remote_ref = f"{remote}/{branch}"
    behind = git("rev-list", "--count", f"HEAD..{remote_ref}", root=root)
    if behind != "0":
        raise PublishError(f"원격에 로컬에 없는 커밋 {behind}개. 사람이 먼저 pull 후 확인")
    foreign = unpushed_foreign_commits(remote_ref, allowed, root)
    if foreign:
        raise PublishError(f"push 안 된 다른 커밋이 있어 중단(사람이 직접 push): {foreign}")

    git("add", "--", *files, root=root)
    changed = git("diff", "--cached", "--name-only", "--", *files, root=root)
    data_path = resolve(config["paths"]["dashboard_data"], root)
    data = json.loads(data_path.read_text(encoding="utf-8")) if data_path.exists() else {}
    as_of = (data.get("analysis") or {}).get("latest", {}).get("collected_at_kst", "?")
    committed = False
    if changed:
        git("commit", "-q", "-m", f"dashboard: 데이터 기준 {as_of}", "--", *files, root=root)
        committed = True
    ahead = git("rev-list", "--count", f"{remote_ref}..HEAD", root=root)
    pushed = False
    if ahead != "0":
        git("push", "--quiet", remote, f"HEAD:{branch}", root=root)
        pushed = True
    return {"committed": committed, "pushed": pushed, "as_of": as_of,
            "commit": git("rev-parse", "--short", "HEAD", root=root),
            "pages_url": pub["pages_url"]}


def main() -> int:
    utf8_stdout()
    try:
        r = run()
    except PublishError as ex:
        print(f"게시 중단: {ex}", file=sys.stderr)
        return 1
    if not r["pushed"]:
        print(f"변경 없음(이미 게시됨). 데이터 기준 {r['as_of']} · {r['pages_url']}")
    else:
        print(f"게시 완료: 커밋 {r['commit']} push · 데이터 기준 {r['as_of']}")
        print(f"Pages 반영은 보통 1~2분 소요 → {r['pages_url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
