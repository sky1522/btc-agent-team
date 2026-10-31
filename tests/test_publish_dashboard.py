import json
import subprocess

import pytest

import publish_dashboard as pd


def sh(cwd, *args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """bare 원격 + 작업 저장소. 첫 커밋은 원격에 push된 상태."""
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
    write_dashboard(work, "2026-10-31 15:00 KST")
    sh(work, "add", "-A")
    sh(work, "commit", "-q", "-m", "init")
    sh(work, "push", "-q", "origin", "main")
    return work, remote


def write_dashboard(work, as_of):
    (work / "dashboard/index.html").write_text(f"<p>{as_of}</p>", encoding="utf-8")
    data = {"analysis": {"latest": {"collected_at_kst": as_of}}}
    (work / "dashboard/data.json").write_text(json.dumps(data), encoding="utf-8")


def remote_files(remote):
    return set(sh(remote, "ls-tree", "-r", "--name-only", "main").splitlines())


def test_publishes_only_dashboard_files(repo, config):
    work, remote = repo
    write_dashboard(work, "2026-10-31 16:00 KST")
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


def test_no_change_does_not_push(repo, config):
    work, remote = repo
    before = sh(remote, "rev-parse", "main")
    r = pd.run(config, root=work)
    assert not r["pushed"] and not r["committed"]
    assert sh(remote, "rev-parse", "main") == before


def test_aborts_when_other_unpushed_commit_exists(repo, config):
    work, remote = repo
    (work / "README.md").write_text("code change", encoding="utf-8")
    sh(work, "commit", "-q", "-am", "code")
    write_dashboard(work, "2026-10-31 17:00 KST")
    before = sh(remote, "rev-parse", "main")
    with pytest.raises(pd.PublishError, match="다른 커밋"):
        pd.run(config, root=work)
    assert sh(remote, "rev-parse", "main") == before


def test_aborts_on_other_branch(repo, config):
    work, _ = repo
    sh(work, "checkout", "-q", "-b", "feature")
    with pytest.raises(pd.PublishError, match="브랜치"):
        pd.run(config, root=work)


def test_aborts_when_remote_is_ahead(repo, config, tmp_path):
    work, remote = repo
    other = tmp_path / "other"
    sh(tmp_path, "clone", "-q", str(remote), str(other))
    sh(other, "config", "user.name", "o")
    sh(other, "config", "user.email", "o@example.com")
    (other / "README.md").write_text("from elsewhere", encoding="utf-8")
    sh(other, "commit", "-q", "-am", "elsewhere")
    sh(other, "push", "-q", "origin", "main")
    write_dashboard(work, "2026-10-31 18:00 KST")
    with pytest.raises(pd.PublishError, match="원격에"):
        pd.run(config, root=work)
