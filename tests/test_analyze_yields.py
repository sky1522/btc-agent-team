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


def test_stats_per_type(multi_day_history, config):
    r = az.analyze(multi_day_history, config, AT)
    s = r["stats"]["예치형"]
    # 최신(10-30 15:00) 예치형: p-a 6.5/102M, p-b 2.0(보상 100%)/39M, p-d 4.2(기본 3.0)/8M
    assert s["count"] == 3
    assert s["tvl_usd_sum"] == 149_000_000
    assert s["apy_mean"] == pytest.approx(12.7 / 3, abs=1e-4)
    assert s["apy_median"] == pytest.approx(4.2)
    assert s["apy_tvl_weighted"] == pytest.approx(774.6 / 149, abs=1e-4)
    assert s["base_share_pct"] == pytest.approx(74.80, abs=0.01)
    assert s["reward_share_pct"] == pytest.approx(25.20, abs=0.01)
    assert s["reward_dependent_count"] == 1
    lp = r["stats"]["LP형"]
    assert (lp["count"], lp["tvl_usd_sum"], lp["apy_median"]) == (2, 13_500_000, 7.5)
    assert lp["reward_dependent_count"] == 1


def test_stats_empty_type():
    s = az.type_stats([], 0.5)
    assert s["count"] == 0 and s["apy_mean"] is None and s["tvl_usd_sum"] == 0


def test_top_by_base_excludes_reward_only(multi_day_history, config):
    r = az.analyze(multi_day_history, config, AT)
    assert [t["pool"] for t in r["top_by_base"]] == ["p-a", "p-d"]  # p-b는 기본 APY 0
    assert [t["rank"] for t in r["top_by_base"]] == [1, 2]


def test_top_by_base_selects_by_base_not_total_apy():
    pools = [
        {"pool": "x", "apy": 10.0, "apy_base": 1.0, "apy_reward": 9.0, "tvl_usd": 1},
        {"pool": "y", "apy": 5.0, "apy_base": 4.0, "apy_reward": 1.0, "tvl_usd": 1},
    ]
    rows = az.ranked_by_base(pools, 1, "u/", 0.5)
    assert [r["pool"] for r in rows] == ["y"]


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


# ---------- 리스크 분류 · 기본 APY 정렬 · KPI ----------

AS_OF = datetime(2026, 10, 31, tzinfo=KST).date()


def _p(project, chain, symbol, meta=None, base=1.0, reward=None, tvl=1e7):
    return {"pool": f"{project}-{chain}-{symbol}", "project": project, "chain": chain,
            "symbol": symbol, "pool_meta": meta, "note": meta or "", "apy_base": base,
            "apy_reward": reward, "apy": (base or 0) + (reward or 0), "tvl_usd": tvl}


@pytest.fixture
def rm(config):
    return az.load_risk_map(config)


def labels(badges):
    return [b["label"] for b in badges]


def test_classify_locked_native_unknown_chain(rm):
    risk, badges = az.classify(_p("mezo-earn", "Mezo", "BTC", "Locked veBTC", 0.05, 2.96), rm,
                               AS_OF)
    assert risk["lockup"] == "락업"
    assert risk["reward_type"] == "토큰"
    assert risk["btc_form"] == "확인 필요"        # Bitcoin 체인이 아닌 BTC 표기
    assert risk["chain_status"] == "신생"         # Mezo 2025-05 출시
    assert labels(badges) == ["락업", "신생 체인", "확인 필요: BTC 형태"]
    risk, _ = az.classify(_p("x", "Unknownchain", "WBTC"), rm, AS_OF)
    assert risk["chain_status"] == "확인 필요"    # 매핑에 없는 체인


def test_classify_points_custodial_new_chain(rm):
    risk, badges = az.classify(_p("accountable", "Monad", "CBBTC", "Earn ACC Points", 3.6, 0.2),
                               rm, AS_OF)
    assert risk["reward_type"] == "포인트"
    assert risk["btc_form"].startswith("수탁형 (코인베이스") and risk["custodial"] is True
    assert risk["sources"]                        # 조사 근거 링크(풀별 매핑)
    assert risk["chain_status"] == "신생"         # 2025-11 출시 → 24개월 미만
    assert "포인트 보상" in labels(badges) and "수탁형" in labels(badges)
    assert "신생 체인" in labels(badges)


