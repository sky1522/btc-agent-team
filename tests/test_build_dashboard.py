import json
from datetime import datetime

import pytest

import analyze_yields as az
import build_dashboard as bd
from common import KST

AT = datetime(2026, 10, 30, 15, 10, tzinfo=KST)


@pytest.fixture
def analysis(multi_day_history, config):
    return az.analyze(multi_day_history, config, datetime(2026, 10, 30, 15, 5, tzinfo=KST))


def write_inputs(tmp_path, analysis, summary=None):
    d = tmp_path / "data"
    d.mkdir()
    (d / "analysis.json").write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
    if summary is not None:
        (d / "summary.json").write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")


def test_ranking_contains_all_primary_pools(analysis):
    assert [r["pool"] for r in analysis["ranking"]] == ["p-a", "p-d", "p-b"]
    assert all(r["type"] == "예치형" for r in analysis["ranking"])


def test_html_has_header_sections_and_rows(analysis, config):
    html = bd.render(analysis, None, config["dashboard"])
    assert "기준 2026-10-30 15:00 KST" in html
    assert "DefiLlama Yields" in html
    for section in ("예치형 순위", "기본 APY 상위 2", "유형별 통계", "전일 대비"):
        assert section in html
    assert "aave-v3" in html and "euler-v2" in html
    assert "보상 의존" in html                       # p-b 플래그
    assert "LP형 2개 (순위 제외, 참고)" in html     # LP는 접힌 섹션
    assert 'name="viewport"' in html
    assert "<script" not in html                     # 외부·내부 스크립트 없음


def test_summary_states(analysis, config):
    ok = {"written_at_kst": "2026-10-30 15:06 KST", "data_as_of_kst": "2026-10-30 15:00 KST",
          "lines": ["요약 1줄"]}
    stale = dict(ok, data_as_of_kst="2026-10-29 09:00 KST")
    assert bd.summary_status(None, analysis) == "missing"
    assert bd.summary_status(ok, analysis) == "ok"
    assert bd.summary_status(stale, analysis) == "stale"
    assert "요약이 최신 데이터보다 오래됨" in bd.render(analysis, stale, config["dashboard"])
    assert "요약 1줄" in bd.render(analysis, ok, config["dashboard"])
    assert "요약 없음" in bd.render(analysis, None, config["dashboard"])


def test_html_escapes_text(analysis, config):
    bad = {"written_at_kst": "x", "data_as_of_kst": "2026-10-30 15:00 KST",
           "lines": ["<img src=x onerror=alert(1)>"]}
    html = bd.render(analysis, bad, config["dashboard"])
    assert "<img src=x" not in html
    assert "&lt;img src=x" in html


def test_run_writes_html_and_data(tmp_path, analysis, config):
    write_inputs(tmp_path, analysis)
    r = bd.run(config, root=tmp_path)
    assert r["summary"] == "missing"
    assert (tmp_path / "dashboard/index.html").read_text(encoding="utf-8").startswith("<!doctype")
    data = json.loads((tmp_path / "dashboard/data.json").read_text(encoding="utf-8"))
    assert data["analysis"]["latest"]["collected_at_kst"] == "2026-10-30 15:00 KST"


def test_output_is_deterministic(tmp_path, analysis, config):
    write_inputs(tmp_path, analysis)
    bd.run(config, root=tmp_path)
    first = (tmp_path / "dashboard/index.html").read_bytes()
    bd.run(config, root=tmp_path)
    assert (tmp_path / "dashboard/index.html").read_bytes() == first


def test_csp_blocks_scripts(analysis, config):
    html = bd.render(analysis, None, config["dashboard"])
    assert "Content-Security-Policy" in html and "default-src 'none'" in html


def test_run_without_analysis_fails(tmp_path, config):
    with pytest.raises(RuntimeError):
        bd.run(config, root=tmp_path)


def test_no_comparison_message(multi_day_history, config):
    a = az.analyze([multi_day_history[-1]], config, AT)
    assert "전일 대비: 비교 데이터 없음" in bd.render(a, None, config["dashboard"])
