import json
from datetime import datetime

import pytest

import analyze_yields as az
from common import KST

AT = datetime(2026, 10, 30, 15, 5, tzinfo=KST)


def test_single_day_history_reports_no_comparison(multi_day_history, config):
    one_day = [multi_day_history[-1]]
    r = az.analyze(one_day, config, AT)
    assert r["previous"] is None
    for key in ("change", "new_pools", "dropped_pools"):
        assert r[key] == {"status": "비교 데이터 없음", "items": []}
    assert [t["pool"] for t in r["top"]] == ["p-a", "p-d", "p-b"]
    assert "전일 대비: 비교 데이터 없음" in az.summary_lines(r)


def test_top_is_primary_type_only_and_lp_is_separate(multi_day_history, config):
    r = az.analyze(multi_day_history, config, AT)
    assert r["primary_type"] == "예치형"
    assert all(t["type"] == "예치형" for t in r["top"])
    assert "lp-x" not in [t["pool"] for t in r["top"]]  # APY 12%로 가장 높아도 기본 표에서 제외
    assert r["secondary"]["type"] == "LP형"
    assert r["secondary"]["count"] == 2
    assert [t["pool"] for t in r["secondary"]["top"]] == ["lp-x", "lp-y"]
    # 변화·신규·이탈도 예치형만
    changed = [c["pool"] for c in r["change"]["items"]]
    assert "lp-x" not in changed
    assert "lp-y" not in [p["pool"] for p in r["new_pools"]["items"]]


def test_previous_is_latest_snapshot_of_an_earlier_kst_day(multi_day_history, config):
    latest, previous = az.pick_latest_and_previous(multi_day_history)
    assert latest["collected_at"] == "2026-10-30T15:00:00+09:00"
    # 같은 날 09:00 스냅샷이 아니라 전날 스냅샷과 비교
    assert previous["collected_at"] == "2026-10-29T09:00:00+09:00"


def test_change_new_and_dropped(multi_day_history, config):
    r = az.analyze(multi_day_history, config, AT)
    assert r["change"]["status"] == "ok"
    deltas = {c["pool"]: c["delta_pp"] for c in r["change"]["items"]}
    assert deltas == {"p-a": pytest.approx(1.5), "p-b": pytest.approx(-1.0)}
    # 절댓값 큰 순
    assert [c["pool"] for c in r["change"]["items"]] == ["p-a", "p-b"]
    assert [p["pool"] for p in r["new_pools"]["items"]] == ["p-d"]
    assert [p["pool"] for p in r["dropped_pools"]["items"]] == ["p-c"]


def test_top_n_and_reward_dependency_flag(multi_day_history, config):
    cfg = dict(config, analyze=dict(config["analyze"], top_n=2))
    r = az.analyze(multi_day_history, cfg, AT)
    assert len(r["top"]) == 2
    flags = {t["pool"]: t["flags"] for t in az.analyze(multi_day_history, config, AT)["top"]}
    assert flags["p-b"] == ["보상 의존"]  # 보상 100%
    assert flags["p-a"] == []
    assert flags["p-d"] == []  # 보상 1.2/4.2 = 29%


def test_unordered_history_is_handled(multi_day_history, config):
    r = az.analyze(list(reversed(multi_day_history)), config, AT)
    assert r["latest"]["collected_at_kst"] == "2026-10-30 15:00 KST"
    assert r["previous"]["collected_at_kst"] == "2026-10-29 09:00 KST"


def test_empty_history_raises(config):
    with pytest.raises(RuntimeError):
        az.analyze([], config, AT)


def test_run_writes_analysis_json(tmp_path, multi_day_history, config):
    hist = tmp_path / "data" / "history.jsonl"
    hist.parent.mkdir(parents=True)
    hist.write_text("\n".join(json.dumps(s) for s in multi_day_history) + "\n", encoding="utf-8")
    az.run(config, root=tmp_path, at=AT)
    out = json.loads((tmp_path / "data/analysis.json").read_text(encoding="utf-8"))
    assert out["generated_at_kst"] == "2026-10-30 15:05 KST"
    assert out["source"] == "DefiLlama Yields"
    assert out["top"][0]["url"].startswith("https://defillama.com/yields/pool/")