def test_classify_lending_and_native_bitcoin(rm):
    risk, badges = az.classify(_p("aave-v3", "Arbitrum", "WBTC"), rm, AS_OF)
    assert (risk["lockup"], risk["chain_status"]) == ("수시 출금", "성숙")
    assert labels(badges) == ["수탁형"]
    risk, _ = az.classify(_p("chainflip-amm", "Bitcoin", "BTC"), rm, AS_OF)
    assert risk["btc_form"] == "네이티브 BTC" and risk["custodial"] is False


def test_unknown_symbol_is_check_not_guess(rm):
    risk, badges = az.classify(_p("x", "Ethereum", "KBTC"), rm, AS_OF)
    assert risk["btc_form"] == "확인 필요"
    assert risk["custodial"] is None
    assert "수탁형" not in labels(badges)


def test_ranking_sorted_by_base_with_risk_and_btc_per_year(multi_day_history, config):
    r = az.analyze(multi_day_history, config, AT)
    assert [x["pool"] for x in r["ranking"]] == ["p-a", "p-d", "p-b"]   # 기본 6.5 > 3.0 > 0
    first = r["ranking"][0]
    assert first["btc_per_year"] == pytest.approx(0.065)
    assert "risk" in first and "badges" in first


def test_kpi_and_large_top(multi_day_history, config):
    r = az.analyze(multi_day_history, config, AT)
    k = r["kpi"]
    assert k["base_top"]["pool"] == "p-a"
    assert k["large_top"]["pool"] == "p-a"          # TVL 1억 달러 이상은 p-a(102M)뿐
    assert [x["pool"] for x in r["large_top"]] == ["p-a"]
    assert k["primary_count"] == 3
    assert k["reward_share_pct"] == pytest.approx(25.20, abs=0.01)



# ---------- 위험 등급 · 추이 · 추천 · 원화 ----------

def _ctx(rm, charts=None, krw=None):
    return az.Ctx(rm, AS_OF, charts or {}, krw, 100_000_000)


def _series(vals):
    return [{"d": f"2026-10-{i + 1:02d}", "base": v, "apy": v} for i, v in enumerate(vals)]


def test_trend_metrics():
    t = az.trend("x", {"x": _series([1.0] * 22 + [1.2, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.5])})
    assert t["days"] == 30
    assert t["base_30d_avg"] == pytest.approx((1.0 * 28 + 1.2 + 1.5) / 30, abs=1e-4)
    assert t["base_7d_change"] == pytest.approx(1.5 - 1.2)   # 오늘 - 7일 전
    assert t["vol_pp"] == pytest.approx(0.5)                 # 최고-최저
    assert az.trend("none", {})["spark"] == []


def test_grade_rules(rm):
    big = _p("aave-v3", "Arbitrum", "WBTC", base=0.5, tvl=2e8)
    rows = az.ranked([big], 1, "u/", 0.5, key="apy_base",
                     risk_ctx=_ctx(rm, {big["pool"]: _series([0.5, 0.52] * 15)}))
    assert rows[0]["grade"] == "낮음"
    small = _p("aave-v3", "Arbitrum", "WBTC", base=0.5, tvl=5e6)
    assert az.ranked([small], 1, "u/", 0.5, risk_ctx=_ctx(rm))[0]["grade"] == "높음"
    reward = _p("aave-v3", "Arbitrum", "WBTC", base=0.1, reward=2.0, tvl=2e8)
    r = az.ranked([reward], 1, "u/", 0.5, risk_ctx=_ctx(rm))[0]
    assert r["grade"] == "높음" and "보상" in r["grade_reason"]
    mid = _p("aave-v3", "Arbitrum", "WBTC", base=0.5, tvl=5e7)
    r = az.ranked([mid], 1, "u/", 0.5, risk_ctx=_ctx(rm, {mid["pool"]: _series([0.5] * 30)}))[0]
    assert r["grade"] == "보통" and "규모 중간" in r["grade_reason"]
    vol = _p("aave-v3", "Arbitrum", "WBTC", base=0.5, tvl=2e8)
    r = az.ranked([vol], 1, "u/", 0.5,
                  risk_ctx=_ctx(rm, {vol["pool"]: _series([0.5] * 29 + [2.0])}))[0]
    assert r["grade"] == "높음" and "출렁임" in r["grade_reason"]


