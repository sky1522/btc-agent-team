"""분석 결과로 정적 대시보드를 만든다.

실행: uv run python tools/build_dashboard.py
입력: data/analysis.json (필수), data/summary.json (reporter가 쓰는 AI 요약, 없어도 됨)
출력: dashboard/index.html (데이터를 HTML에 직접 넣음 → 파일을 더블클릭해도 열림)
      dashboard/data.json  (같은 데이터, 나중 배포·연동용)
외부 라이브러리 없음.
"""

from __future__ import annotations

import json
import sys
from html import escape
from pathlib import Path
from typing import Any

from common import ROOT, load_config, resolve, utf8_stdout, write_json_atomic


def pct(v: float | None) -> str:
    return "-" if v is None else f"{v:.2f}"


def musd(v: float | None) -> str:
    return "-" if v is None else f"{v / 1e6:,.1f}"


def e(v: Any) -> str:
    return escape("" if v is None else str(v))


def load_summary(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) and isinstance(data.get("lines"), list) else None


def summary_status(summary: dict | None, analysis: dict) -> str:
    """'ok' | 'stale' | 'missing'"""
    if not summary:
        return "missing"
    if summary.get("data_as_of_kst") != analysis["latest"]["collected_at_kst"]:
        return "stale"
    return "ok"


def pool_cell(r: dict) -> str:
    sub = [e(r["chain"])]
    if r.get("note"):
        sub.append(e(r["note"]))
    sub += [f'<b class="flag">{e(f)}</b>' for f in r.get("flags", [])]
    return f'{e(r["project"])}<div class="sub">{" · ".join(sub)}</div>'


def ranking_table(rows: list[dict]) -> str:
    body = "".join(
        f'<tr><td class="n">{r["rank"]}</td><td>{pool_cell(r)}</td>'
        f'<td><a href="{e(r["url"])}" target="_blank" rel="noopener">{e(r["symbol"])}</a></td>'
        f'<td class="n">{pct(r["apy_base"])}</td><td class="n">{pct(r["apy_reward"])}</td>'
        f'<td class="n b">{pct(r["apy"])}</td><td class="n">{musd(r["tvl_usd"])}</td></tr>'
        for r in rows
    )
    return (
        '<div class="scroll"><table><thead><tr><th>#</th><th>프로토콜</th><th>심볼</th>'
        '<th class="n">기본</th><th class="n">보상</th><th class="n">합계</th>'
        f'<th class="n">TVL $M</th></tr></thead><tbody>{body}</tbody></table></div>'
    )


def base_table(rows: list[dict]) -> str:
    body = "".join(
        f'<tr><td class="n">{r["rank"]}</td><td>{pool_cell(r)}</td>'
        f'<td><a href="{e(r["url"])}" target="_blank" rel="noopener">{e(r["symbol"])}</a></td>'
        f'<td class="n b">{pct(r["apy_base"])}</td><td class="n">{pct(r["apy"])}</td>'
        f'<td class="n">{musd(r["tvl_usd"])}</td></tr>'
        for r in rows
    )
    return (
        '<div class="scroll"><table><thead><tr><th>#</th><th>프로토콜</th><th>심볼</th>'
        '<th class="n">기본</th><th class="n">합계</th><th class="n">TVL $M</th></tr></thead>'
        f"<tbody>{body}</tbody></table></div>"
    )


