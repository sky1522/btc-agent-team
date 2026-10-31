import json
import os
from datetime import datetime

import pytest

import analyze_yields as az
import build_dashboard as bd
from common import KST

AT = datetime(2026, 10, 30, 15, 10, tzinfo=KST)
OK_SUMMARY = {"data_as_of_kst": "2026-10-30 15:00 KST", "generated_at_kst": "2026-10-30 15:06 KST",
              "lines": ["결론 1", "결론 2", "결론 3"]}


@pytest.fixture
def analysis(multi_day_history, config):
    return az.analyze(multi_day_history, config, datetime(2026, 10, 30, 15, 5, tzinfo=KST))


def write_inputs(tmp_path, analysis, summary=None):
    d = tmp_path / "data"
    d.mkdir(exist_ok=True)
    (d / "analysis.json").write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
    if summary is not None:
        (d / "summary.json").write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")


def test_layout_order_and_header(analysis, config):
    html = bd.render(analysis, OK_SUMMARY, config["dashboard"])
    assert "데이터 기준 2026-10-30 15:00 KST" in html and "DefiLlama Yields" in html
    order = ["핵심 지표", "오늘의 결론", "예치형 순위", "전일 대비", "LP형 2개", "유형별 통계"]
    pos = [html.index(s) for s in order]
    assert pos == sorted(pos)
    assert "기본 APY 상위" not in html          # 중복 표 삭제


def test_kpi_cards(analysis, config):
    html = bd.render(analysis, None, config["dashboard"])
    for label in ("실제 이자 1위", "대형 풀 1위", "예치형 풀", "보상 의존 비중"):
        assert label in html
    assert "6.50%" in html                      # p-a 기본 APY
    assert "3개" in html


def test_rows_sorted_by_base_with_bar_link_badges(analysis, config):
    html = bd.render(analysis, None, config["dashboard"])
    main = html[html.index("예치형 순위"):html.index("전일 대비")]
    assert main.index("aave-v3") < main.index("euler-v2") < main.index("symbiotic")
    assert main.count('class="bar"') == 3
    assert main.count("DefiLlama 원본") == 3
    assert "https://defillama.com/yields/pool/p-a" in main
    assert "0.0650 BTC" in main                 # 1 BTC 연 이자 (기본 6.5%)
    assert "$102.0M" in main                    # TVL $M
    assert 'class="badge custodial">수탁형' in main
    assert "확인 필요: 락업" in main


def test_lp_section_has_rows_and_is_collapsed(analysis, config):
    html = bd.render(analysis, None, config["dashboard"])
    lp = html[html.index("<details>"):html.index("</details>")]
    assert "<details open" not in html
    assert lp.count('class="row pool"') == 2
    assert "uniswap-v3" in lp and "curve-dex" in lp


def test_no_disclaimer_no_script_csp(analysis, config):
    html = bd.render(analysis, OK_SUMMARY, config["dashboard"])
    assert "투자 권유" not in html and "참고 자료" not in html
    assert "<script" not in html
    assert "default-src 'none'" in html
    assert "prefers-color-scheme:dark" in html and "tabular-nums" in html


def test_summary_states(analysis, config):
    stale = dict(OK_SUMMARY, data_as_of_kst="2026-10-29 09:00 KST")
    assert bd.summary_status(None, analysis) == "missing"
    assert bd.summary_status(OK_SUMMARY, analysis) == "ok"
    assert bd.summary_status(stale, analysis) == "stale"
    html = bd.render(analysis, stale, config["dashboard"])
    assert "요약은 이전 데이터 기준" in html and "생성 2026-10-30 15:06 KST" in html
    assert "결론 3" in bd.render(analysis, OK_SUMMARY, config["dashboard"])
    assert "아직 없음" in bd.render(analysis, None, config["dashboard"])


def test_html_escapes_text(analysis, config):
    bad = dict(OK_SUMMARY, lines=["<img src=x onerror=alert(1)>"])
    html = bd.render(analysis, bad, config["dashboard"])
    assert "<img src=x" not in html and "&lt;img src=x" in html


def test_summary_generated_time_stamped_by_tool(tmp_path, analysis, config):
    s = {"data_as_of_kst": "2026-10-30 15:00 KST", "lines": ["a"]}  # 에이전트는 시각을 안 씀
    write_inputs(tmp_path, analysis, s)
    p = tmp_path / "data/summary.json"
    ts = datetime(2026, 10, 30, 15, 7, tzinfo=KST).timestamp()
    os.utime(p, (ts, ts))
    bd.run(config, root=tmp_path)
    saved = json.loads(p.read_text(encoding="utf-8"))
    assert saved["generated_at_kst"] == "2026-10-30 15:07 KST"


def test_missing_summary_keeps_last_published_one(tmp_path, analysis, config):
    write_inputs(tmp_path, analysis, OK_SUMMARY)
    bd.run(config, root=tmp_path)
    (tmp_path / "data/summary.json").unlink()        # 자동 갱신 환경: 요약 파일 없음
    r = bd.run(config, root=tmp_path)
    assert r["summary"] == "ok"
    assert "결론 1" in (tmp_path / "dashboard/index.html").read_text(encoding="utf-8")


def test_run_writes_html_and_data_deterministic(tmp_path, analysis, config):
    write_inputs(tmp_path, analysis)
    bd.run(config, root=tmp_path)
    first = (tmp_path / "dashboard/index.html").read_bytes()
    bd.run(config, root=tmp_path)
    assert (tmp_path / "dashboard/index.html").read_bytes() == first
    data = json.loads((tmp_path / "dashboard/data.json").read_text(encoding="utf-8"))
    assert data["analysis"]["latest"]["collected_at_kst"] == "2026-10-30 15:00 KST"


def test_run_without_analysis_fails(tmp_path, config):
    with pytest.raises(RuntimeError):
        bd.run(config, root=tmp_path)


def test_no_comparison_message(multi_day_history, config):
    a = az.analyze([multi_day_history[-1]], config, AT)
    assert "비교 데이터 없음" in bd.render(a, None, config["dashboard"])


def test_no_file_paths_on_page(analysis, config):
    html = bd.render(analysis, OK_SUMMARY, config["dashboard"])
    for ext in (".toml", ".jsonl", ".py", ".md", "tools/", "data/"):
        assert ext not in html
