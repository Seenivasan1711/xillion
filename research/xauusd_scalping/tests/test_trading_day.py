"""Trading-day boundary, the S04/S11 sliding-window cache bug, and per-bar
broker spread -- all found/added 2026-09-25 (12_mt5_broker_data_rerun.md)."""

from datetime import UTC, date, datetime, timedelta

import pytest

from research.xauusd_scalping.engine.backtest_engine import Bar, BacktestEngine, StrategyContext
from research.xauusd_scalping.engine.cost_model import CostModel, Session, VolBucket, trading_date
from research.xauusd_scalping.strategies._common import DailyBarCache, daily_bars_from_m1, todays_start


def _bars(start: datetime, n: int) -> list[Bar]:
    return [Bar(ts=start + timedelta(minutes=i), open=100 + i, high=101 + i, low=99 + i, close=100 + i)
            for i in range(n)]


def test_trading_day_rolls_at_1700_new_york():
    # winter: 17:00 EST = 22:00 UTC; summer: 17:00 EDT = 21:00 UTC
    assert trading_date(datetime(2026, 1, 15, 21, 59, tzinfo=UTC)) == date(2026, 1, 15)
    assert trading_date(datetime(2026, 1, 15, 22, 0, tzinfo=UTC)) == date(2026, 1, 16)
    assert trading_date(datetime(2026, 7, 15, 20, 59, tzinfo=UTC)) == date(2026, 7, 15)
    assert trading_date(datetime(2026, 7, 15, 21, 0, tzinfo=UTC)) == date(2026, 7, 16)


def test_sunday_reopen_belongs_to_monday():
    assert trading_date(datetime(2026, 1, 18, 23, 0, tzinfo=UTC)) == date(2026, 1, 19)  # Sunday 23:00 UTC


def test_todays_start_is_right_on_a_sliding_window():
    # The S04/S11 bug: an index cached from an earlier ctx.bars(N) slice
    # is wrong on a later slice. todays_start must be computed per slice.
    bars = _bars(datetime(2026, 1, 14, 0, 0, tzinfo=UTC), 3 * 1440)
    history = []
    ctx = StrategyContext(history=history, has_open_position=False)
    for b in bars:
        history.append(b)
        window = ctx.bars(2000)
        split = todays_start(window)
        today = trading_date(window[-1].ts)
        assert all(trading_date(x.ts) == today for x in window[split:])
        assert split == 0 or trading_date(window[split - 1].ts) != today


def test_daily_cache_today_matches_a_full_resample():
    bars = _bars(datetime(2026, 1, 14, 0, 0, tzinfo=UTC), 4 * 1440)
    cache = DailyBarCache()
    history = []
    ctx = StrategyContext(history=history, has_open_position=False)
    for b in bars:
        history.append(b)
        window = ctx.bars(3000)
        got, want = cache.daily(window), daily_bars_from_m1(window)
        # Every day after the window's oldest (partial) one is identical; the
        # cache may additionally still hold a day the window has slid past
        # since the day began -- harmless for S02/S04, which read only the
        # trailing 10 days of a >=17-day window.
        assert got[-1] == want[-1]
        if len(want) > 1:
            assert got[-(len(want) - 1):] == want[1:]


def test_bar_spread_used_only_when_enabled():
    table = CostModel()
    broker = CostModel(use_bar_spread=True)
    t = table.spread_pts(Session.NY, VolBucket.MEDIUM)
    assert table.spread_pts(Session.NY, VolBucket.MEDIUM, 12.0) == t
    assert broker.spread_pts(Session.NY, VolBucket.MEDIUM, 12.0) == 12.0
    assert broker.spread_pts(Session.NY, VolBucket.MEDIUM, None) == t  # no reading -> table
    assert broker.entry_cost_pts(Session.NY, VolBucket.MEDIUM, False, 12.0) == 6.0 + broker.entry_slippage_pts


def test_vol_buckets_is_one_per_bar():
    bars = _bars(datetime(2026, 1, 14, tzinfo=UTC), 800)
    assert len(BacktestEngine(CostModel()).vol_buckets(bars)) == 800