STAT_ROWS = [
    ("풀 수", "count", lambda v: f"{v}"),
    ("TVL 합계 $M", "tvl_usd_sum", musd),
    ("APY 평균", "apy_mean", pct),
    ("APY 중앙값", "apy_median", pct),
    ("APY TVL가중", "apy_tvl_weighted", pct),
    ("기본 비중 %", "base_share_pct", pct),
    ("보상 비중 %", "reward_share_pct", pct),
    ("보상 의존 풀", "reward_dependent_count", lambda v: f"{v}"),
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
    return f"<table><thead><tr><th></th>{head}</tr></thead><tbody>{body}</tbody></table>"


def change_block(a: dict) -> str:
    ch = a["change"]
    if ch["status"] != "ok":
        return f'<p class="muted">전일 대비: {e(ch["status"])}</p>'
    prev = a["previous"]["collected_at_kst"]
    rows = "".join(
        f'<tr><td>{e(c["project"])}<div class="sub">{e(c["chain"])} · {e(c["symbol"])}</div></td>'
        f'<td class="n">{pct(c["apy_prev"])}</td><td class="n">{pct(c["apy_now"])}</td>'
        f'<td class="n b">{c["delta_pp"]:+.2f}</td></tr>'
        for c in ch["items"]
    )
    n_new, n_drop = len(a["new_pools"]["items"]), len(a["dropped_pools"]["items"])
    return (
        f'<p class="muted">비교: {e(prev)} → {e(a["latest"]["collected_at_kst"])} · '
        f"신규 {n_new} · 이탈 {n_drop}</p>"
        '<div class="scroll"><table><thead><tr><th>풀</th><th class="n">이전</th>'
        f'<th class="n">현재</th><th class="n">%p</th></tr></thead><tbody>{rows}</tbody>'
        "</table></div>"
    )


def summary_block(summary: dict | None, status: str, max_lines: int) -> str:
    if status == "missing":
        return '<p class="muted">요약 없음. 텔레그램에서 "대시보드 갱신해줘"로 생성.</p>'
    items = "".join(f"<li>{e(x)}</li>" for x in summary["lines"][:max_lines])
    meta = f'작성 {e(summary.get("written_at_kst"))} · 데이터 {e(summary.get("data_as_of_kst"))}'
    warn = (
        '<p class="warn">요약이 최신 데이터보다 오래됨. 아래 표 수치가 우선.</p>'
        if status == "stale" else ""
    )
    return f'{warn}<ul class="sum">{items}</ul><p class="muted">{meta}</p>'


CSS = """
:root{--bg:#fff;--fg:#111;--muted:#666;--line:#e3e3e3;--head:#f6f6f6;--accent:#0b57d0;
--warn-bg:#fff4d6;--warn-fg:#6b4e00;--flag:#9a3412}
@media (prefers-color-scheme:dark){:root{--bg:#121212;--fg:#e8e8e8;--muted:#9a9a9a;
--line:#2c2c2c;--head:#1c1c1c;--accent:#8ab4f8;--warn-bg:#3a2f0b;--warn-fg:#f3d27a;--flag:#fdba74}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,-apple-system,
"Segoe UI","Apple SD Gothic Neo","Malgun Gothic",sans-serif}
header{position:sticky;top:0;z-index:1;background:var(--bg);border-bottom:1px solid var(--line);
padding:8px 12px}
header h1{font-size:16px;margin:0}
header .meta{font-size:12px;color:var(--muted)}
main{max-width:760px;margin:0 auto;padding:4px 12px 24px}
h2{font-size:14px;margin:18px 0 6px}
h2 small{font-weight:normal;color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:5px 6px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{background:var(--head);font-weight:600;white-space:nowrap}
.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.b{font-weight:600}
.sub{font-size:11px;color:var(--muted)}
.flag{color:var(--flag);font-weight:600;white-space:nowrap}
.scroll{overflow-x:auto}
.muted{color:var(--muted);font-size:12px;margin:4px 0}
.warn{background:var(--warn-bg);color:var(--warn-fg);padding:6px 8px;font-size:12px;margin:4px 0}
ul.sum{margin:4px 0;padding-left:18px}
a{color:var(--accent);text-decoration:none}
details{margin-top:6px}
summary{cursor:pointer;font-size:13px}
footer{font-size:11px;color:var(--muted);margin-top:20px}
"""


# 스크립트·외부 리소스 전부 차단. 인라인 스타일만 허용
CSP = ("default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; "
       "base-uri 'none'; form-action 'none'")


def render(analysis: dict, summary: dict | None, cfg: dict) -> str:
    a = analysis
    status = summary_status(summary, a)
    primary = a["primary_type"]
    sec = a["secondary"]
    latest = a["latest"]["collected_at_kst"]
    source_url = "https://defillama.com/yields"
    lp = (
        f"<details><summary>{e(sec['type'])} {sec['count']}개 (순위 제외, 참고)</summary>"
        f"{ranking_table(sec['top'])}</details>"
        if sec["count"] else ""
    )
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<title>{e(cfg["title"])}</title><style>{CSS}</style></head>
<body>
<header><h1>{e(cfg["title"])}</h1>
<div class="meta">기준 {e(latest)} · 출처 <a href="{source_url}" target="_blank"
rel="noopener">{e(a["source"])}</a></div></header>
<main>
<h2>요약</h2>
{summary_block(summary, status, cfg["summary_max_lines"])}
<h2>{e(primary)} 순위 <small>APY %, 기본/보상 구분</small></h2>
{ranking_table(a.get("ranking") or a["top"])}
<h2>기본 APY 상위 {len(a["top_by_base"])} <small>보상 제외 실제 이자</small></h2>
{base_table(a["top_by_base"])}
<h2>유형별 통계</h2>
{stats_table(a["stats"])}
<h2>전일 대비</h2>
{change_block(a)}
{lp}
<footer>참고 자료이며 투자 권유가 아님. 수치는 원본 링크로 확인.<br>
분석 {e(a.get("generated_at_kst"))}</footer>
</main></body></html>
"""


def run(config: dict | None = None, root: Path = ROOT) -> dict:
    """입력이 같으면 출력도 같다(생성 시각을 넣지 않음) → 변경 없으면 게시도 없음."""
    config = config or load_config()
    paths = config["paths"]
    analysis_path = resolve(paths["analysis"], root)
    if not analysis_path.exists():
        raise RuntimeError("analysis.json 없음. 먼저: uv run python tools/analyze_yields.py")
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    summary = load_summary(resolve(paths["summary"], root))
    html = render(analysis, summary, config["dashboard"])
    out = resolve(paths["dashboard_html"], root)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(html, encoding="utf-8")
    tmp.replace(out)
    write_json_atomic(resolve(paths["dashboard_data"], root),
                      {"analysis": analysis, "summary": summary})
    return {"latest": analysis["latest"]["collected_at_kst"],
            "summary": summary_status(summary, analysis), "path": str(out)}


def main() -> int:
    utf8_stdout()
    try:
        r = run()
    except Exception as ex:
        print(f"대시보드 생성 실패: {ex}", file=sys.stderr)
        return 1
    label = {"ok": "최신", "stale": "오래됨(데이터보다 이전)", "missing": "없음"}[r["summary"]]
    print(f"대시보드 갱신 → dashboard/index.html (데이터 기준 {r['latest']}, 요약 {label})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
