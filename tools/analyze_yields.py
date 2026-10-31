"""수집 이력으로 상위 N개, 전일 대비 변화, 신규·이탈 풀을 계산한다.

실행: uv run python tools/analyze_yields.py
입력: data/history.jsonl
출력: data/analysis.json
설정: tools/config.toml [analyze]

전일 = 최신 스냅샷의 KST 날짜보다 이전 날짜 중 가장 최근 스냅샷.
없으면 변화·신규·이탈 항목은 "비교 데이터 없음".
"""

from __future__ import annotations

import json
import statistics
import sys
import tomllib
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from common import (
    KST,
    ROOT,
    fmt_kst,
    load_config,
    now_kst,
    parse_iso,
    read_jsonl,
    resolve,
    utf8_stdout,
    write_json_atomic,
)

NO_COMPARE = "비교 데이터 없음"


def kst_date(snapshot: dict) -> str:
    return parse_iso(snapshot["collected_at"]).astimezone(KST).date().isoformat()


def pick_latest_and_previous(history: list[dict]) -> tuple[dict | None, dict | None]:
    if not history:
        return None, None
    ordered = sorted(history, key=lambda s: parse_iso(s["collected_at"]))
    latest = ordered[-1]
    latest_day = kst_date(latest)
    earlier = [s for s in ordered if kst_date(s) < latest_day]
    return latest, (earlier[-1] if earlier else None)


def flags_for(p: dict, ratio: float) -> list[str]:
    flags = []
    reward = p.get("apy_reward") or 0
    if p["apy"] and reward / p["apy"] >= ratio:
        flags.append("보상 의존")
    return flags


def snap_meta(s: dict) -> dict:
    at = parse_iso(s["collected_at"])
    return {
        "collected_at": s["collected_at"],
        "collected_at_kst": fmt_kst(at),
        "count": len(s["pools"]),
    }


def brief(p: dict) -> dict:
    keys = ("pool", "type", "project", "chain", "symbol", "note", "apy", "tvl_usd")
    return {k: p.get(k) for k in keys}


def of_type(pools: list[dict], type_name: str) -> list[dict]:
    return [p for p in pools if p.get("type") == type_name]


CHECK = "확인 필요"


def load_risk_map(config: dict[str, Any]) -> dict:
    with open(ROOT / config["paths"]["risk_map"], "rb") as f:
        return tomllib.load(f)


def _months_since(ym: str, d: date) -> int:
    y, m = (int(x) for x in ym.split("-"))
    return (d.year - y) * 12 + (d.month - m)


def _btc_form(symbol: str, chain: str, forms: dict) -> tuple[str, bool | None]:
    """심볼 → (BTC 형태, 수탁형 여부). 모르면 ("확인 필요", None)."""
    if symbol == "BTC":
        return ("네이티브 BTC", False) if chain == forms.get("native_chain") else (CHECK, None)
    v = forms.get(symbol)
    if isinstance(v, list):
        return v[0], bool(v[1])
    return CHECK, None


def classify(p: dict, rm: dict, as_of: date) -> tuple[dict, list[dict]]:
    """풀 1개의 리스크 항목과 배지. 매핑에 없는 항목은 추측하지 않고 '확인 필요'."""
    meta = (p.get("pool_meta") or p.get("note") or "").lower()
    lk = rm["lockup"]
    if any(k in meta for k in lk["keywords"]):
        lockup = "락업"
    elif p["project"] in lk["free_withdraw_projects"]:
        lockup = "수시 출금"
    else:
        lockup = CHECK

    if any(k in meta for k in rm["reward"]["points_keywords"]):
        reward = "포인트"
    elif (p.get("apy_reward") or 0) > 0:
        reward = "토큰"
    else:
        reward = "없음"

    tokens = [t for t in p["symbol"].upper().split("-") if t]
    forms = [_btc_form(t, p["chain"], rm["btc_form"]) for t in tokens]
    if any(f == CHECK for f, _ in forms):
        btc_form, custodial = CHECK, (True if any(c for _, c in forms) else None)
    else:
        btc_form = " + ".join(dict.fromkeys(f for f, _ in forms))
        custodial = any(c for _, c in forms)

    # 공식 문서로 확인한 풀별 값이 있으면 우선 (근거 링크는 risk_map.toml에)
    ov = rm.get("pool", {}).get(f'{p["project"]}|{p["chain"]}|{p["symbol"].upper()}', {})
    if "lockup" in ov:
        lockup = ov["lockup"]
    if "btc_form" in ov:
        btc_form, custodial = ov["btc_form"], ov.get("custodial")
    launched = rm["chain"]["launched"].get(p["chain"])
    if launched is None:
        chain_status = CHECK
    elif _months_since(launched, as_of) < rm["chain"]["new_months"]:
        chain_status = "신생"
    else:
        chain_status = "성숙"

    unknown = [name for name, v in (("락업", lockup), ("BTC 형태", btc_form),
                                    ("체인", chain_status)) if v == CHECK]
    badges = []
    if lockup == "락업":
        badges.append({"key": "lockup", "label": "락업"})
    if reward == "포인트":
        badges.append({"key": "points", "label": "포인트 보상"})
    if custodial:
        badges.append({"key": "custodial", "label": "수탁형"})
    if chain_status == "신생":
        badges.append({"key": "newchain", "label": "신생 체인"})
    if unknown:
        badges.append({"key": "check", "label": "확인 필요: " + "·".join(unknown)})
    risk = {"lockup": lockup, "reward_type": reward, "btc_form": btc_form,
            "custodial": custodial, "chain_status": chain_status,
            "chain_launched": launched, "unknown": unknown, "sources": ov.get("sources", [])}
    return risk, badges


