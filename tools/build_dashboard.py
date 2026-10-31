"""분석 결과로 정적 대시보드를 만든다.

실행: uv run python tools/build_dashboard.py
입력: data/analysis.json (필수), data/summary.json (AI 요약 "오늘의 결론", 없으면
      기존 dashboard/data.json에 들어 있던 마지막 요약을 그대로 쓴다)
출력: dashboard/index.html (데이터·그래프를 HTML에 직접 넣음 → 파일을 더블클릭해도 열림)
      dashboard/data.json  (같은 데이터)
그래프는 이 파일이 인라인 SVG로 그린다. 스크립트·외부 폰트·라이브러리 없음(CSP로 차단).
같은 입력이면 같은 출력.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

from common import KST, ROOT, fmt_kst, load_config, resolve, utf8_stdout, write_json_atomic

CSP = ("default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; "
       "base-uri 'none'; form-action 'none'")
GRADE_KEY = {"낮음": "low", "보통": "mid", "높음": "high"}
GRADES = ("낮음", "보통", "높음")


def e(v: Any) -> str:
    return escape("" if v is None else str(v))


def pct(v: float | None) -> str:
    return "-" if v is None else f"{v:.2f}%"


def musd(v: float | None) -> str:
    return "-" if v is None else f"${v / 1e6:,.1f}M"


def btc(v: float | None) -> str:
    return "-" if v is None else f"{v:.4f} BTC"


def krw(v: float | None) -> str:
    if v is None:
        return ""
    man = round(v / 1e4)
    if man >= 10000:
        eok, rest = divmod(man, 10000)
        return f"약 {eok}억 {rest:,}만 원" if rest else f"약 {eok}억 원"
    return f"약 {man:,}만 원"


def short_time(kst: str) -> str:
    """'2026-10-31 16:16 KST' → '10월 31일 16:16'"""
    try:
        d, t, _ = kst.split(" ")
        _, m, dd = d.split("-")
        return f"{int(m)}월 {int(dd)}일 {t}"
    except ValueError:
        return kst


# ---------- 요약(오늘의 결론) ----------

def load_summary(path: Path, fallback_data: Path) -> dict | None:
    """data/summary.json → 없으면 기존 dashboard/data.json의 마지막 요약."""
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
        return ('<section class="concl reveal" aria-labelledby="h-concl">'
                '<h2 id="h-concl">오늘의 결론</h2>'
                '<p class="muted">아직 없습니다. 텔레그램에서 "대시보드 갱신해줘"를 보내면 '
                "만들어집니다.</p></section>")
    text = " ".join(e(x) for x in summary["lines"][:max_lines])
    meta = (f'AI 요약, {e(summary.get("generated_at_kst"))} 작성 '
            f'({e(summary.get("data_as_of_kst"))} 데이터 기준)')
    note = ""
    if status == "stale":
        note = ('<p class="note">요약은 이전 데이터 기준입니다. 숫자는 위 카드와 아래 표가 '
                "최신입니다.</p>")
    return (f'<section class="concl reveal" aria-labelledby="h-concl">'
            f'<h2 id="h-concl">오늘의 결론</h2><p class="concl-text">{text}</p>'
            f'{note}<p class="muted">{meta}</p></section>')


# ---------- 작은 부품 ----------

def shape(k: str, x: float, y: float, r: float) -> str:
    """위험 등급별 모양: 낮음 원, 보통 네모, 높음 세모 (색만으로 구분하지 않음)."""
    if k == "low":
        return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" class="m-low"/>'
    if k == "mid":
        s = r * 1.7
        return (f'<rect x="{x - s / 2:.1f}" y="{y - s / 2:.1f}" width="{s:.1f}" '
                f'height="{s:.1f}" class="m-mid"/>')
    h = r * 2.1
    return (f'<polygon points="{x:.1f},{y - h / 2 - 0.6:.1f} {x - h / 1.9:.1f},{y + h / 2:.1f} '
            f'{x + h / 1.9:.1f},{y + h / 2:.1f}" class="m-high"/>')


def grade_pill(g: str | None) -> str:
    if not g:
        return ""
    k = GRADE_KEY[g]
    return (f'<span class="grade g-{k}"><svg class="gicon" viewBox="0 0 10 10" '
            f'aria-hidden="true">{shape(k, 5, 5, 4)}</svg>위험 {e(g)}</span>')


def sparkline(values: list[float], w: int = 112, h: int = 36) -> str:
    if len(values) < 2:
        return '<span class="spark-none">추이 없음</span>'
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    pad = 3
    pts = [(pad + i * (w - 2 * pad) / (len(values) - 1),
            h - pad - (v - lo) / span * (h - 2 * pad)) for i, v in enumerate(values)]
    d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    lx, ly = pts[-1]
    label = f"최근 {len(values)}일 기본 APY 추이, 최저 {lo:.2f}%, 최고 {hi:.2f}%"
    return (f'<svg class="spark" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
            f'aria-label="{e(label)}"><title>{e(label)}</title>'
            f'<path d="{d}" pathLength="1" class="spark-line"/>'
            f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="2.6" class="spark-end"/></svg>')


def delta(v: float | None) -> str:
    if v is None:
        return '<span class="muted">-</span>'
    if abs(v) < 0.005:
        return '<span class="d-flat">변화 없음</span>'
    cls, arrow = ("d-up", "↑") if v > 0 else ("d-down", "↓")
    return f'<span class="{cls}">{arrow} {abs(v):.2f}%p</span>'


def side_notes(r: dict) -> str:
    """위험 등급 외 배지는 작은 글씨로만."""
    items = [b["label"] for b in r.get("badges") or []]
    lk = (r.get("risk") or {}).get("lockup")
    if lk and lk.startswith("출금 대기"):
        items.insert(0, lk)
    return f'<p class="small muted">{e(", ".join(items))}</p>' if items else ""


def src_link(r: dict) -> str:
    return (f'<a class="src" href="{e(r["url"])}" target="_blank" rel="noopener">'
            "DefiLlama에서 원본 보기</a>")


# ---------- 추천 카드 ----------

def stable_cond(rec: dict) -> str:
    t = rec.get("stable_tvl_min")
    if not t:
        return rec.get("stable_note") or "조건에 맞는 풀 없음"
    base = f"위험 낮음·보통 중 TVL {t / 1e8:g}억 달러 이상 1위" if t >= 1e8 else (
        f"위험 낮음·보통 중 TVL {t / 1e7:g}천만 달러 이상 1위")
    return f"{base} ({rec['stable_note']})" if rec.get("stable_note") else base


def rec_card(kind: str, title: str, cond: str, r: dict | None) -> str:
    if not r:
        return (f'<article class="rec reveal"><p class="rec-kind">{e(title)}</p>'
                f'<p class="big-none">조건에 맞는 풀 없음</p>'
                f'<p class="small muted">{e(cond)}.</p></article>')
    form_full = (r.get("risk") or {}).get("btc_form") or "-"
    form = form_full.split(" (")[0]
    money = btc(r.get("btc_per_year"))
    if r.get("krw_per_year") is not None:
        money += f", {krw(r['krw_per_year'])}"
    avg = f", 30일 평균 {pct(r['base_30d_avg'])}" if r.get("base_30d_avg") is not None else ""
    return f"""<article class="rec rec-{kind} reveal" aria-label="{e(title)} 추천">
