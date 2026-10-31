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


def _pool(pid, note="", project="aave-v3", symbol="WBTC", tvl=1.0):
    return {"pool": pid, "project": project, "chain": "Ethereum", "symbol": symbol,
            "pool_meta": note or None, "note": note, "tvl_usd": tvl}


def test_duplicate_rows_get_distinct_notes_without_pool_id():
    pools = [
        _pool("aaaaaaaa-1111", tvl=10), _pool("bbbbbbbb-2222", tvl=20),   # meta 없음
        _pool("cccccccc-3333", "Core", "morpho"), _pool("dddddddd-4444", "Prime", "morpho"),
        _pool("eeeeeeee-5555", "Same", "euler", tvl=5), _pool("ffffffff-6666", "Same", "euler"),
        _pool("99999999-7777", "Solo", "spark"),                          # 단독 → 그대로
    ]
    dl.disambiguate_notes(pools)
    notes = {p["pool"][:2]: p["note"] for p in pools}
    assert notes == {"aa": "동일 이름 2/2", "bb": "동일 이름 1/2",       # TVL 큰 순
                     "cc": "Core", "dd": "Prime",
                     "ee": "Same · 동일 이름 1/2", "ff": "Same · 동일 이름 2/2", "99": "Solo"}
    assert not any("aaaaaaaa" in n for n in notes.values())


@pytest.mark.parametrize(
    ("meta", "symbol", "expected"),
    [
        ("Solv Protocol-Solv Protocol-SolvBTC", "SOLVBTC", "Solv Protocol"),
        ("Lombard-Flow Traders-LBTC", "LBTC", "Lombard · Flow Traders"),
        ("Locked veBTC", "BTC", "Locked veBTC"),
        ("SolvBTC", "SOLVBTC", "SolvBTC"),   # 남는 게 없으면 원래 조각 유지
        (None, "WBTC", ""),
    ],
)
def test_clean_meta(meta, symbol, expected):
    assert dl.clean_meta(meta, symbol) == expected


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