@dataclass
class Ctx:
    """순위 행에 붙일 부가 정보: 리스크 매핑, 기준일, 30일 추이, BTC 원화 가격."""
    rm: dict
    as_of: date
    charts: dict = field(default_factory=dict)
    btc_krw: float | None = None
    large_tvl: float = 100_000_000


def trend(pool_id: str, charts: dict) -> dict:
    """30일 기본 APY 추이 지표. 추이 데이터가 없으면 빈 값."""
    series = [x["base"] for x in charts.get(pool_id, []) if x.get("base") is not None]
    if len(series) < 2:
        return {"spark": [], "base_30d_avg": None, "base_30d_std": None, "vol_cv": None,
                "base_7d_change": None, "vol_pp": None, "days": len(series)}
    mean = statistics.fmean(series)
    std = statistics.pstdev(series)
    return {
        "spark": [round(v, 4) for v in series],
        "base_30d_avg": round(mean, 4),
        "base_30d_std": round(std, 4),
        # 변동계수 = 30일 표준편차 ÷ 30일 평균 (상대 변동성)
        "vol_cv": round(std / mean, 4) if mean > 0 else None,
        "base_7d_change": round(series[-1] - series[-8], 4) if len(series) >= 8 else None,
        "vol_pp": round(max(series) - min(series), 4),   # 참고: 30일 최고-최저 차
        "days": len(series),
    }


def _musd(v: float) -> str:
    return f"${v / 1e6:,.1f}M"


def volatility_status(tr: dict, g: dict) -> str:
    """'high' | 'mid' | 'low' | 'excluded'(평균이 너무 낮아 판정 제외) | 'missing'"""
    mean, cv = tr.get("base_30d_avg"), tr.get("vol_cv")
    if mean is None:
        return "missing"
    if mean < g["cv_min_mean_pct"] or cv is None:
        return "excluded"
    if cv >= g["cv_high"]:
        return "high"
    return "low" if cv < g["cv_low"] else "mid"


def grade(p: dict, risk: dict, tr: dict, rm: dict, ratio: float,
          large_tvl: float) -> tuple[str, str, str]:
    """위험 등급(낮음/보통/높음), 이유 한 줄, 변동성 판정. 가장 나쁜 항목이 등급을 정한다."""
    g = rm["grade"]
    vs = volatility_status(tr, g)
    cv_pct = f"{(tr.get('vol_cv') or 0) * 100:.0f}%"
    reward = p.get("apy_reward") or 0
    high = []
    if p.get("apy") and reward / p["apy"] >= ratio:
        high.append("이자 대부분이 보상이라 끝나면 줄어듦")
    if risk["chain_status"] == "신생":
        high.append("출시 2년이 안 된 체인")
    if risk["lockup"] == "락업":
        high.append("락업 기간 동안 못 뺌")
    if p["tvl_usd"] < g["small_tvl_usd"]:
        high.append(f"규모가 작음(TVL {_musd(p['tvl_usd'])})")
    if vs == "high":
        high.append(f"30일 이자가 크게 출렁임(표준편차가 평균의 {cv_pct})")
    if high:
        return "높음", high[0], vs
    mid = []
    if p["tvl_usd"] < large_tvl:
        mid.append(f"규모 중간(TVL {_musd(p['tvl_usd'])})")
    if risk["lockup"].startswith("출금 대기"):
        mid.append(risk["lockup"])
    if risk["lockup"] == CHECK:
        mid.append("출금 조건 확인 필요")
    if risk["btc_form"] == CHECK:
        mid.append("BTC 보관 방식 확인 필요")
    if risk["chain_status"] == CHECK:
        mid.append("체인 출시 시점 확인 필요")
    if vs == "missing":
        mid.append("이자 변동 데이터 없음")
    elif vs == "mid":
        mid.append(f"30일 이자 변동 중간(표준편차가 평균의 {cv_pct})")
    if mid:
        return "보통", mid[0], vs
    if vs == "excluded":
        return ("낮음", "대형 풀, 성숙한 체인, 수시 출금 (이자가 0.5% 미만이라 변동성은 판정 제외)",
                vs)
    return "낮음", "대형 풀, 성숙한 체인, 수시 출금, 이자 변동 작음", vs


