"""분석 결과로 정적 대시보드를 만든다.

실행: uv run python tools/build_dashboard.py
입력: data/analysis.json (필수), data/summary.json (AI 요약 "오늘의 결론", 없으면
      기존 dashboard/data.json에 들어 있던 마지막 요약을 그대로 쓴다)
출력: dashboard/index.html (데이터를 HTML에 직접 넣음 → 파일을 더블클릭해도 열림)
      dashboard/data.json  (같은 데이터)
스크립트·외부 폰트·라이브러리 없음. CSP로 스크립트 차단. 같은 입력이면 같은 출력.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

from common import KST, ROOT, fmt_kst, load_config, resolve, utf8_stdout, write_json_atomic

CSP = ("default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; "
       "base-uri 'none'; form-action 'none'")


def e(v: Any) -> str:
    return escape("" if v is None else str(v))


def pct(v: float | None) -> str:
    return "-" if v is None else f"{v:.2f}%"


def num(v: float | None) -> str:
    return "-" if v is None else f"{v:.2f}"


def musd(v: float | None) -> str:
    return "-" if v is None else f"${v / 1e6:,.1f}M"


def btc(v: float | None) -> str:
    return "-" if v is None else f"{v:.4f} BTC"


# ---------- 요약(오늘의 결론) ----------

def load_summary(path: Path, fallback_data: Path) -> dict | None:
    """data/summary.json → 없으면 기존 dashboard/data.json의 마지막 요약."""
    data = None
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict) and isinstance(data.get("lines"), list):
            if not data.get("generated_at_kst"):
                # 에이전트는 현재 시각을 모르므로 생성 시각은 파일 수정 시각으로 도구가 찍는다
                mtime = datetime.fromtimestamp(path.stat().st_mtime, KST)
                data["generated_at_kst"] = fmt_kst(mtime)
                path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return data
    if fallback_data.exists():
        try:
            old = json.loads(fallback_data.read_text(encoding="utf-8")).get("summary")
        except json.JSONDecodeError:
            old = None
        if isinstance(old, dict) and isinstance(old.get("lines"), list):
            return old
    return None


def summary_status(summary: dict | None, analysis: dict) -> str:
    """'ok' | 'stale' | 'missing'"""
    if not summary:
        return "missing"
    if summary.get("data_as_of_kst") != analysis["latest"]["collected_at_kst"]:
        return "stale"
    return "ok"


def conclusion_block(summary: dict | None, status: str, max_lines: int) -> str:
    if status == "missing":
        body = '<p class="muted">아직 없음. 텔레그램에서 "대시보드 갱신해줘"로 만든다.</p>'
        meta = ""
    else:
        items = "".join(f"<li>{e(x)}</li>" for x in summary["lines"][:max_lines])
        body = f'<ul class="concl">{items}</ul>'
        meta = (f'<p class="muted">AI 요약 · 생성 {e(summary.get("generated_at_kst"))} · '
                f'{e(summary.get("data_as_of_kst"))} 데이터 기준</p>')
        if status == "stale":
            meta += ('<p class="note">요약은 이전 데이터 기준이다. 위 숫자 카드와 아래 순위가 '
                     '최신 값.</p>')
    return f'<section class="card"><h2>오늘의 결론</h2>{body}{meta}</section>'


# ---------- KPI ----------

def kpi_cards(a: dict) -> str:
    k = a["kpi"]
    cards = []
    bt = k.get("base_top")
    if bt:
        cards.append(("실제 이자 1위", pct(bt["apy_base"]),
                      f'{bt["project"]} · {bt["chain"]} · {bt["symbol"]}'))
    else:
        cards.append(("실제 이자 1위", "-", "기본 APY가 있는 풀 없음"))
    lt = k.get("large_top")
    big = f'TVL {k["large_tvl_usd"] / 1e8:,.0f}억 달러 이상'
    if lt:
        cards.append(("대형 풀 1위", pct(lt["apy_base"]),
                      f'{lt["project"]} · {lt["symbol"]} · TVL {musd(lt["tvl_usd"])}'))
    else:
        cards.append(("대형 풀 1위", "-", f"{big} 풀 없음"))
    cards.append(("예치형 풀", f'{k["primary_count"]}개',
                  f'TVL 합계 {musd(k["primary_tvl_usd_sum"])}'))
    cards.append(("보상 의존 비중", pct(k["reward_share_pct"]),
                  f'APY 합계 중 보상 몫 · 보상 의존 풀 {k["reward_dependent_count"]}개'))
    html = "".join(
        f'<div class="kpi"><div class="kpi-label">{e(t)}</div>'
        f'<div class="kpi-value">{e(v)}</div><div class="kpi-desc">{e(d)}</div></div>'
        for t, v, d in cards
    )
    return f'<section class="kpis" aria-label="핵심 지표">{html}</section>'


# ---------- 순위 (데스크톱 표 / 모바일 카드) ----------

def bar(r: dict, scale: float) -> str:
    base = r.get("apy_base") or 0
    reward = r.get("apy_reward") or 0
    wb = min(base / scale * 100, 100) if scale else 0
    wr = min(reward / scale * 100, 100 - wb) if scale else 0
    return (f'<span class="bar" aria-hidden="true"><i class="b" style="width:{wb:.1f}%"></i>'
            f'<i class="r" style="width:{wr:.1f}%"></i></span>')


def badges(r: dict) -> str:
    items = r.get("badges") or []
    if not items:
        return '<span class="muted">-</span>'
    return "".join(f'<span class="badge {e(b["key"])}">{e(b["label"])}</span>' for b in items)


def pool_rows(rows: list[dict]) -> str:
    scale = max(((r.get("apy_base") or 0) + (r.get("apy_reward") or 0) for r in rows),
                default=0)
    head = (
        '<div class="row head" role="row"><span>#</span><span>풀</span>'
        '<span class="n">기본 APY</span><span class="n">보상</span><span class="n">합계</span>'
        '<span class="n">1 BTC 연 이자</span><span class="n">TVL</span><span>리스크</span>'
        "<span>원본</span></div>"
    )
    out = [head]
    for r in rows:
        sub = " · ".join(e(x) for x in (r["chain"], r["symbol"], r.get("note")) if x)
        out.append(
            '<div class="row pool" role="row">'
            f'<span class="rank">{r["rank"]}</span>'
            f'<span class="name"><b>{e(r["project"])}</b><small>{sub}</small></span>'
            f'<span class="n base"><span class="lbl">기본 APY</span>'
            f'<b class="big">{pct(r.get("apy_base"))}</b>{bar(r, scale)}</span>'
            f'<span class="n"><span class="lbl">보상</span>{pct(r.get("apy_reward"))}</span>'
            f'<span class="n"><span class="lbl">합계</span>{pct(r.get("apy"))}</span>'
            f'<span class="n"><span class="lbl">1 BTC 연 이자</span>{btc(r.get("btc_per_year"))}'
            "</span>"
            f'<span class="n"><span class="lbl">TVL</span>{musd(r["tvl_usd"])}</span>'
            f'<span class="badges">{badges(r)}</span>'
            f'<span class="src"><a href="{e(r["url"])}" target="_blank" rel="noopener">'
            "DefiLlama 원본</a></span>"
            "</div>"
        )
    return f'<div class="rank-list" role="table">{"".join(out)}</div>'


def legend() -> str:
    return (
        '<p class="legend"><span class="sw b"></span>기본 APY(실제 이자)'
        '<span class="sw r"></span>보상 APY · 막대 길이는 이 표의 최대 합계 대비</p>'
    )


# ---------- 전일 대비 / 통계 ----------

def change_block(a: dict) -> str:
    ch = a["change"]
    if ch["status"] != "ok":
        return f'<p class="muted">{e(ch["status"])}. 매일 08:00 자동 수집이 쌓이면 표시된다.</p>'
    rows = "".join(
        f'<tr><td>{e(c["project"])}<small>{e(c["chain"])} · {e(c["symbol"])}</small></td>'
        f'<td class="n">{pct(c["apy_prev"])}</td><td class="n">{pct(c["apy_now"])}</td>'
        f'<td class="n"><b>{c["delta_pp"]:+.2f}%p</b></td></tr>'
        for c in ch["items"]
    )
    n_new, n_drop = len(a["new_pools"]["items"]), len(a["dropped_pools"]["items"])
    return (
        f'<p class="muted">{e(a["previous"]["collected_at_kst"])} → '
        f'{e(a["latest"]["collected_at_kst"])} · 신규 {n_new} · 이탈 {n_drop}</p>'
        '<table class="simple"><thead><tr><th>풀</th><th class="n">이전</th>'
        f'<th class="n">현재</th><th class="n">변화</th></tr></thead><tbody>{rows}</tbody>'
        "</table>"
    )


STAT_ROWS = [
    ("풀 수", "count", lambda v: f"{v}개"),
    ("TVL 합계", "tvl_usd_sum", musd),
    ("APY 평균", "apy_mean", pct),
    ("APY 중앙값", "apy_median", pct),
    ("APY TVL 가중 평균", "apy_tvl_weighted", pct),
    ("기본 비중", "base_share_pct", pct),
    ("보상 비중", "reward_share_pct", pct),
    ("보상 의존 풀", "reward_dependent_count", lambda v: f"{v}개"),
]


def stats_table(stats: dict[str, dict]) -> str:
    types = list(stats)
    head = "".join(f'<th class="n">{e(t)}</th>' for t in types)
    body = "".join(
        f"<tr><td>{label}</td>"
        + "".join(f'<td class="n">{fmt(stats[t].get(key))}</td>' for t in types)
        + "</tr>"
        for label, key, fmt in STAT_ROWS
    )
    return (f'<table class="simple"><thead><tr><th></th>{head}</tr></thead>'
            f"<tbody>{body}</tbody></table>")


# ---------- 스타일 ----------

CSS = """
:root{--bg:#f7f7f5;--surface:#fff;--fg:#1a1a1a;--muted:#5f6368;--line:#e2e2de;
--base:#1f6f5c;--reward:#c08a2b;--track:#ecece8;--link:#1a5fb4;
--b-lockup-bg:#fde8e8;--b-lockup-fg:#8a1c1c;--b-points-bg:#fdf1dc;--b-points-fg:#7a4b00;
--b-cust-bg:#e6eefc;--b-cust-fg:#1d3f7a;--b-new-bg:#efe6fb;--b-new-fg:#4b2a7a;
--b-check-bg:#ececec;--b-check-fg:#3c3c3c}
@media (prefers-color-scheme:dark){:root{--bg:#111312;--surface:#1a1d1c;--fg:#e9eae8;
--muted:#a3a7a5;--line:#2e3331;--base:#5cc2a4;--reward:#e0b05a;--track:#2a2f2d;--link:#8ab4f8;
--b-lockup-bg:#4a1f1f;--b-lockup-fg:#ffc9c9;--b-points-bg:#44340f;--b-points-fg:#ffe1a6;
--b-cust-bg:#1d2d4d;--b-cust-fg:#c4d6ff;--b-new-bg:#33224d;--b-new-fg:#dccbff;
--b-check-bg:#333;--b-check-fg:#ddd}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,
"Segoe UI","Apple SD Gothic Neo","Malgun Gothic",sans-serif;font-variant-numeric:tabular-nums}
a{color:var(--link)}
header{position:sticky;top:0;z-index:2;background:var(--surface);
border-bottom:1px solid var(--line)}
.hwrap{max-width:1180px;margin:0 auto;padding:10px 16px}
header h1{font-size:17px;margin:0}
header .meta{font-size:13px;color:var(--muted)}
main{max-width:1180px;margin:0 auto;padding:16px 16px 40px}
h2{font-size:16px;margin:0 0 10px}
section{margin-bottom:24px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:14px 16px}
.muted{color:var(--muted);font-size:13px;margin:6px 0 0}
.note{font-size:13px;margin:6px 0 0;padding:6px 8px;border-left:3px solid var(--reward)}
.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:12px 14px;
min-width:0}
.kpi-label{font-size:13px;color:var(--muted)}
.kpi-value{font-size:28px;font-weight:700;line-height:1.2;margin:4px 0}
.kpi-desc{font-size:13px;overflow-wrap:anywhere}
ul.concl{margin:0;padding-left:20px}
ul.concl li{margin:4px 0}
.legend{font-size:13px;color:var(--muted);margin:0 0 8px}
.sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin:0 4px 0 10px;
vertical-align:-1px}
.sw:first-child{margin-left:0}
.sw.b,.bar .b{background:var(--base)}
.sw.r,.bar .r{background:var(--reward)}
.bar{display:flex;height:6px;background:var(--track);border-radius:3px;overflow:hidden;
margin-top:4px}
.bar i{display:block;height:100%}
.n{text-align:right}
small{display:block;font-size:12px;color:var(--muted);overflow-wrap:anywhere}
.badge{display:inline-block;font-size:12px;line-height:1.3;padding:2px 6px;border-radius:4px;
margin:0 4px 4px 0;white-space:nowrap}
.badge.lockup{background:var(--b-lockup-bg);color:var(--b-lockup-fg)}
.badge.points{background:var(--b-points-bg);color:var(--b-points-fg)}
.badge.custodial{background:var(--b-cust-bg);color:var(--b-cust-fg)}
.badge.newchain{background:var(--b-new-bg);color:var(--b-new-fg)}
.badge.check{background:var(--b-check-bg);color:var(--b-check-fg)}
.rank-list{background:var(--surface);border:1px solid var(--line);border-radius:8px}
.row{display:grid;grid-template-columns:32px minmax(150px,1.6fr) 130px 70px 70px 105px 90px
minmax(150px,1.4fr) 100px;gap:10px;align-items:start;padding:10px 12px;
border-bottom:1px solid var(--line)}
.row:last-child{border-bottom:0}
.row.head{font-size:12px;color:var(--muted);font-weight:600;align-items:end}
.row .lbl{display:none}
.rank{color:var(--muted)}
.name b{font-weight:600}
.base .big{font-size:16px}
.src{font-size:13px}
table.simple{width:100%;border-collapse:collapse;background:var(--surface);
border:1px solid var(--line);border-radius:8px;font-size:14px}
table.simple th,table.simple td{padding:7px 10px;border-bottom:1px solid var(--line);
text-align:left;vertical-align:top}
table.simple th{font-size:12px;color:var(--muted);font-weight:600}
table.simple .n{text-align:right}
details>summary{cursor:pointer;font-size:16px;font-weight:600;margin-bottom:10px}
footer{font-size:12px;color:var(--muted)}
@media (max-width:760px){
 .kpis{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
 .kpi{padding:10px 12px}
 .kpi-value{font-size:22px}
 .rank-list{background:none;border:0}
 .row.head{display:none}
 .row.pool{grid-template-columns:repeat(2,minmax(0,1fr));gap:6px 12px;
 background:var(--surface);border:1px solid var(--line);border-radius:8px;margin-bottom:10px;
 padding:12px}
 .row.pool .rank{grid-column:1 / -1;font-size:12px}
 .row.pool .rank::before{content:"순위 "}
 .row.pool .name{grid-column:1 / -1}
 .row.pool .base{grid-column:1 / -1;text-align:left}
 .row.pool .base .big{font-size:24px;display:block}
 .row.pool .n{text-align:left}
 .row .lbl{display:block;font-size:12px;color:var(--muted)}
 .row.pool .badges,.row.pool .src{grid-column:1 / -1}
}
"""


RISK_NOTE = ("리스크 기준: 락업은 풀 설명·대출 시장 여부, BTC 형태는 토큰별 발행 구조, "
             "신생 체인은 메인넷 출시 24개월 미만. 근거가 없으면 확인 필요")


def render(analysis: dict, summary: dict | None, cfg: dict) -> str:
    a = analysis
    status = summary_status(summary, a)
    sec = a["secondary"]
    latest = a["latest"]["collected_at_kst"]
    rows = a.get("ranking") or a["top"]
    lp = (
        f'<section><details><summary>{e(sec["type"])} {sec["count"]}개 '
        "(토큰 2개 이상 유동성 공급, 순위 제외)</summary>"
        f"{legend()}{pool_rows(sec['top'])}</details></section>"
        if sec["count"] else ""
    )
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<meta name="color-scheme" content="light dark">
<title>{e(cfg["title"])}</title><style>{CSS}</style></head>
<body>
<header><div class="hwrap"><h1>{e(cfg["title"])}</h1>
<div class="meta">데이터 기준 {e(latest)} · 출처 <a href="https://defillama.com/yields"
target="_blank" rel="noopener">{e(a["source"])}</a></div></div></header>
<main>
{kpi_cards(a)}
{conclusion_block(summary, status, cfg["summary_max_lines"])}
<section><h2>{e(a["primary_type"])} 순위 · 실제 이자(기본 APY) 높은 순</h2>
{legend()}{pool_rows(rows)}</section>
<section><h2>전일 대비</h2>{change_block(a)}</section>
{lp}
<section><h2>유형별 통계</h2>{stats_table(a["stats"])}</section>
<footer>분석 {e(a.get("generated_at_kst"))} · {RISK_NOTE}</footer>
</main></body></html>
"""


def run(config: dict | None = None, root: Path = ROOT) -> dict:
    """입력이 같으면 출력도 같다(빌드 시각을 넣지 않음) → 변경 없으면 게시도 없음."""
    config = config or load_config()
    paths = config["paths"]
    analysis_path = resolve(paths["analysis"], root)
    if not analysis_path.exists():
        raise RuntimeError("analysis.json 없음. 먼저: uv run python tools/analyze_yields.py")
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    data_path = resolve(paths["dashboard_data"], root)
    summary = load_summary(resolve(paths["summary"], root), data_path)
    html = render(analysis, summary, config["dashboard"])
    out = resolve(paths["dashboard_html"], root)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(html, encoding="utf-8")
    tmp.replace(out)
    write_json_atomic(data_path, {"analysis": analysis, "summary": summary})
    return {"latest": analysis["latest"]["collected_at_kst"],
            "summary": summary_status(summary, analysis), "path": str(out)}


def main() -> int:
    utf8_stdout()
    try:
        r = run()
    except Exception as ex:
        print(f"대시보드 생성 실패: {ex}", file=sys.stderr)
        return 1
    label = {"ok": "최신", "stale": "이전 데이터 기준(유지)", "missing": "없음"}[r["summary"]]
    print(f"대시보드 갱신 → dashboard/index.html (데이터 기준 {r['latest']}, 요약 {label})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