def test_s08_drops_a_setup_that_pulled_back_too_far_to_ever_fire():
    # Pullback of 45% (> max 38.2, < old 61.8 invalidation): the setup can
    # never fire again, and must not sit in the state machine blocking new
    # BOS setups (the 2026-09-25 "zero-trade months" bug).
    from research.xauusd_scalping.signals.price_action import Direction
    from research.xauusd_scalping.strategies.s08_bos_pullback_continuation import (
        BosPullbackContinuationStrategy, _Pending,
    )

    s = BosPullbackContinuationStrategy()
    s._pending = _Pending(direction=Direction.UP, impulse_leg=10.0, bos_close=110.0,
                          extreme_price=110.0, extreme_bar_bound=111.0)
    bars = _bars(datetime(2026, 1, 14, tzinfo=UTC), 40)
    deep = Bar(ts=bars[-1].ts + timedelta(minutes=1), open=106, high=106.5, low=105.5, close=106)
    ctx = StrategyContext(history=bars + [deep], has_open_position=False)
    s.on_bar(deep, ctx)
    assert s._pending is None or s._pending.bos_close != 110.0


def test_swap_counts_rollovers_and_triples_wednesday():
    c = CostModel(charge_swap=True)
    mon = datetime(2026, 1, 12, 15, 0, tzinfo=UTC)  # Monday, trading day Mon
    # Mon -> Tue: 1 night; Mon -> Thu: Mon+Tue+Wed(x3) = 5; Fri -> Mon: 1 (weekend is in Wed's x3)
    assert c.swap_usd(True, mon, mon + timedelta(days=1), 1.0, 1.0) == -93.17
    assert c.swap_usd(True, mon, mon + timedelta(days=3), 1.0, 1.0) == pytest.approx(-93.17 * 5)
    fri = datetime(2026, 1, 16, 15, 0, tzinfo=UTC)
    assert c.swap_usd(False, fri, fri + timedelta(days=3), 0.1, 1.0) == pytest.approx(2.168)
    assert c.swap_usd(True, mon, mon + timedelta(hours=2), 1.0, 1.0) == 0.0  # intraday
    assert CostModel().swap_usd(True, mon, mon + timedelta(days=3), 1.0, 1.0) == 0.0  # off by default


def test_fixed_risk_sizing_rounds_down_to_lot_step_with_a_minimum():
    from research.xauusd_scalping.engine.backtest_engine import SizingConfig

    e = BacktestEngine(CostModel(), sizing=SizingConfig(mode="fixed_risk_usd", risk_usd=25.0, lot_step=0.01))
    assert e._lots_for(5000, 4000.0, 3997.0) == pytest.approx(0.08)  # $3 stop: 25/300 = 0.083 -> 0.08
    assert e._lots_for(5000, 4000.0, 3970.0) == pytest.approx(0.01)  # $30 stop: 0.0083 -> min 0.01


def test_flat_before_weekend_cutoff_is_friday_1645_new_york():
    from research.xauusd_scalping.engine.backtest_engine import RiskLimits

    e = BacktestEngine(CostModel(), risk=RiskLimits(flat_before_weekend=True))
    assert not e._past_friday_cutoff(datetime(2026, 1, 16, 21, 40, tzinfo=UTC))  # 16:40 EST
    assert e._past_friday_cutoff(datetime(2026, 1, 16, 21, 45, tzinfo=UTC))
    assert e._past_friday_cutoff(datetime(2026, 7, 17, 20, 45, tzinfo=UTC))  # 16:45 EDT
    assert not BacktestEngine(CostModel())._past_friday_cutoff(datetime(2026, 1, 16, 21, 45, tzinfo=UTC))


def test_make_engine_builds_in_default_and_realistic_modes():
    # Regression: a frozen-dataclass assignment in make_engine crashed every
    # run started after it (2026-09-25) and no unit test called make_engine.
    # Subprocess: run_backtests puts research/ on sys.path, whose
    # `strategies` package would shadow the app's own in this test session.
    import os
    import subprocess
    import sys
    from pathlib import Path

    here = Path(__file__).resolve().parent.parent
    code = (
        "import run_backtests as rb\n"
        "e = rb.make_engine(); assert e.sizing.mode == 'fixed_lot' and not e.cost_model.charge_swap\n"
        "rb.REALISTIC = True\n"
        "e = rb.make_engine(); assert e.sizing.mode == 'fixed_risk_usd' and e.cost_model.charge_swap\n"
        "assert e.risk.flat_before_weekend\n"
    )
    env = {**os.environ, "RESEARCH_DATA_SOURCE": "dukascopy", "RESEARCH_TIMEFRAME": "M1"}
    r = subprocess.run([sys.executable, "-c", code], cwd=here, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
