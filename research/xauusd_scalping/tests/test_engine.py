"""
Synthetic-data proof tests for the backtest engine (build spec's
<part_4_proof>). Every test uses a hand-constructed price series with a
known, independently-computable expected answer -- the harness is not
"done" until every one of these genuinely passes, and this file's own
docstrings show the by-hand arithmetic so the expected values aren't just
asserted, they're derivable.
"""

from datetime import UTC, datetime, timedelta

from research.xauusd_scalping.engine.backtest_engine import (
    Bar,
    BacktestEngine,
    Side,
    Signal,
    SizingConfig,
)
from research.xauusd_scalping.engine.cost_model import CostModel


def _bar(ts, o, h, low, c, vol=0.0):
    return Bar(ts=ts, open=o, high=h, low=low, close=c, volume=vol)


def _ts(hour: int, minute: int = 0) -> datetime:
    # 09:00 UTC = London session, avoids session/spread edge cases in tests
    # that aren't testing session logic.
    return datetime(2026, 1, 5, hour, minute, tzinfo=UTC)


class _EntersOnceStrategy:
    """Fires exactly one LONG signal on the very first bar it sees, then
    never again (the engine wouldn't ask again while a position is open
    anyway, but this also proves correct behaviour after the position
    closes with bars remaining)."""

    def __init__(self, stop_price: float, target_price: float):
        self.stop_price = stop_price
        self.target_price = target_price
        self.fired = False

    def on_bar(self, bar, ctx):
        if self.fired:
            return None
        self.fired = True
        return Signal(side=Side.LONG, stop_price=self.stop_price, target_price=self.target_price)


class _NeverEntersStrategy:
    def __init__(self):
        self.seen_ts: list[datetime] = []
        self.saw_future_bar = False

    def on_bar(self, bar, ctx):
        self.seen_ts.append(bar.ts)
        # Lookahead check: every bar ctx exposes must have ts <= the current
        # bar's ts. If this is ever violated, the engine leaked a future bar.
        history = ctx.bars(10_000)
        if any(b.ts > bar.ts for b in history):
            self.saw_future_bar = True
        if history[-1].ts != bar.ts:
            self.saw_future_bar = True
        return None


def test_deterministic_staircase_matches_hand_computed_pnl():
    """Entry at bar0.close=2000.00 (zero cost). Ascending staircase
    2000,2001,...,2009. Target=2005 hits exactly at bar index 5 (touch,
    not a gap through). Stop=1900 never hit.

    By hand: gross = 2005 - 2000 = 5 points. lots=1.0, point_value=1.0 ->
    gross_usd = $5.00. Zero commission -> net = $5.00 exactly.
    """
    bars = [_bar(_ts(9, i), 2000 + i, 2000 + i, 2000 + i, 2000 + i) for i in range(10)]
    strategy = _EntersOnceStrategy(stop_price=1900.0, target_price=2005.0)
    engine = BacktestEngine(cost_model=CostModel.zero(), sizing=SizingConfig(fixed_lots=1.0))

    result = engine.run(bars, strategy, initial_equity=5000.0)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_price == 2000.0
    assert trade.exit_price == 2005.0
    assert trade.pnl_usd == 5.0
    assert trade.exit_reason == "target"
    assert not trade.ambiguous_bar


def test_gap_through_stop_fills_at_gap_not_at_stop_price():
    """Entry at bar0.close=2000 (zero cost, stop=1990). bar1 GAPS: opens at
    1980 (already below the 1990 stop), high=1985, low=1975, close=1978.

    A resting stop order does not magically fill at 1990 when the market
    never traded there -- it fills at the first tradable price past it,
    which is the bar's open (1980). Asserting exit_price == 1980, not 1990,
    is exactly the spec's own required behaviour.
    """
    bars = [
        _bar(_ts(9, 0), 2000, 2000, 2000, 2000),
        _bar(_ts(9, 1), 1980, 1985, 1975, 1978),
    ]
    strategy = _EntersOnceStrategy(stop_price=1990.0, target_price=2100.0)
    engine = BacktestEngine(cost_model=CostModel.zero(), sizing=SizingConfig(fixed_lots=1.0))

    result = engine.run(bars, strategy)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == "stop"
    assert trade.exit_price == 1980.0  # the gap price, NOT 1990 (the stop level)
    assert trade.pnl_usd == 1980.0 - 2000.0  # -20.0, the real gapped loss


