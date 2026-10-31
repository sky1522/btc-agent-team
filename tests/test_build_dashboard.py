import json
import os
import re
from datetime import datetime

import pytest

import analyze_yields as az
import build_dashboard as bd
from common import KST

AT = datetime(2026, 10, 30, 15, 10, tzinfo=KST)
OK_SUMMARY = {"data_as_of_kst": "2026-10-30 15:00 KST", "generated_at_kst": "2026-10-30 15:06 KST",
              "lines": ["실제 이자는 6%대가 최고입니다.", "큰 풀도 6.50%입니다."]}
PRICE = {"usd": 77000, "krw": 103_000_000, "as_of_kst": "2026-10-30 15:00 KST",
         "source": "CoinGecko"}


def _series(vals):
    return [{"d": f"2026-10-{i + 1:02d}", "base": v, "apy": v} for i, v in enumerate(vals)]


@pytest.fixture
def analysis(multi_day_history, config):
    charts = {"p-a": _series([6.0 + i * 0.02 for i in range(30)]),
              "p-d": _series([3.0] * 30)}
    return az.analyze(multi_day_history, config, datetime(2026, 10, 30, 15, 5, tzinfo=KST),
                      {"charts": charts, "btc_price": PRICE})


def write_inputs(tmp_path, analysis, summary=None):
    d = tmp_path / "data"
    d.mkdir(exist_ok=True)
    (d / "analysis.json").write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
    if summary is not None:
        (d / "summary.json").write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")


def test_layout_order(analysis, config):
    html = bd.render(analysis, OK_SUMMARY, config["dashboard"])
    order = ["밝기 전환", "안정 우선", "이자 우선", "오늘의 결론", "이자 vs 규모 지도",
             "실제 이자와 보상", "실제 이자 상위 5", "나머지 ", "LP형 2개 보기", "유형별 통계 보기"]
    pos = [html.index(s, html.index("<body>")) for s in order]
    assert pos == sorted(pos)
    assert "10월 30일 15:00 기준" in html and "DefiLlama Yields" in html


def test_rec_cards(analysis, config):
    html = bd.render(analysis, OK_SUMMARY, config["dashboard"])
    rec = html[html.index('aria-label="추천"'):html.index("오늘의 결론")]
    assert "aave-v3" in rec                              # 안정 우선 = TVL 1억 달러 이상 1위
    assert "6.50%" in rec and "0.0650 BTC" in rec
    assert "약 670만 원" in rec                           # 0.065 × 1.03억
    assert rec.count('class="spark"') >= 1                # 30일 추이선
    assert "위험 " in rec and "DefiLlama에서 원본 보기" in rec


def test_conclusion_large_text(analysis, config):
    html = bd.render(analysis, OK_SUMMARY, config["dashboard"])
    assert '<p class="concl-text">실제 이자는 6%대가 최고입니다. 큰 풀도 6.50%입니다.</p>' in html
    size = re.search(r"\.concl-text\{font-size:(\d+)px", html)
    assert size and int(size.group(1)) >= 20


def test_charts_svg_inline_with_legend_and_notes(analysis, config):
    html = bd.render(analysis, OK_SUMMARY, config["dashboard"])
    assert html.count('class="chart"') == 2
    assert "예치 규모 TVL (로그 눈금, 달러)" in html and "대형 풀 기준" in html
    assert "위험 낮음" in html and "위험 보통" in html and "위험 높음" in html  # 범례 글자
    assert 'fill="url(#hatch)"' in html                   # 보상 구간 빗금 패턴
    assert "큰 풀일수록 이자가 낮습니다" in html or "점 하나가 풀 하나입니다" in html
    assert "빗금 친 보상 구간은" in html
    assert "<title>" in html                              # 마우스 올리면 값 표시


def test_top5_cards_and_rest_collapsed(analysis, config):
    html = bd.render(analysis, OK_SUMMARY, config["dashboard"])
    top = html[html.index('id="h-top"'):html.index("나머지 ")]
    assert top.count('class="pool reveal"') == 3          # fixture 예치형 3개
    for label in ("30일 평균", "7일 변화", "보상 APY", "TVL"):
        assert label in top
    assert "↑ 0.14%p" in top                              # p-a 7일 변화 (기본 APY)
    assert "<details open" not in html


