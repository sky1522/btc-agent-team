"""수집 이력으로 상위 N개, 전일 대비 변화, 신규·이탈 풀을 계산한다.

실행: uv run python tools/analyze_yields.py
입력: data/history.jsonl
출력: data/analysis.json
설정: tools/config.toml [analyze]

전일 = 최신 스냅샷의 KST 날짜보다 이전 날짜 중 가장 최근 스냅샷.
없으면 변화·신규·이탈 항목은 "비교 데이터 없음".
"""

from __future__ import annotations

import sys
from datetime import datetime
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


def ranked(pools: list[dict], n: int, url_prefix: str, ratio: float) -> list[dict]:
    ordered = sorted(pools, key=lambda p: p["apy"], reverse=True)
    return [
        {
            "rank": i,
            **{k: p.get(k) for k in ("pool", "type", "project", "chain", "symbol", "note",
                                     "apy", "apy_base", "apy_reward", "tvl_usd")},
            "url": url_prefix + p["pool"],
            "flags": flags_for(p, ratio),
        }
        for i, p in enumerate(ordered[:n], 1)
    ]


def analyze(history: list[dict], config: dict[str, Any], at: datetime) -> dict:
    acfg = config["analyze"]
    url_prefix = config["collect"]["pool_url_prefix"]
    primary, secondary = acfg["primary_type"], acfg["secondary_type"]
    ratio = acfg["reward_dependency_ratio"]
    latest, previous = pick_latest_and_previous(history)
    if latest is None:
        raise RuntimeError("이력이 없습니다. 먼저 수집: uv run python tools/defillama_btc.py")

    now_primary = of_type(latest["pools"], primary)
    now_secondary = of_type(latest["pools"], secondary)

    result: dict[str, Any] = {
        "generated_at": at.isoformat(timespec="seconds"),
        "generated_at_kst": fmt_kst(at),
        "source": latest.get("source", config["collect"]["source_name"]),
        "latest": snap_meta(latest),
        "previous": snap_meta(previous) if previous else None,
        "primary_type": primary,
        "top_n": acfg["top_n"],
        "top": ranked(now_primary, acfg["top_n"], url_prefix, ratio),
        "secondary": {
            "type": secondary,
            "count": len(now_secondary),
            "top": ranked(now_secondary, acfg["top_n"], url_prefix, ratio),
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
    result = analyze(history, config, at or now_kst())
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