def ranked(pools: list[dict], n: int, url_prefix: str, ratio: float,
           key: str = "apy", risk_ctx: Ctx | None = None) -> list[dict]:
    ordered = sorted(pools, key=lambda p: (p.get(key) or 0, p.get("apy") or 0), reverse=True)
    rows = []
    for i, p in enumerate(ordered[:n], 1):
        row = {
            "rank": i,
            **{k: p.get(k) for k in ("pool", "type", "project", "chain", "symbol", "note",
                                     "apy", "apy_base", "apy_reward", "tvl_usd")},
            "url": url_prefix + p["pool"],
            "flags": flags_for(p, ratio),
            # 1 BTC를 1년 맡겼을 때 기본 APY 기준 이자 (BTC). APY는 복리 포함 연 수익률
            "btc_per_year": None if p.get("apy_base") is None else round(p["apy_base"] / 100, 6),
        }
        for k in ("apy_mean_30d", "apy_pct_1d", "apy_pct_7d", "apy_pct_30d"):
            row[k] = p.get(k)
        if risk_ctx:
            c = risk_ctx
            row["risk"], row["badges"] = classify(p, c.rm, c.as_of)
            tr = trend(p["pool"], c.charts)
            row.update(tr)
            row["grade"], row["grade_reason"], row["vol_status"] = grade(
                p, row["risk"], tr, c.rm, ratio, c.large_tvl)
            row["krw_per_year"] = (round(row["btc_per_year"] * c.btc_krw)
                                   if c.btc_krw and row["btc_per_year"] is not None else None)
        rows.append(row)
    return rows


def _r(x: float | None, nd: int = 4) -> float | None:
    return None if x is None else round(x, nd)


def type_stats(pools: list[dict], ratio: float) -> dict:
    """유형 하나의 요약 통계. 에이전트는 이 값만 인용한다(직접 계산 금지)."""
    n = len(pools)
    if n == 0:
        return {"count": 0, "tvl_usd_sum": 0, "apy_mean": None, "apy_median": None,
                "apy_tvl_weighted": None, "base_share_pct": None, "reward_share_pct": None,
                "reward_dependent_count": 0}
    apys = [p["apy"] for p in pools]
    tvl_sum = sum(p["tvl_usd"] for p in pools)
    apy_sum = sum(apys)
    base_sum = sum(p.get("apy_base") or 0 for p in pools)
    reward_sum = sum(p.get("apy_reward") or 0 for p in pools)
    return {
        "count": n,
        "tvl_usd_sum": round(tvl_sum, 2),
        "apy_mean": _r(statistics.fmean(apys)),
        "apy_median": _r(statistics.median(apys)),
        "apy_tvl_weighted": _r(sum(p["apy"] * p["tvl_usd"] for p in pools) / tvl_sum)
        if tvl_sum else None,
        # APY 합계 중 기본/보상이 차지하는 비중 (%). 둘의 합이 100이 아닐 수 있음(원본 누락)
        "base_share_pct": _r(base_sum / apy_sum * 100, 2) if apy_sum else None,
        "reward_share_pct": _r(reward_sum / apy_sum * 100, 2) if apy_sum else None,
        "reward_dependent_count": sum(1 for p in pools if flags_for(p, ratio)),
    }


def ranked_by_base(pools: list[dict], n: int, url_prefix: str, ratio: float,
                   risk_ctx: Ctx | None = None) -> list[dict]:
    with_base = [p for p in pools if (p.get("apy_base") or 0) > 0]
    return ranked(with_base, n, url_prefix, ratio, key="apy_base", risk_ctx=risk_ctx)


def usd_kr(v: float) -> str:
    """100_000_000 → '1억 달러', 50_000_000 → '5천만 달러'"""
    return f"{v / 1e8:g}억 달러" if v >= 1e8 else f"{v / 1e7:g}천만 달러"