<div class="rec-top"><p class="rec-kind">{e(title)}</p>{grade_pill(r.get("grade"))}</div>
<p class="rec-name"><b>{e(r["project"])}</b>
<span title="{e(form_full)}">{e(r["chain"])}, {e(form)}</span></p>
<div class="rec-num"><p><span class="big">{pct(r.get("apy_base"))}</span>
<span class="lbl muted">기본 APY{avg}</span></p>{sparkline(r.get("spark") or [], 96, 34)}</div>
<p class="rec-money">1 BTC 맡기면 1년에 {e(money)}</p>
<p class="small">{e(cond)}. {e(r.get("grade_reason"))}.</p>
{src_link(r)}
</article>"""


# ---------- 그래프 ----------

def scatter_chart(rows: list[dict], rec: dict, large_tvl: float) -> tuple[str, str]:
    """이자 vs 규모 지도: 가로 TVL(로그), 세로 기본 APY, 모양·색 = 위험 등급."""
    pts = [r for r in rows if r.get("apy_base") is not None and r["tvl_usd"] > 0]
    if not pts:
        return "", ""
    W, H, L, R, T, B = 400, 270, 44, 14, 18, 44
    xs = [math.log10(r["tvl_usd"]) for r in pts]
    x0, x1 = math.floor(min(xs) * 4) / 4 - 0.05, math.ceil(max(xs) * 4) / 4 + 0.05
    ymax = max(1.0, math.ceil(max(r["apy_base"] for r in pts) + 0.4))

    def px(t: float) -> float:
        return L + (math.log10(t) - x0) / (x1 - x0) * (W - L - R)

    def py(a: float) -> float:
        return T + (1 - a / ymax) * (H - T - B)

    g = []
    step = 1 if ymax <= 6 else 2
    for a in range(0, int(ymax) + 1, step):
        y = py(a)
        g.append(f'<line x1="{L}" x2="{W - R}" y1="{y:.1f}" y2="{y:.1f}" class="grid"/>'
                 f'<text x="{L - 6}" y="{y + 4:.1f}" class="tick" text-anchor="end">{a}%</text>')
    for t, lab in ((5e6, "$5M"), (1e7, "$10M"), (3e7, "$30M"), (1e8, "$100M"), (3e8, "$300M"),
                   (1e9, "$1B")):
        if x0 <= math.log10(t) <= x1:
            g.append(f'<text x="{px(t):.1f}" y="{H - B + 16}" class="tick" '
                     f'text-anchor="middle">{lab}</text>')
    if x0 <= math.log10(large_tvl) <= x1:
        x = px(large_tvl)
        g.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{T}" y2="{H - B}" class="ref"/>'
                 f'<text x="{x + 4:.1f}" y="{T - 4}" class="tick">대형 풀 기준</text>')
    g.append(f'<line x1="{L}" x2="{W - R}" y1="{H - B}" y2="{H - B}" class="axis"/>')
    g.append(f'<text x="{(L + W - R) / 2:.1f}" y="{H - 8}" class="axis-title" '
             'text-anchor="middle">예치 규모 TVL (로그 눈금, 달러)</text>')
    g.append(f'<text transform="translate(12 {(T + H - B) / 2:.1f}) rotate(-90)" '
             'class="axis-title" text-anchor="middle">기본 APY</text>')
    marks, labels = [], []
    rec_ids = {(rec.get(k) or {}).get("pool"): name
               for k, name in (("stable", "안정 우선"), ("yield", "이자 우선"))}
    for r in sorted(pts, key=lambda r: r["tvl_usd"]):
        x, y = px(r["tvl_usd"]), py(r["apy_base"])
        k = GRADE_KEY.get(r.get("grade") or "보통", "mid")
        tip = (f'{r["project"]} {r["symbol"]} ({r["chain"]}): 기본 {r["apy_base"]:.2f}%, '
               f'TVL {musd(r["tvl_usd"])}, 위험 {r.get("grade") or "-"}')
        marks.append(f'<g class="pt"><title>{e(tip)}</title>{shape(k, x, y, 5)}</g>')
        if r["pool"] in rec_ids:
            labels.append((x, y, f'{rec_ids[r["pool"]]}: {r["project"]}'))
    used: list[float] = []
    for x, y, text in sorted(labels, key=lambda t: t[1]):
        ly = y - 10
        while any(abs(ly - u) < 13 for u in used):
            ly += 13
        used.append(ly)
        right = x < W * 0.55
        tx, anchor = (x + 8, "start") if right else (x - 8, "end")
        marks.append(f'<text x="{tx:.1f}" y="{ly:.1f}" class="pt-label" '
                     f'text-anchor="{anchor}">{e(text)}</text>')
    big = [r["apy_base"] for r in pts if r["tvl_usd"] >= large_tvl]
    small = [r["apy_base"] for r in pts if r["tvl_usd"] < large_tvl]
    if big and small:
        note = (f"TVL 1억 달러가 넘는 큰 풀의 실제 이자는 최고 {max(big):.2f}%, "
                f"그보다 작은 풀은 최고 {max(small):.2f}%입니다. 큰 풀일수록 이자가 낮습니다.")
    else:
        note = "점 하나가 풀 하나입니다. 오른쪽일수록 규모가 크고, 위쪽일수록 실제 이자가 높습니다."
    svg = (f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" '
           f'aria-label="TVL과 기본 APY 산점도"><title>이자 vs 규모 지도</title>'
           f'{"".join(g)}{"".join(marks)}</svg>')
    return svg, note


def bar_chart(rows: list[dict]) -> tuple[str, str]:
    """실제 이자와 보상: APY 합계 상위 10개, 한 막대 안 기본·보상 두 구간."""
    rows = [r for r in rows if r.get("apy")][:10]
    if not rows:
        return "", ""
    W, LBL, VAL, ROW, T = 400, 136, 50, 24, 4
    H = T + ROW * len(rows) + 4
    vmax = max((r.get("apy_base") or 0) + (r.get("apy_reward") or 0) for r in rows) or 1
    span = W - LBL - VAL
    out = ['<defs><pattern id="hatch" width="5" height="5" patternUnits="userSpaceOnUse" '
           'patternTransform="rotate(45)"><rect width="5" height="5" class="seg-r"/>'
           '<line x1="0" y1="0" x2="0" y2="5" class="hatch-line"/></pattern></defs>']
    for i, r in enumerate(rows):
        y = T + i * ROW
        b, w = r.get("apy_base") or 0, r.get("apy_reward") or 0
        wb, ww = b / vmax * span, w / vmax * span
        name = f'{r["project"]} {r["symbol"]}'
        tip = f'{name}: 기본 {b:.2f}% + 보상 {w:.2f}% = {r["apy"]:.2f}%'
        seg = []
        if wb > 0.5:
            seg.append(f'<rect x="{LBL}" y="{y + 5}" width="{wb:.1f}" height="13" rx="2" '
                       'class="seg-b bar-seg"/>')
        if ww > 0.5:
            gap = 2 if wb > 0.5 else 0
            seg.append(f'<rect x="{LBL + wb + gap:.1f}" y="{y + 5}" '
                       f'width="{max(ww - gap, 1):.1f}" height="13" rx="2" fill="url(#hatch)" '
                       'class="bar-seg"/>')
        label = name if len(name) <= 22 else name[:21] + "…"
        out.append(
            f'<g><title>{e(tip)}</title>'
            f'<text x="{LBL - 6}" y="{y + 15}" class="tick" text-anchor="end">{e(label)}</text>'
            f'{"".join(seg)}<text x="{LBL + wb + ww + 5:.1f}" y="{y + 15}" class="val">'
            f'{r["apy"]:.2f}%</text></g>')
    top = rows[0]
    share = (top.get("apy_reward") or 0) / top["apy"] * 100 if top["apy"] else 0
    note = (f"합계 1위 {top['project']} {top['apy']:.2f}% 중 {share:.0f}%가 보상입니다. "
            "빗금 친 보상 구간은 보상이 끝나면 사라집니다.")
    svg = (f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" '
           f'aria-label="APY 합계 상위 10개 풀의 기본과 보상 구성"><title>실제 이자와 보상</title>'
           f'{"".join(out)}</svg>')
    return svg, note


# ---------- 상위 카드 · 나머지 목록 ----------

def top_card(r: dict) -> str:
    return f"""<article class="pool reveal">
