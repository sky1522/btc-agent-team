"""DefiLlama Yields에서 BTC 계열 풀을 수집한다.

실행: uv run python tools/defillama_btc.py
출력: data/yields.json (최신 스냅샷), data/history.jsonl (수집 1회당 1줄 누적)
설정: tools/config.toml
"""

from __future__ import annotations

import json
import sys
import urllib.request
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from common import (
    ROOT,
    append_jsonl,
    fmt_kst,
    load_config,
    now_kst,
    resolve,
    utf8_stdout,
    write_json_atomic,
)

Fetcher = Callable[[str, int], dict[str, Any]]


def fetch_pools(url: str, timeout: int) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "btc-agent-team/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def symbol_tokens(symbol: str) -> list[str]:
    """'WBTC-cbBTC' -> ['WBTC', 'CBBTC']"""
    return [t for t in symbol.upper().split("-") if t]


def is_btc_pool(raw: dict[str, Any], btc_tokens: set[str]) -> bool:
    tokens = symbol_tokens(raw.get("symbol") or "")
    return bool(tokens) and all(t in btc_tokens for t in tokens)


def passes_noise_filter(raw: dict[str, Any], cfg: dict[str, Any]) -> bool:
    apy = raw.get("apy")
    tvl = raw.get("tvlUsd")
    if apy is None or tvl is None:
        return False
    if tvl < cfg["min_tvl_usd"] or apy < cfg["min_apy"]:
        return False
    if cfg.get("exclude_outliers", True) and raw.get("outlier"):
        return False
    return True


def pool_type(raw: dict[str, Any], type_by_exposure: dict[str, str]) -> str:
    return type_by_exposure.get(raw.get("exposure") or "", "기타")


def normalize(raw: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    return {
        "pool": raw["pool"],
        "type": pool_type(raw, cfg["type_by_exposure"]),
        "project": raw["project"],
        "chain": raw["chain"],
        "symbol": raw["symbol"],
        "pool_meta": raw.get("poolMeta"),
        "note": clean_meta(raw.get("poolMeta"), raw["symbol"]),
        "apy": raw["apy"],
        "apy_base": raw.get("apyBase"),
        "apy_reward": raw.get("apyReward"),
        "tvl_usd": raw["tvlUsd"],
        "apy_pct_1d_source": raw.get("apyPct1D"),  # DefiLlama 제공 1일 변화(%p), 참고용
        "exposure": raw.get("exposure"),
        "il_risk": raw.get("ilRisk"),
        "url": cfg["pool_url_prefix"] + raw["pool"],
    }


def clean_meta(meta: str | None, symbol: str) -> str:
    """'Solv Protocol-Solv Protocol-SolvBTC' → 'Solv Protocol'

    '-'로 나눈 조각 중 중복과 심볼과 같은 조각을 빼고 ' · '로 잇는다.
    """
    if not meta:
        return ""
    parts: list[str] = []
    for seg in (s.strip() for s in meta.split("-")):
        if seg and seg.lower() not in (p.lower() for p in parts):
            parts.append(seg)
    trimmed = [p for p in parts if p.upper() != symbol.upper()]
    return " · ".join(trimmed or parts)


def disambiguate_notes(pools: list[dict[str, Any]]) -> None:
    """같은 프로토콜·체인·심볼이 여러 줄이면 비고(note)로 구분되게 한다.

    정리된 poolMeta가 그룹 안에서 서로 다르면 그대로, 아니면 TVL 큰 순으로
    "동일 이름 i/n"을 덧붙인다. pool id는 화면에 쓰지 않는다(링크로만).
    """
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for p in pools:
        groups[(p["project"], p["chain"], p["symbol"].upper())].append(p)
    for members in groups.values():
        if len(members) < 2:
            continue
        notes = [m["note"] for m in members]
        if all(notes) and len(set(notes)) == len(notes):
            continue
        members.sort(key=lambda m: m["tvl_usd"], reverse=True)
        n = len(members)
        for i, m in enumerate(members, 1):
            tag = f"동일 이름 {i}/{n}"
            m["note"] = f"{m['note']} · {tag}" if m["note"] else tag


def select_btc_pools(raw_pools: list[dict[str, Any]], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    btc_tokens = {t.upper() for t in cfg["btc_tokens"]}
    picked = [
        normalize(p, cfg)
        for p in raw_pools
        if is_btc_pool(p, btc_tokens) and passes_noise_filter(p, cfg)
    ]
    picked.sort(key=lambda p: p["apy"], reverse=True)
    disambiguate_notes(picked)
    return picked


def build_snapshot(pools: list[dict[str, Any]], cfg: dict[str, Any], at: datetime) -> dict:
    return {
        "source": cfg["source_name"],
        "source_url": cfg["url"],
        "collected_at": at.isoformat(timespec="seconds"),
        "collected_at_kst": fmt_kst(at),
        "filter": {
            "min_tvl_usd": cfg["min_tvl_usd"],
            "min_apy": cfg["min_apy"],
            "exclude_outliers": cfg.get("exclude_outliers", True),
            "btc_tokens": cfg["btc_tokens"],
            "type_by_exposure": cfg["type_by_exposure"],
        },
        "count": len(pools),
        "count_by_type": dict(Counter(p["type"] for p in pools)),
        "pools": pools,
    }


HISTORY_FIELDS = ("pool", "type", "project", "chain", "symbol", "pool_meta", "note",
                  "apy", "apy_base", "apy_reward", "tvl_usd")


def history_record(snapshot: dict) -> dict:
    keep = HISTORY_FIELDS
    return {
        "collected_at": snapshot["collected_at"],
        "source": snapshot["source"],
        "pools": [{k: p[k] for k in keep} for p in snapshot["pools"]],
    }


def run(
    config: dict[str, Any] | None = None,
    root: Path = ROOT,
    fetcher: Fetcher = fetch_pools,
    at: datetime | None = None,
) -> dict:
    config = config or load_config()
    cfg = config["collect"]
    paths = config["paths"]
    resp = fetcher(cfg["url"], cfg["timeout_sec"])
    if resp.get("status") != "success" or not isinstance(resp.get("data"), list):
        raise RuntimeError(f"DefiLlama 응답 이상: status={resp.get('status')!r}")
    pools = select_btc_pools(resp["data"], cfg)
    snapshot = build_snapshot(pools, cfg, at or now_kst())
    write_json_atomic(resolve(paths["yields"], root), snapshot)
    append_jsonl(resolve(paths["history"], root), history_record(snapshot))
    return snapshot


def main() -> int:
    utf8_stdout()
    try:
        snap = run()
    except Exception as e:  # 수집 실패 시 기존 파일은 그대로 둔다
        print(f"수집 실패: {e}", file=sys.stderr)
        return 1
    print(f"기준: {snap['collected_at_kst']} · 출처: {snap['source']}")
    by_type = ", ".join(f"{k} {v}개" for k, v in snap["count_by_type"].items())
    print(f"BTC 계열 풀 {snap['count']}개 ({by_type}) 저장 → data/yields.json, data/history.jsonl")
    return 0


if __name__ == "__main__":
    sys.exit(main())