def recommend(ranking: list[dict], tvl_steps: list[float]) -> dict:
    """안정 우선: 위험 낮음·보통 중 TVL 기준 이상 기본 APY 1위(기준을 단계적으로 낮춤).
    이자 우선: 위험 높음을 뺀 기본 APY 1위."""
    ok = [r for r in ranking if r.get("grade") in ("낮음", "보통") and (r.get("apy_base") or 0) > 0]
    stable, used = None, None
    for t in tvl_steps:
        stable = next((r for r in ok if r["tvl_usd"] >= t), None)
        if stable:
            used = t
            break
    if stable is None:
        note = f"위험 낮음·보통인 풀 중 TVL {usd_kr(tvl_steps[-1])} 이상이 없음"
    elif used != tvl_steps[0]:
        note = f"TVL {usd_kr(tvl_steps[0])} 이상 중 해당 풀이 없어 기준을 낮춤"
    else:
        note = ""
    return {"stable": stable, "stable_tvl_min": used, "stable_note": note,
            "yield": ok[0] if ok else None}


def analyze(history: list[dict], config: dict[str, Any], at: datetime,
            extras: dict | None = None) -> dict:
    """extras: {"charts": data/charts.json의 pools, "btc_price": yields.json의 btc_price}"""
    extras = extras or {}
    acfg = config["analyze"]
    url_prefix = config["collect"]["pool_url_prefix"]
    primary, secondary = acfg["primary_type"], acfg["secondary_type"]
    ratio = acfg["reward_dependency_ratio"]
    latest, previous = pick_latest_and_previous(history)
    if latest is None:
        raise RuntimeError("이력이 없습니다. 먼저 수집: uv run python tools/defillama_btc.py")

    now_primary = of_type(latest["pools"], primary)
    now_secondary = of_type(latest["pools"], secondary)
    as_of = parse_iso(latest["collected_at"]).astimezone(KST).date()
    large = acfg["large_tvl_usd"]
    price = extras.get("btc_price")
    ctx = Ctx(load_risk_map(config), as_of, extras.get("charts") or {},
              (price or {}).get("krw"), large)
    top_by_base = ranked_by_base(now_primary, acfg["base_top_n"], url_prefix, ratio, ctx)
    large_top = ranked_by_base([p for p in now_primary if p["tvl_usd"] >= large], 3,
                               url_prefix, ratio, ctx)
    primary_stats = type_stats(now_primary, ratio)
    ranking = ranked(now_primary, len(now_primary), url_prefix, ratio, key="apy_base",
                     risk_ctx=ctx)

    result: dict[str, Any] = {
        "generated_at": at.isoformat(timespec="seconds"),
        "generated_at_kst": fmt_kst(at),
        "source": latest.get("source", config["collect"]["source_name"]),
        "latest": snap_meta(latest),
        "previous": snap_meta(previous) if previous else None,
        "primary_type": primary,
        "top_n": acfg["top_n"],
        "top": ranked(now_primary, acfg["top_n"], url_prefix, ratio),
        # 예치형 전체 순위 (대시보드용): 기본 APY 내림차순, 리스크 분류·위험 등급 포함
        "ranking": ranking,
        # 추천 2종: 안정 우선(TVL 1억 달러 이상 중 기본 APY 1위), 이자 우선(위험 높음 제외 1위)
        "recommend": recommend(ranking, acfg["stable_tvl_steps"]),
        "btc_price": price,
        "charts_days": config["collect"]["chart_days"],
        # 기본 APY(실제 이자) 기준 상위. 보상·포인트 의존 수익과 구분해서 보기 위함
        "top_by_base": top_by_base,
        # TVL large_tvl_usd 이상 대형 풀 중 기본 APY 상위
        "large_tvl_usd": large,
        "large_top": large_top,
        "kpi": {
            "base_top": top_by_base[0] if top_by_base else None,
            "large_top": large_top[0] if large_top else None,
            "large_tvl_usd": large,
            "primary_count": primary_stats["count"],
            "primary_tvl_usd_sum": primary_stats["tvl_usd_sum"],
            "reward_share_pct": primary_stats["reward_share_pct"],
            "reward_dependent_count": primary_stats["reward_dependent_count"],
        },
        "stats": {
            primary: primary_stats,
            secondary: type_stats(now_secondary, ratio),
        },
        "secondary": {
            "type": secondary,
            "count": len(now_secondary),
            "top": ranked(now_secondary, len(now_secondary), url_prefix, ratio,
                          key="apy_base", risk_ctx=ctx),
        },
    }

    if previous is None:
        empty = {"status": NO_COMPARE, "items": []}
        result["change"] = dict(empty)
        result["new_pools"] = dict(empty)
        result["dropped_pools"] = dict(empty)
        return result

    # 변화·신규·이탈은 기본 유형(예치형)만 대상
    prev_by_id = {p["pool"]: p for p in of_type(previous["pools"], primary)}
    now_by_id = {p["pool"]: p for p in now_primary}
    changes = []
    for pid, p in now_by_id.items():
        old = prev_by_id.get(pid)
        if old is None:
            continue
        changes.append({
            **brief(p),
            "apy_prev": old["apy"],
            "apy_now": p["apy"],
            "delta_pp": round(p["apy"] - old["apy"], 4),
            "tvl_prev": old["tvl_usd"],
        })
    changes.sort(key=lambda c: abs(c["delta_pp"]), reverse=True)

    new_ids = now_by_id.keys() - prev_by_id.keys()
    dropped_ids = prev_by_id.keys() - now_by_id.keys()
    result["change"] = {"status": "ok", "items": changes[: acfg["change_top_n"]]}
    result["new_pools"] = {
        "status": "ok",
        "items": sorted((brief(now_by_id[i]) for i in new_ids), key=lambda p: -p["apy"]),
    }
    result["dropped_pools"] = {
        "status": "ok",
        "items": sorted((brief(prev_by_id[i]) for i in dropped_ids), key=lambda p: -p["apy"]),
    }
    return result