def test_krw_per_year(rm):
    p = _p("aave-v3", "Arbitrum", "WBTC", base=2.0, tvl=2e8)
    r = az.ranked([p], 1, "u/", 0.5, risk_ctx=_ctx(rm, krw=100_000_000))[0]
    assert r["btc_per_year"] == pytest.approx(0.02)
    assert r["krw_per_year"] == 2_000_000


def test_recommendations(multi_day_history, config):
    r = az.analyze(multi_day_history, config, AT,
                   {"btc_price": {"krw": 1e8, "usd": 7e4, "as_of_kst": "x", "source": "t"}})
    assert r["recommend"]["stable"]["pool"] == "p-a"          # TVL 1억 달러 이상 중 1위
    y = r["recommend"]["yield"]
    assert y is None or y["grade"] != "높음"
    assert r["btc_price"]["krw"] == 1e8



def test_volatility_is_relative_cv(rm):
    # 평균 3% ± 0.3%p 진동: 절댓값 범위 0.6%p지만 변동계수 0.1 → 높음 아님
    hi_apy = _p("aave-v3", "Arbitrum", "WBTC", base=3.0, tvl=2e8)
    r = az.ranked([hi_apy], 1, "u/", 0.5,
                  risk_ctx=_ctx(rm, {hi_apy["pool"]: _series([2.7, 3.3] * 15)}))[0]
    assert r["vol_cv"] == pytest.approx(0.1, abs=1e-4)
    assert r["vol_status"] == "mid" and r["grade"] == "보통"
    # 평균 0.5% 이상이고 변동계수 0.3 이상 → 높음
    swing = _p("aave-v3", "Arbitrum", "WBTC", base=1.0, tvl=2e8)
    r = az.ranked([swing], 1, "u/", 0.5,
                  risk_ctx=_ctx(rm, {swing["pool"]: _series([0.5, 1.5] * 15)}))[0]
    assert r["vol_status"] == "high" and r["grade"] == "높음"


def test_volatility_excluded_below_half_percent(rm):
    tiny = _p("aave-v3", "Arbitrum", "WBTC", base=0.2, tvl=2e8)
    r = az.ranked([tiny], 1, "u/", 0.5,
                  risk_ctx=_ctx(rm, {tiny["pool"]: _series([0.1, 0.3] * 15)}))[0]
    assert r["vol_cv"] == pytest.approx(0.5, abs=1e-4)      # 변동계수는 크지만
    assert r["vol_status"] == "excluded"                       # 평균 0.2% < 0.5% → 판정 제외
    assert r["grade"] == "낮음" and "판정 제외" in r["grade_reason"]


def _row(pool, grade, base, tvl):
    return {"pool": pool, "grade": grade, "apy_base": base, "tvl_usd": tvl}


def test_recommend_stable_excludes_high_and_steps_down():
    ranking = [_row("hi", "높음", 5.0, 5e8), _row("mid50", "보통", 2.0, 6e7),
               _row("low200", "낮음", 0.5, 2e8)]
    r = az.recommend(ranking, [1e8, 5e7])
    assert r["stable"]["pool"] == "low200" and r["stable_tvl_min"] == 1e8
    assert r["yield"]["pool"] == "mid50"                      # 높음 제외 1위
    r = az.recommend(ranking[:2], [1e8, 5e7])                 # 1억 달러 이상 낮음·보통 없음
    assert r["stable"]["pool"] == "mid50" and r["stable_tvl_min"] == 5e7
    assert "기준을 낮춤" in r["stable_note"]
    r = az.recommend([_row("hi", "높음", 5.0, 5e8), _row("s", "보통", 1.0, 1e7)], [1e8, 5e7])
    assert r["stable"] is None and "없음" in r["stable_note"]


def test_usd_kr():
    assert az.usd_kr(1e8) == "1억 달러" and az.usd_kr(5e7) == "5천만 달러"
