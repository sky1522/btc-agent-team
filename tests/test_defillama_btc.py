import json
from datetime import datetime

import pytest

import defillama_btc as dl
from common import KST, read_jsonl

AT = datetime(2026, 10, 31, 14, 45, tzinfo=KST)


def ids(pools):
    return {p["pool"] for p in pools}


def test_filter_keeps_only_btc_family_above_noise_floor(raw_response, config):
    picked = dl.select_btc_pools(raw_response["data"], config["collect"])
    assert ids(picked) == {
        "fx-wbtc-single", "fx-wbtc-dup2", "fx-cbbtc-mixedcase", "fx-wbtc-cbbtc-lp"}


def test_type_from_exposure(raw_response, config):
    picked = {p["pool"]: p for p in dl.select_btc_pools(raw_response["data"], config["collect"])}
    assert picked["fx-wbtc-single"]["type"] == "예치형"
    assert picked["fx-wbtc-cbbtc-lp"]["type"] == "LP형"
    assert dl.pool_type({"exposure": "weird"}, config["collect"]["type_by_exposure"]) == "기타"


def test_tvl_floor_is_5m(config):
    assert config["collect"]["min_tvl_usd"] == 5_000_000


def test_stx_based_token_excluded(config):
    tokens = {t.upper() for t in config["collect"]["btc_tokens"]}
    assert not dl.is_btc_pool({"symbol": "STSTXBTC"}, tokens)


def _pool(pid, meta=None, project="aave-v3", symbol="WBTC"):
    return {"pool": pid, "project": project, "chain": "Ethereum", "symbol": symbol,
            "pool_meta": meta, "note": meta or ""}


def test_duplicate_rows_get_distinct_notes():
    pools = [
        _pool("aaaaaaaa-1111"), _pool("bbbbbbbb-2222"),                 # meta 없음 → id 8자리
        _pool("cccccccc-3333", "Core", "morpho"), _pool("dddddddd-4444", "Prime", "morpho"),
        _pool("eeeeeeee-5555", "Same", "euler"), _pool("ffffffff-6666", "Same", "euler"),
        _pool("99999999-7777", "Solo", "spark"),                         # 단독 → meta 그대로
    ]
    dl.disambiguate_notes(pools)
    notes = [p["note"] for p in pools]
    assert notes == ["aaaaaaaa", "bbbbbbbb", "Core", "Prime",
                     "Same · eeeeeeee", "Same · ffffffff", "Solo"]


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [
        ("WBTC", True),
        ("cbBTC", True),
        ("WBTC-CBBTC", True),
        ("WBTC-USDC", False),
        ("STSTXBTC", False),
        ("BTCBULL", False),
        ("STETH", False),
        ("", False),
    ],
)
def test_is_btc_pool(symbol, expected, config):
    tokens = {t.upper() for t in config["collect"]["btc_tokens"]}
    assert dl.is_btc_pool({"symbol": symbol}, tokens) is expected


def test_sorted_by_apy_desc_and_fields_split(raw_response, config):
    picked = dl.select_btc_pools(raw_response["data"], config["collect"])
    assert [p["apy"] for p in picked] == sorted((p["apy"] for p in picked), reverse=True)
    top = picked[0]
    assert top["pool"] == "fx-cbbtc-mixedcase"
    assert (top["apy_base"], top["apy_reward"]) == (0.5, 3.5)
    assert top["url"] == "https://defillama.com/yields/pool/fx-cbbtc-mixedcase"
    assert {"project", "chain", "symbol", "tvl_usd"} <= top.keys()


def test_min_tvl_is_configurable(raw_response, config):
    cfg = dict(config["collect"], min_tvl_usd=100_000)
    picked = dl.select_btc_pools(raw_response["data"], cfg)
    assert "fx-wbtc-small" in ids(picked)


def test_run_writes_snapshot_and_appends_history(tmp_path, raw_response, config):
    def fake_fetch(url, timeout):
        return raw_response

    dl.run(config, root=tmp_path, fetcher=fake_fetch, at=AT)
    dl.run(config, root=tmp_path, fetcher=fake_fetch, at=AT)

    snap = json.loads((tmp_path / "data/yields.json").read_text(encoding="utf-8"))
    assert snap["collected_at"] == "2026-10-31T14:45:00+09:00"
    assert snap["collected_at_kst"] == "2026-10-31 14:45 KST"
    assert snap["source"] == "DefiLlama Yields"
    assert snap["count"] == 4
    assert snap["count_by_type"] == {"예치형": 3, "LP형": 1}

    history = read_jsonl(tmp_path / "data/history.jsonl")
    assert len(history) == 2  # 실행할 때마다 1줄 누적
    assert set(history[0]["pools"][0]) == set(dl.HISTORY_FIELDS)


def test_bad_response_keeps_existing_files(tmp_path, config):
    with pytest.raises(RuntimeError):
        dl.run(config, root=tmp_path, fetcher=lambda u, t: {"status": "error"}, at=AT)
    assert not (tmp_path / "data/yields.json").exists()
    assert not (tmp_path / "data/history.jsonl").exists()