def run(config: dict[str, Any] | None = None, root: Path = ROOT,
        at: datetime | None = None) -> dict:
    config = config or load_config()
    paths = config["paths"]
    history = read_jsonl(resolve(paths["history"], root))
    extras = {}
    charts_path, yields_path = resolve(paths["charts"], root), resolve(paths["yields"], root)
    if charts_path.exists():
        extras["charts"] = json.loads(charts_path.read_text(encoding="utf-8")).get("pools", {})
    if yields_path.exists():
        extras["btc_price"] = json.loads(yields_path.read_text(encoding="utf-8")).get("btc_price")
    result = analyze(history, config, at or now_kst(), extras)
    write_json_atomic(resolve(paths["analysis"], root), result)
    return result


def summary_lines(r: dict) -> list[str]:
    lines = [f"기준: {r['latest']['collected_at_kst']} · 출처: {r['source']}"]
    lines.append(f"{r['primary_type']} 상위 {len(r['top'])}개 (APY)")
    for t in r["top"]:
        tags = ([t["note"]] if t.get("note") else []) + t["flags"]
        tag = f" [{' | '.join(tags)}]" if tags else ""
        lines.append(f"{t['rank']}. {t['project']}/{t['chain']}/{t['symbol']} "
                     f"{t['apy']:.2f}% TVL ${t['tvl_usd'] / 1e6:.1f}M{tag}")
    lines.append(f"기본 APY 상위 {len(r['top_by_base'])}개 (보상 제외 실제 이자)")
    for t in r["top_by_base"]:
        lines.append(f"{t['rank']}. {t['project']}/{t['chain']}/{t['symbol']} "
                     f"기본 {t['apy_base']:.2f}% (합계 {t['apy']:.2f}%)")
    st = r["stats"][r["primary_type"]]
    if st["count"]:
        tvl_m = st["tvl_usd_sum"] / 1e6
        lines.append(f"{r['primary_type']} 통계: {st['count']}개, TVL ${tvl_m:.1f}M, "
                     f"APY 평균 {st['apy_mean']:.2f}% / 중앙 {st['apy_median']:.2f}%, "
                     f"기본 {st['base_share_pct']}% · 보상 {st['reward_share_pct']}%, "
                     f"보상 의존 {st['reward_dependent_count']}개")
    sec = r["secondary"]
    lines.append(f"{sec['type']} {sec['count']}개는 별도 섹션(data/analysis.json secondary)")
    if r["previous"] is None:
        lines.append(f"전일 대비: {NO_COMPARE}")
    else:
        lines.append(f"{r['primary_type']} 전일 대비 ({r['previous']['collected_at_kst']} → "
                     f"{r['latest']['collected_at_kst']})")
        for c in r["change"]["items"][:5]:
            lines.append(f"- {c['project']}/{c['symbol']} {c['apy_prev']:.2f}% → "
                         f"{c['apy_now']:.2f}% ({c['delta_pp']:+.2f}%p)")
        lines.append(f"신규 {len(r['new_pools']['items'])}개 · "
                     f"이탈 {len(r['dropped_pools']['items'])}개")
    return lines


def main() -> int:
    utf8_stdout()
    try:
        r = run()
    except Exception as e:
        print(f"분석 실패: {e}", file=sys.stderr)
        return 1
    print("\n".join(summary_lines(r)))
    print("저장 → data/analysis.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