def test_no_lookahead_possible_through_the_strategy_context():
    """A strategy that tries to peek at future bars via ctx.bars() must
    never actually see one -- proves lookahead is architecturally
    impossible, not just avoided by convention."""
    bars = [_bar(_ts(9, i), 2000 + i, 2000 + i, 2000 + i, 2000 + i) for i in range(20)]
    strategy = _NeverEntersStrategy()
    engine = BacktestEngine(cost_model=CostModel.zero())

    engine.run(bars, strategy)

    assert strategy.saw_future_bar is False
    assert strategy.seen_ts == [b.ts for b in bars]  # saw every bar, in order, once each


def test_costed_vs_zero_cost_differs_by_exactly_the_modelled_cost():
    """Same bars, same strategy, two cost models. The P&L difference must
    equal EXACTLY the modelled cost -- computed independently here from
    the CostModel's own inputs, not just asserted to be "some" difference.
    """
    bars = [_bar(_ts(9, i), 2000 + i, 2000 + i, 2000 + i, 2000 + i) for i in range(10)]

    zero_strategy = _EntersOnceStrategy(stop_price=1900.0, target_price=2005.0)
    zero_engine = BacktestEngine(cost_model=CostModel.zero(), sizing=SizingConfig(fixed_lots=1.0))
    zero_result = zero_engine.run(bars, zero_strategy)

    real_cost = CostModel(commission_per_lot_per_side=3.50, entry_slippage_pts=3.0, exit_slippage_pts=5.0)
    real_strategy = _EntersOnceStrategy(stop_price=1900.0, target_price=2005.0)
    real_engine = BacktestEngine(cost_model=real_cost, sizing=SizingConfig(fixed_lots=1.0))
    real_result = real_engine.run(bars, real_strategy)

    assert len(zero_result.trades) == 1
    assert len(real_result.trades) == 1

    # Independently compute the expected cost from CostModel's own inputs,
    # using the same session/vol-bucket the engine actually used (London,
    # medium vol bucket -- see BacktestEngine.run's hardcoded VolBucket.MEDIUM
    # for entries/exits until a real ATR feed is wired into ctx).
    from research.xauusd_scalping.engine.cost_model import Session, VolBucket, session_for

    sess = session_for(_ts(9, 0))
    assert sess == Session.LONDON
    entry_cost_pts = real_cost.entry_cost_pts(sess, VolBucket.MEDIUM)
    exit_cost_pts = real_cost.exit_cost_pts(sess, VolBucket.MEDIUM)
    commission = real_cost.commission_usd(1.0)

    zero_trade = zero_result.trades[0]
    real_trade = real_result.trades[0]

    # LONG: entry costs push entry price UP, exit costs push exit price DOWN
    # -- both work against the trade, per _open_position/_close_position.
    expected_entry = zero_trade.entry_price + entry_cost_pts
    expected_exit = zero_trade.exit_price - exit_cost_pts
    expected_gross = expected_exit - expected_entry
    expected_net = expected_gross * 1.0 - commission

    assert abs(real_trade.entry_price - expected_entry) < 1e-9
    assert abs(real_trade.exit_price - expected_exit) < 1e-9
    assert abs(real_trade.pnl_usd - expected_net) < 1e-9

    diff = zero_trade.pnl_usd - real_trade.pnl_usd
    expected_diff = zero_trade.pnl_usd - expected_net
    assert abs(diff - expected_diff) < 1e-9


