import copy
import json
import subprocess
from datetime import datetime

import pytest

import analyze_yields as az
import publish_dashboard as pd
from common import KST


def sh(cwd, *args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


@pytest.fixture
def base_analysis(multi_day_history, config):
    return az.analyze(multi_day_history, config, datetime(2026, 10, 31, 15, 1, tzinfo=KST))


@pytest.fixture
def repo(tmp_path, base_analysis, config):
    """bare 원격 + 작업 저장소. 첫 커밋(대시보드 포함)은 원격에 push된 상태."""
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    sh(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    sh(tmp_path, "init", "-q", "-b", "main", str(work))
    sh(work, "config", "user.name", "t")
    sh(work, "config", "user.email", "t@example.com")
    sh(work, "config", "core.autocrlf", "false")
    sh(work, "remote", "add", "origin", str(remote))
    (work / "dashboard").mkdir()
    (work / "README.md").write_text("x", encoding="utf-8")
    (work / ".gitattributes").write_text("data/history.jsonl merge=union\n", encoding="utf-8")
    write_analysis(work, base_analysis, "2026-10-31 15:00 KST")
    pd.build_dashboard.run(config, root=work)
    sh(work, "add", "-A")
    sh(work, "commit", "-q", "-m", "init")
    sh(work, "push", "-q", "origin", "main")
    return work, remote


def write_analysis(work, analysis, as_of):
    """데이터 기준 시각만 바꾼 분석 결과를 쓴다 (대시보드 내용이 바뀌는 상황)."""
    a = copy.deepcopy(analysis)
    a["latest"]["collected_at_kst"] = as_of
    (work / "data").mkdir(exist_ok=True)
    (work / "data/analysis.json").write_text(json.dumps(a, ensure_ascii=False), encoding="utf-8")


def remote_files(remote):
    return set(sh(remote, "ls-tree", "-r", "--name-only", "main").splitlines())


def test_publishes_only_dashboard_files(repo, config, base_analysis):
    work, remote = repo
    write_analysis(work, base_analysis, "2026-10-31 16:00 KST")
    (work / "README.md").write_text("changed", encoding="utf-8")
    sh(work, "add", "README.md")  # 다른 파일이 스테이징돼 있어도
    r = pd.run(config, root=work)
    assert r["pushed"] and r["committed"]
    assert r["as_of"] == "2026-10-31 16:00 KST"
    last = sh(remote, "show", "--name-only", "--format=%s", "main").splitlines()
    assert last[0] == "dashboard: 데이터 기준 2026-10-31 16:00 KST"
    assert set(filter(None, last[1:])) == {"dashboard/index.html", "dashboard/data.json"}
    assert sh(remote, "show", "main:README.md") == "x"  # README 변경은 게시 안 됨
    assert "README.md" in sh(work, "diff", "--cached", "--name-only")
    assert "data/analysis.json" in sh(work, "status", "--short")  # 데이터 파일도 게시 안 됨


def test_hand_edited_html_is_overwritten_by_render(repo, config, base_analysis):
    work, remote = repo
    write_analysis(work, base_analysis, "2026-10-31 16:30 KST")
    (work / "dashboard/index.html").write_text("<script>alert(1)</script>", encoding="utf-8")
    pd.run(config, root=work)
    published = sh(remote, "show", "main:dashboard/index.html")
    assert "<script" not in published
    assert "기준 2026-10-31 16:30 KST" in published


def test_no_change_does_not_push(repo, config):
    work, remote = repo
    before = sh(remote, "rev-parse", "main")
    r = pd.run(config, root=work)
    assert not r["pushed"] and not r["committed"]
    assert sh(remote, "rev-parse", "main") == before


def test_aborts_when_other_unpushed_commit_exists(repo, config, base_analysis):
    work, remote = repo
    (work / "README.md").write_text("code change", encoding="utf-8")
    sh(work, "commit", "-q", "-am", "code")
    write_analysis(work, base_analysis, "2026-10-31 17:00 KST")
    before = sh(remote, "rev-parse", "main")
    with pytest.raises(pd.PublishError, match="다른 커밋"):
        pd.run(config, root=work)
    assert sh(remote, "rev-parse", "main") == before


def test_aborts_on_other_branch(repo, config):
    work, _ = repo
    sh(work, "checkout", "-q", "-b", "feature")
    with pytest.raises(pd.PublishError, match="브랜치"):
        pd.run(config, root=work)


def append_history(repo_dir, snapshot):
    with open(repo_dir / "data/history.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot, ensure_ascii=False) + "\n")


def test_syncs_when_remote_ahead_only_with_auto_update(repo, config, tmp_path,
                                                        multi_day_history):
    """매일 자동 갱신(원격)과 에이전트 게시(로컬)가 각각 이력을 추가해도 양쪽 줄이 모두 남는다."""
    work, remote = repo
    append_history(work, multi_day_history[0])
    sh(work, "add", "data/history.jsonl")
    sh(work, "commit", "-q", "-m", "history seed")
    sh(work, "push", "-q", "origin", "main")

    ci = tmp_path / "ci"
    sh(tmp_path, "clone", "-q", str(remote), str(ci))
    sh(ci, "config", "user.name", "bot")
    sh(ci, "config", "user.email", "bot@example.com")
    append_history(ci, multi_day_history[1])
    (ci / "dashboard/index.html").write_text("<p>ci build</p>", encoding="utf-8")
    sh(ci, "commit", "-q", "-am", "auto: 매일 수집")
    sh(ci, "push", "-q", "origin", "main")

    append_history(work, multi_day_history[2])          # 로컬 에이전트 수집 (미커밋)
    r = pd.run(config, root=work)
    assert r["pushed"]
    lines = sh(remote, "show", "main:data/history.jsonl").splitlines()
    stamps = sorted(json.loads(x)["collected_at"] for x in lines)
    assert stamps == ["2026-10-29T09:00:00+09:00", "2026-10-30T09:00:00+09:00",
                      "2026-10-30T15:00:00+09:00"]
    html = sh(remote, "show", "main:dashboard/index.html")
    assert "ci build" not in html                         # 합친 이력으로 다시 생성
    assert "기준 2026-10-30 15:00 KST" in html


def test_aborts_when_remote_is_ahead(repo, config, tmp_path, base_analysis):
    work, remote = repo
    other = tmp_path / "other"
    sh(tmp_path, "clone", "-q", str(remote), str(other))
    sh(other, "config", "user.name", "o")
    sh(other, "config", "user.email", "o@example.com")
    (other / "README.md").write_text("from elsewhere", encoding="utf-8")
    sh(other, "commit", "-q", "-am", "elsewhere")
    sh(other, "push", "-q", "origin", "main")
    write_analysis(work, base_analysis, "2026-10-31 18:00 KST")
    with pytest.raises(pd.PublishError, match="원격에"):
        pd.run(config, root=work)