<div class="pool-top"><p><span class="rank">{r["rank"]}</span><b>{e(r["project"])}</b>
<span class="muted"> {e(r["chain"])}, {e(r["symbol"])}</span></p>{grade_pill(r.get("grade"))}</div>
<div class="pool-num"><p><span class="mid-num">{pct(r.get("apy_base"))}</span>
<span class="small muted">기본 APY</span></p>{sparkline(r.get("spark") or [])}</div>
<dl class="facts">
<div><dt>30일 평균</dt><dd>{pct(r.get("base_30d_avg"))}</dd></div>
<div><dt>7일 변화</dt><dd>{delta(r.get("base_7d_change"))}</dd></div>
<div><dt>보상 APY</dt><dd>{pct(r.get("apy_reward"))}</dd></div>
<div><dt>TVL</dt><dd>{musd(r["tvl_usd"])}</dd></div>
</dl>
<p class="small">{e(r.get("grade_reason"))}</p>
{side_notes(r)}
{src_link(r)}
</article>"""


def rest_table(rows: list[dict]) -> str:
    body = "".join(
        f'<tr><td class="n">{r["rank"]}</td>'
        f'<td><b>{e(r["project"])}</b><span class="small muted"> {e(r["chain"])}, '
        f'{e(r["symbol"])}{", " + e(r["note"]) if r.get("note") else ""}</span></td>'
        f'<td class="n">{pct(r.get("apy_base"))}</td><td class="n">{pct(r.get("apy_reward"))}</td>'
        f'<td class="n">{musd(r["tvl_usd"])}</td><td>{grade_pill(r.get("grade"))}</td>'
        f'<td><a href="{e(r["url"])}" target="_blank" rel="noopener">원본</a></td></tr>'
        for r in rows
    )
    return ('<div class="table-wrap"><table class="list"><thead><tr><th class="n">순위</th>'
            '<th>풀</th><th class="n">기본</th><th class="n">보상</th><th class="n">TVL</th>'
            f"<th>위험</th><th>원본</th></tr></thead><tbody>{body}</tbody></table></div>")


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
    return (f'<div class="table-wrap"><table class="list"><thead><tr><th></th>{head}</tr>'
            f"</thead><tbody>{body}</tbody></table></div>")


def change_block(a: dict) -> str:
    ch = a["change"]
    if ch["status"] != "ok":
        return (f'<p class="muted small">전일 대비: {e(ch["status"])}. 매일 08:00 자동 수집이 '
                "쌓이면 표시됩니다.</p>")
    items = ", ".join(f'{e(c["project"])} {e(c["symbol"])} {c["delta_pp"]:+.2f}%p'
                      for c in ch["items"][:5])
    return (f'<p class="muted small">전일 대비({e(a["previous"]["collected_at_kst"])}부터): '
            f"{items}</p>")


# ---------- 스타일 ----------

LIGHT = ("--bg:#f3f4f6;--surface:#ffffff;--ink:#15171c;--ink-2:#4a505c;--line:#dcdfe5;"
         "--base:#2a78d6;--reward:#eb6834;--hatch:rgba(255,255,255,.55);--grid:#e6e8ec;"
         "--axis:#b9bec8;--low:#0ca30c;--mid:#fab219;--high:#d03b3b;--up:#006300;"
         "--down:#b42323;--link:#1d5fb8;color-scheme:light;")
DARK = ("--bg:#121417;--surface:#1b1e23;--ink:#eef0f3;--ink-2:#aeb4bf;--line:#2c3139;"
        "--base:#3987e5;--reward:#d95926;--hatch:rgba(0,0,0,.35);--grid:#262a31;"
        "--axis:#3d434d;--low:#0ca30c;--mid:#fab219;--high:#e05252;--up:#3bc43b;"
        "--down:#ff8a8a;--link:#8ab4f8;color-scheme:dark;")

CSS = (
    ":root{" + LIGHT + "}"
    "@media (prefers-color-scheme:dark){:root{" + DARK + "}"
    ":root:has(#theme:checked){" + LIGHT + "}}"
    "@media (prefers-color-scheme:light){:root:has(#theme:checked){" + DARK + "}}"
    + """
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,
"Segoe UI","Apple SD Gothic Neo","Malgun Gothic",sans-serif;font-variant-numeric:tabular-nums}
a{color:var(--link)}
p{margin:0}
h2{font-size:17px;margin:0 0 10px;letter-spacing:-.01em}
h3{font-size:15px;margin:0 0 6px}
.small{font-size:13px}
.muted{color:var(--ink-2)}
#theme{position:absolute;opacity:0;width:1px;height:1px}
header{position:sticky;top:0;z-index:3;background:var(--bg);border-bottom:1px solid var(--line)}
.hwrap{max-width:1120px;margin:0 auto;padding:10px 16px;display:flex;gap:12px;
align-items:center;justify-content:space-between}
header h1{font-size:18px;margin:0;letter-spacing:-.02em}
header .meta{font-size:12px;color:var(--ink-2)}
.toggle{flex:none;font-size:13px;border:1px solid var(--line);border-radius:999px;
padding:5px 11px;cursor:pointer;background:var(--surface);color:var(--ink)}
#theme:focus-visible~header .toggle{outline:2px solid var(--link);outline-offset:2px}
main{max-width:1120px;margin:0 auto;padding:14px 16px 48px}
section{margin-bottom:28px}
.recs{display:grid;gap:12px;margin-bottom:18px}
.rec{background:var(--surface);border:1px solid var(--line);border-radius:14px;
padding:14px 16px;display:flex;flex-direction:column;gap:5px;min-width:0}
.rec-top,.pool-top{display:flex;justify-content:space-between;align-items:center;gap:8px}
.rec-kind{font-size:14px;font-weight:700}
.rec-name{font-size:16px}
.rec-name span{color:var(--ink-2);font-size:13px;white-space:nowrap}
.rec-num,.pool-num{display:flex;justify-content:space-between;align-items:flex-end;gap:10px}
.rec-num p,.pool-num p{display:flex;flex-direction:column}
.big{font-size:42px;line-height:1;font-weight:750;letter-spacing:-.03em}
.lbl{font-size:12px;margin-top:3px}
.big-none{font-size:22px;font-weight:700;margin:6px 0}
.mid-num{font-size:28px;line-height:1.1;font-weight:700;letter-spacing:-.02em}
.rec-money{font-size:15px;font-weight:600}
.src{font-size:13px}
.grade{display:inline-flex;align-items:center;gap:5px;font-size:13px;font-weight:600;
white-space:nowrap;border:1px solid var(--line);border-radius:999px;padding:2px 9px 2px 7px}
.gicon{width:10px;height:10px}
.g-low{border-color:var(--low)}.g-mid{border-color:var(--mid)}.g-high{border-color:var(--high)}
.m-low{fill:var(--low)}.m-mid{fill:var(--mid)}.m-high{fill:var(--high)}
.concl-text{font-size:20px;line-height:1.5;font-weight:500;max-width:36em;letter-spacing:-.01em}
.concl .muted{font-size:12px;margin-top:6px}
.note{font-size:13px;margin-top:6px;padding-left:8px;border-left:3px solid var(--mid)}
.price{margin:-16px 0 28px}
.charts{display:grid;gap:14px}
figure{margin:0;background:var(--surface);border:1px solid var(--line);border-radius:12px;
padding:14px;min-width:0}
figcaption p{font-size:14px;margin-top:8px}
.legend{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12px;color:var(--ink-2);
margin:2px 0 6px}
.legend span{display:inline-flex;align-items:center;gap:5px}
.legend svg{width:12px;height:12px}
.sw{display:inline-block;width:14px;height:10px;border-radius:2px}
.sw-b{background:var(--base)}
.sw-r{background:var(--reward);background-image:repeating-linear-gradient(45deg,
var(--hatch) 0 1.5px,transparent 1.5px 5px)}
.chart{width:100%;height:auto;display:block;overflow:visible}
.grid{stroke:var(--grid);stroke-width:1}
.axis{stroke:var(--axis);stroke-width:1}
.ref{stroke:var(--axis);stroke-width:1;stroke-dasharray:3 3}
.tick,.val,.axis-title{font-size:11px;fill:var(--ink-2)}
.val{fill:var(--ink)}
.pt-label{font-size:11px;font-weight:700;fill:var(--ink);paint-order:stroke;
stroke:var(--surface);stroke-width:3px}
.pt circle,.pt rect,.pt polygon{stroke:var(--surface);stroke-width:2}
.seg-b{fill:var(--base)}
.seg-r{fill:var(--reward)}
.hatch-line{stroke:var(--hatch);stroke-width:2}
.spark{flex:none}
.spark-line{fill:none;stroke:var(--base);stroke-width:2;stroke-linecap:round;
stroke-linejoin:round}
.spark-end{fill:var(--base)}
.spark-none{font-size:12px;color:var(--ink-2)}
.pools{display:grid;gap:12px}
.pool{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px;
display:flex;flex-direction:column;gap:8px;min-width:0}
.rank{display:inline-block;min-width:1.6em;color:var(--ink-2);font-weight:600}
.facts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:4px 12px;margin:0}
.facts div{display:flex;justify-content:space-between;gap:6px;font-size:14px}
.facts dt{color:var(--ink-2)}
.facts dd{margin:0;font-weight:600}
.d-up{color:var(--up)}.d-down{color:var(--down)}.d-flat{color:var(--ink-2)}
details{background:var(--surface);border:1px solid var(--line);border-radius:12px;
margin-bottom:12px}
details>summary{cursor:pointer;padding:12px 14px;font-weight:600}
details>*:not(summary){margin:0 14px 14px}
.table-wrap{overflow-x:auto}
table.list{width:100%;border-collapse:collapse;font-size:14px}
table.list th,table.list td{padding:7px 6px;border-bottom:1px solid var(--line);
text-align:left;vertical-align:middle}
table.list th{font-size:12px;color:var(--ink-2);font-weight:600}
table.list .n{text-align:right}
footer{font-size:12px;color:var(--ink-2);line-height:1.6}
footer p+p{margin-top:6px}
@media (min-width:760px){
 .recs{grid-template-columns:1fr 1fr;gap:16px}
 .rec{padding:18px 20px}
 .big{font-size:56px}
 .charts{grid-template-columns:1fr 1fr}
 .pools{grid-template-columns:repeat(auto-fill,minmax(300px,1fr))}
 .concl-text{font-size:22px}
}
@media (max-width:420px){
 .hwrap{padding:8px 14px}
 main{padding:10px 14px 40px}
 .rec{padding:12px 14px;gap:4px}
 .recs{gap:10px;margin-bottom:14px}
 table.list{font-size:13px}
 .tick,.val,.axis-title,.pt-label{font-size:12.5px}
}
@media (prefers-reduced-motion:no-preference){
 .bar-seg{transform-box:fill-box;transform-origin:left center;animation:grow .6s ease-out both}
 .spark-line{stroke-dasharray:1;stroke-dashoffset:1;animation:draw .9s ease-out .25s forwards}
 .reveal{animation:fade .45s ease-out both}
 .recs .reveal:nth-child(2){animation-delay:.08s}
 .concl.reveal{animation-delay:.16s}
 .pools .reveal:nth-child(2){animation-delay:.06s}
 .pools .reveal:nth-child(3){animation-delay:.12s}
 .pools .reveal:nth-child(4){animation-delay:.18s}
 .pools .reveal:nth-child(5){animation-delay:.24s}
}
@keyframes grow{from{transform:scaleX(0)}to{transform:scaleX(1)}}
@keyframes draw{to{stroke-dashoffset:0}}
@keyframes fade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
"""
)

RISK_NOTE = ("위험 등급은 가장 나쁜 항목 하나로 정합니다. 높음: 보상 의존, 출시 2년 미만 체인, "
             "락업, TVL 1천만 달러 미만, 30일 이자 변동 1%p 이상 중 하나라도 해당. "
             "낮음: TVL 1억 달러 이상, 성숙한 체인, 수시 출금, BTC 보관 방식 확인, "
             "30일 변동 0.5%p 미만을 모두 충족. 나머지는 보통.")


def legend_grades() -> str:
    return "".join(
        f'<span><svg viewBox="0 0 12 12" aria-hidden="true">{shape(GRADE_KEY[g], 6, 6, 4.5)}'
        f"</svg>위험 {g}</span>" for g in GRADES)


def render(analysis: dict, summary: dict | None, cfg: dict) -> str:
    a = analysis
    status = summary_status(summary, a)
    rec = a.get("recommend") or {}
    price = a.get("btc_price")
    ranking = a.get("ranking") or []
    large = a.get("large_tvl_usd", 100_000_000)
    sc_svg, sc_note = scatter_chart(ranking, rec, large)
    bar_svg, bar_note = bar_chart(a.get("top") or [])
    top5 = "".join(top_card(r) for r in ranking[:5])
    rest = ranking[5:]
    sec = a["secondary"]
    price_line = ""
    if price:
        price_line = (f'<p class="price small muted">원화 환산은 1 BTC = '
                      f'{krw(price["krw"]).replace("약 ", "")} 기준({e(price["source"])}, '
                      f'{e(price["as_of_kst"])}). 실제 이자는 보상을 뺀 기본 APY입니다.</p>')
    lp = (f'<details><summary>LP형 {sec["count"]}개 보기 (토큰 2개 이상을 함께 맡기는 상품, '
          f"순위 제외)</summary>{rest_table(sec['top'])}</details>" if sec["count"] else "")
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<meta name="color-scheme" content="light dark">
<title>{e(cfg["title"])}</title><style>{CSS}</style></head>
<body>
<input type="checkbox" id="theme" aria-label="밝기 전환">
<header><div class="hwrap"><div><h1>{e(cfg["title"])}</h1>
<p class="meta">{e(short_time(a["latest"]["collected_at_kst"]))} 기준, 출처
<a href="https://defillama.com/yields" target="_blank" rel="noopener">{e(a["source"])}</a></p>
</div><label for="theme" class="toggle">밝기 전환</label></div></header>
<main>
<section class="recs" aria-label="추천">
{rec_card("stable", "안정 우선", stable_cond(rec), rec.get("stable"))}
{rec_card("yield", "이자 우선", "위험 높음을 뺀 풀 중 1위", rec.get("yield"))}
</section>
{conclusion_block(summary, status, cfg["summary_max_lines"])}
{price_line}
<section aria-labelledby="h-charts"><h2 id="h-charts">한눈에 보기</h2><div class="charts">
<figure><h3>이자 vs 규모 지도</h3><div class="legend">{legend_grades()}</div>{sc_svg}
<figcaption><p>{e(sc_note)}</p></figcaption></figure>
<figure><h3>실제 이자와 보상 (APY 합계 상위 10)</h3><div class="legend">
<span><i class="sw sw-b"></i>기본 APY (실제 이자)</span>
<span><i class="sw sw-r"></i>보상 APY (빗금)</span></div>{bar_svg}
<figcaption><p>{e(bar_note)}</p></figcaption></figure>
</div></section>
<section aria-labelledby="h-top"><h2 id="h-top">실제 이자 상위 5</h2>
<div class="pools">{top5}</div></section>
<details><summary>나머지 {len(rest)}개 보기</summary>{rest_table(rest)}</details>
{lp}
<details><summary>전일 대비, 유형별 통계 보기</summary>{change_block(a)}{stats_table(a["stats"])}
</details>
<footer><p>분석 {e(a.get("generated_at_kst"))}. 추이선은 최근 {e(a.get("charts_days", 30))}일
기본 APY(DefiLlama 풀별 이력), 7일 변화도 기본 APY 기준입니다.</p><p>{RISK_NOTE}</p></footer>
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