def test_daily_loss_cap_halts_new_entries_for_the_rest_of_the_day():
    """A strategy that always enters and always loses $10/trade should stop
    getting new fills once cumulative daily losses cross the $15 cap, and
    should resume on the next calendar day. Uses a long run of "drop 10"
    bars so the exact bar a stop-out lands on doesn't matter -- the engine
    is free to re-enter on the same bar a position just closed on (a
    legitimate simplification for M1 bars, not tested here), this test
    only cares about the CAP being enforced, not the precise trade count.
    """

    class _AlwaysLosesStrategy:
        def on_bar(self, bar, ctx):
            if ctx.has_open_position:
                return None
            return Signal(side=Side.LONG, stop_price=bar.close - 10, target_price=bar.close + 1000)

    from research.xauusd_scalping.engine.backtest_engine import RiskLimits

    day1 = datetime(2026, 1, 5, 9, tzinfo=UTC)
    day2 = datetime(2026, 1, 6, 9, tzinfo=UTC)
    bars = []
    # Day 1: a long run of bars, each one 10 points below the last close --
    # guarantees every open long stops out within a bar or two, however the
    # engine times same-bar re-entry, giving many chances to hit the cap.
    price = 2000.0
    ts = day1
    for _ in range(20):
        bars.append(_bar(ts, price, price, price - 10, price - 10))
        price -= 10
        ts += timedelta(minutes=1)
    # Day 2: a fresh day, one more entry+stop-out round -- a single -$10
    # loss on a NEW day, well under the $15 cap, proves the halt actually
    # reset rather than carrying over from day 1.
    bars.append(_bar(day2, price, price, price, price))
    bars.append(_bar(day2 + timedelta(minutes=1), price, price, price - 10, price - 10))

    strategy = _AlwaysLosesStrategy()
    engine = BacktestEngine(
        cost_model=CostModel.zero(),
        sizing=SizingConfig(fixed_lots=1.0),
        risk=RiskLimits(daily_loss_cap_usd=15.0),
    )

    result = engine.run(bars, strategy, initial_equity=5000.0)

    day1_trades = [t for t in result.trades if t.entry_ts.date().isoformat() == "2026-01-05"]
    day2_trades = [t for t in result.trades if t.entry_ts.date().isoformat() == "2026-01-06"]

    assert "2026-01-05" in result.halted_days
    # The halt check runs AFTER a trade closes, using the now-updated daily
    # P&L -- so it's the trade that PUSHES cumulative losses past the cap
    # that triggers the halt, not the one before it. Two -$10 losses
    # (-$20 cumulative) cross the -$15 cap; a third never gets a chance.
    assert len(day1_trades) == 2
    assert sum(t.pnl_usd for t in day1_trades) == -20.0
    # Day 2 must still get its own fresh trade -- proves the halt is a
    # daily circuit breaker, not permanent for the rest of the backtest.
    assert len(day2_trades) >= 1


def test_consecutive_loss_halt_resets_on_a_new_day():
    """Mirrors test_daily_loss_cap_halts_new_entries_for_the_rest_of_the_day
    but for `consecutive_loss_halt`. Found 2026-09-22 while running P3's
    real backtests: EVERY strategy showed a near-identical, tiny (2-3)
    trade count across a 20k-bar dataset regardless of the strategy's own
    logic -- the tell that a shared halt was firing almost immediately and
    never releasing. Root cause: `consecutive_losses` was reset nowhere,
    so once a strategy hit the threshold ANYWHERE in the run, every
    subsequent day was permanently halted (unlike its sibling
    `daily_loss_cap_usd`, which is documented and tested above as a
    per-day reset). Fixed by resetting `consecutive_losses = 0` on day
    rollover, matching the other risk limits' daily-circuit-breaker
    semantics.
    """

    class _AlwaysLosesStrategy:
        def on_bar(self, bar, ctx):
            if ctx.has_open_position:
                return None
            return Signal(side=Side.LONG, stop_price=bar.close - 10, target_price=bar.close + 1000)

    from research.xauusd_scalping.engine.backtest_engine import RiskLimits

    day1 = datetime(2026, 1, 5, 9, tzinfo=UTC)
    day2 = datetime(2026, 1, 6, 9, tzinfo=UTC)
    bars = []
    price = 2000.0
    ts = day1
    for _ in range(20):
        bars.append(_bar(ts, price, price, price - 10, price - 10))
        price -= 10
        ts += timedelta(minutes=1)
    bars.append(_bar(day2, price, price, price, price))
    bars.append(_bar(day2 + timedelta(minutes=1), price, price, price - 10, price - 10))

    strategy = _AlwaysLosesStrategy()
    engine = BacktestEngine(
        cost_model=CostModel.zero(),
        sizing=SizingConfig(fixed_lots=1.0),
        risk=RiskLimits(consecutive_loss_halt=2),
    )

    result = engine.run(bars, strategy, initial_equity=5000.0)

    day1_trades = [t for t in result.trades if t.entry_ts.date().isoformat() == "2026-01-05"]
    day2_trades = [t for t in result.trades if t.entry_ts.date().isoformat() == "2026-01-06"]

    assert "2026-01-05" in result.halted_days
    assert len(day1_trades) == 2  # two straight losses trips the halt
    # Day 2 must get its own fresh attempt -- if this fails, the halt is
    # leaking across days again.
    assert len(day2_trades) >= 1
    assert "2026-01-06" not in result.halted_days
    assert all(t.pnl_usd == -10.0 for t in day1_trades)
    # Day 2 is a fresh day -- the halt must not carry over.
    assert len(day2_trades) == 1
    assert day2_trades[0].pnl_usd == -10.0
