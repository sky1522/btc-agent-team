"""DefiLlama Yields에서 BTC 계열 풀을 수집한다.

실행: uv run python tools/defillama_btc.py
출력: data/yields.json (최신 스냅샷), data/history.jsonl (수집 1회당 1줄 누적)
설정: tools/config.toml
"""

from __future__ import annotations

import json
import sys
import urllib.request
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


def normalize(raw: dict[str, Any], pool_url_prefix: str) -> dict[str, Any]:
    return {
        "pool": raw["pool"],
        "project": raw["project"],
        "chain": raw["chain"],
        "symbol": raw["symbol"],
        "pool_meta": raw.get("poolMeta"),
        "apy": raw["apy"],
        "apy_base": raw.get("apyBase"),
        "apy_reward": raw.get("apyReward"),
        "tvl_usd": raw["tvlUsd"],
        "apy_pct_1d_source": raw.get("apyPct1D"),  # DefiLlama 제공 1일 변화(%p), 참고용
        "exposure": raw.get("exposure"),
        "url": pool_url_prefix + raw["pool"],
    }


def select_btc_pools(raw_pools: list[dict[str, Any]], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    btc_tokens = {t.upper() for t in cfg["btc_tokens"]}
    picked = [
        normalize(p, cfg["pool_url_prefix"])
        for p in raw_pools
        if is_btc_pool(p, btc_tokens) and passes_noise_filter(p, cfg)
    ]
    picked.sort(key=lambda p: p["apy"], reverse=True)
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
        },
        "count": len(pools),
        "pools": pools,
    }


def history_record(snapshot: dict) -> dict:
    keep = ("pool", "project", "chain", "symbol", "apy", "apy_base", "apy_reward", "tvl_usd")
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
    print(f"BTC 계열 풀 {snap['count']}개 저장 → data/yields.json, data/history.jsonl")
    for i, p in enumerate(snap["pools"][:5], 1):
        print(f"{i}. {p['project']} / {p['chain']} / {p['symbol']} APY {p['apy']:.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