def test_lp_rows_inside_details(analysis, config):
    html = bd.render(analysis, OK_SUMMARY, config["dashboard"])
    lp = html[html.index("LP형 2개 보기"):]
    lp = lp[:lp.index("</details>")]
    assert "uniswap-v3" in lp and "curve-dex" in lp


def test_theme_toggle_css_only_and_motion(analysis, config):
    html = bd.render(analysis, OK_SUMMARY, config["dashboard"])
    assert '<input type="checkbox" id="theme"' in html and ":root:has(#theme:checked)" in html
    assert "prefers-color-scheme:dark" in html
    assert "@media (prefers-reduced-motion:no-preference)" in html   # 모션은 이 안에서만
    assert "infinite" not in html
    assert "<script" not in html and "default-src 'none'" in html
    assert "tabular-nums" in html


def test_no_disclaimer_no_paths(analysis, config):
    html = bd.render(analysis, OK_SUMMARY, config["dashboard"])
    assert "투자 권유" not in html and "참고 자료" not in html
    for s in (".toml", ".jsonl", ".py", "tools/", "data/"):
        assert s not in html


def test_summary_states(analysis, config):
    stale = dict(OK_SUMMARY, data_as_of_kst="2026-10-29 09:00 KST")
    assert bd.summary_status(None, analysis) == "missing"
    assert bd.summary_status(OK_SUMMARY, analysis) == "ok"
    assert bd.summary_status(stale, analysis) == "stale"
    assert "요약은 이전 데이터 기준" in bd.render(analysis, stale, config["dashboard"])
    assert "아직 없습니다" in bd.render(analysis, None, config["dashboard"])


def test_html_escapes_text(analysis, config):
    bad = dict(OK_SUMMARY, lines=["<img src=x onerror=alert(1)>"])
    html = bd.render(analysis, bad, config["dashboard"])
    assert "<img src=x" not in html and "&lt;img src=x" in html


@pytest.mark.parametrize(("v", "out"), [(670_000, "약 67만 원"), (123_450_000, "약 1억 2,345만 원"),
                                        (100_000_000, "약 1억 원"), (None, "")])
def test_krw_format(v, out):
    assert bd.krw(v) == out


def test_sparkline_and_delta():
    assert bd.sparkline([1.0]) == '<span class="spark-none">추이 없음</span>'
    svg = bd.sparkline([1.0, 2.0, 1.5])
    assert 'pathLength="1"' in svg and "최저 1.00%, 최고 2.00%" in svg
    assert "↑ 0.30%p" in bd.delta(0.3) and "↓ 0.30%p" in bd.delta(-0.3)
    assert "변화 없음" in bd.delta(0.0)


def test_summary_generated_time_stamped_by_tool(tmp_path, analysis, config):
    s = {"data_as_of_kst": "2026-10-30 15:00 KST", "lines": ["a"]}  # 에이전트는 시각을 안 씀
    write_inputs(tmp_path, analysis, s)
    p = tmp_path / "data/summary.json"
    ts = datetime(2026, 10, 30, 15, 7, tzinfo=KST).timestamp()
    os.utime(p, (ts, ts))
    bd.run(config, root=tmp_path)
    assert json.loads(p.read_text(encoding="utf-8"))["generated_at_kst"] == "2026-10-30 15:07 KST"


def test_missing_summary_keeps_last_published_one(tmp_path, analysis, config):
    write_inputs(tmp_path, analysis, OK_SUMMARY)
    bd.run(config, root=tmp_path)
    (tmp_path / "data/summary.json").unlink()        # 자동 갱신 환경: 요약 파일 없음
    assert bd.run(config, root=tmp_path)["summary"] == "ok"


def test_run_deterministic(tmp_path, analysis, config):
    write_inputs(tmp_path, analysis)
    bd.run(config, root=tmp_path)
    first = (tmp_path / "dashboard/index.html").read_bytes()
    bd.run(config, root=tmp_path)
    assert (tmp_path / "dashboard/index.html").read_bytes() == first


def test_run_without_analysis_fails(tmp_path, config):
    with pytest.raises(RuntimeError):
        bd.run(config, root=tmp_path)


def test_no_comparison_message(multi_day_history, config):
    a = az.analyze([multi_day_history[-1]], config, AT)
    assert "비교 데이터 없음" in bd.render(a, None, config["dashboard"])
