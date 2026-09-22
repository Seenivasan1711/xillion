"""
Signal toolkit correctness proofs -- synthetic bars with hand-computed
expected outputs, same discipline as tests/test_engine.py. Covers at least
liquidity sweep, displacement, FVG, and one indicator per the build
directive, plus BOS/CHoCH and the confidence composer since every strategy
module leans on them.
"""

from datetime import UTC, datetime, timedelta

from engine.backtest_engine import Bar
from signals.confidence import ConfidenceComponent, ConfidenceScorer
from signals.indicators import IndicatorSignals
from signals.price_action import Direction, PriceActionSignals

pa = PriceActionSignals()
ind = IndicatorSignals()


def _bar(o: float, h: float, low: float, c: float, ts_offset_min: int = 0, volume: float = 1.0) -> Bar:
    return Bar(
        ts=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=ts_offset_min),
        open=o,
        high=h,
        low=low,
        close=c,
        volume=volume,
    )


# ── Liquidity sweep ──────────────────────────────────────────────────────────


def test_liquidity_sweep_fires_and_detects_reclaim():
    # Level (a prior high) at 2650. Bar pokes to 2655 then closes back at 2648 -- a swept + reclaimed high.
    bars = [_bar(2649, 2655, 2647, 2648, ts_offset_min=i) for i in range(3)]
    result = pa.liquidity_sweep(bars, level_price=2650.0, level_is_high=True)
    assert result.fired is True
    assert result.extreme_price == 2655
    assert result.reclaimed is True
    assert result.direction == Direction.UP


def test_liquidity_sweep_does_not_fire_when_level_untouched():
    bars = [_bar(2640, 2645, 2635, 2642, ts_offset_min=i) for i in range(3)]
    result = pa.liquidity_sweep(bars, level_price=2650.0, level_is_high=True)
    assert result.fired is False


def test_liquidity_sweep_low_side():
    # Level (a prior low) at 2600. Bar pokes down to 2595, closes back at 2603.
    bars = [_bar(2602, 2604, 2595, 2603, ts_offset_min=i) for i in range(3)]
    result = pa.liquidity_sweep(bars, level_price=2600.0, level_is_high=False)
    assert result.fired is True
    assert result.extreme_price == 2595
    assert result.reclaimed is True
    assert result.direction == Direction.DOWN


# ── Displacement candle ──────────────────────────────────────────────────────


def test_displacement_candle_fires_on_a_real_impulse():
    # 20 quiet bars with a ~1.0 body, then one bar with a 2.0 body (2.0x avg)
    # closing at the very top of its own range (100% close position).
    quiet = [_bar(2600 + i * 0.01, 2600.5 + i * 0.01, 2599.5 + i * 0.01, 2601 + i * 0.01, ts_offset_min=i) for i in range(20)]
    impulse = _bar(2601, 2603, 2600.9, 2603, ts_offset_min=20)  # body=2.0, range=2.1, closes at the high
    result = pa.displacement_candle(quiet + [impulse], avg_body_lookback=20, body_mult=1.5, close_pct_threshold=25.0)
    assert result.fired is True
    assert result.direction == Direction.UP
    assert result.body_size == 2.0


def test_displacement_candle_does_not_fire_on_an_ordinary_bar():
    quiet = [_bar(2600 + i * 0.01, 2600.5 + i * 0.01, 2599.5 + i * 0.01, 2601 + i * 0.01, ts_offset_min=i) for i in range(20)]
    ordinary = _bar(2601, 2601.5, 2600.5, 2601.1, ts_offset_min=20)  # small body, same size as the quiet run
    result = pa.displacement_candle(quiet + [ordinary])
    assert result.fired is False


# ── Fair value gap ───────────────────────────────────────────────────────────


def test_fair_value_gap_detects_a_real_bullish_gap():
    # c1.high=2600, c3.low=2605 -- a clean bullish FVG from 2600 to 2605.
    c1 = _bar(2598, 2600, 2597, 2599, ts_offset_min=0)
    c2 = _bar(2599, 2604, 2599, 2603, ts_offset_min=1)  # the displacement candle
    c3 = _bar(2605, 2608, 2605, 2607, ts_offset_min=2)
    result = pa.fair_value_gap([c1, c2, c3])
    assert result.fired is True
    assert result.direction == Direction.UP
    assert result.gap_low == 2600
    assert result.gap_high == 2605


def test_fair_value_gap_none_when_candles_overlap():
    c1 = _bar(2598, 2602, 2597, 2600, ts_offset_min=0)
    c2 = _bar(2600, 2603, 2599, 2601, ts_offset_min=1)
    c3 = _bar(2601, 2604, 2600, 2602, ts_offset_min=2)  # overlaps c1's range -- no gap
    result = pa.fair_value_gap([c1, c2, c3])
    assert result.fired is False


def test_fvg_retest_true_when_price_touches_back_into_the_gap():
    c1 = _bar(2598, 2600, 2597, 2599, ts_offset_min=0)
    c2 = _bar(2599, 2604, 2599, 2603, ts_offset_min=1)
    c3 = _bar(2605, 2608, 2605, 2607, ts_offset_min=2)
    fvg = pa.fair_value_gap([c1, c2, c3])
    retest_bar = _bar(2607, 2607, 2601, 2603, ts_offset_min=3)  # dips back into 2600-2605
    assert pa.fvg_retest([c1, c2, c3, retest_bar], fvg) is True


def test_fvg_retest_false_when_price_never_returns():
    c1 = _bar(2598, 2600, 2597, 2599, ts_offset_min=0)
    c2 = _bar(2599, 2604, 2599, 2603, ts_offset_min=1)
    c3 = _bar(2605, 2608, 2605, 2607, ts_offset_min=2)
    fvg = pa.fair_value_gap([c1, c2, c3])
    away_bar = _bar(2609, 2611, 2608, 2610, ts_offset_min=3)
    assert pa.fvg_retest([c1, c2, c3, away_bar], fvg) is False


# ── NR7 / inside bar ──────────────────────────────────────────────────────────


def test_nr7_inside_bar_fires_on_the_narrowest_contained_bar():
    # nr7_inside_bar needs nr_lookback+1 bars total (the window itself, plus
    # one more to compare the "inside bar" containment against) -- 8 bars
    # for nr_lookback=7, not 7.
    wide = [_bar(2600, 2600 + 2 - i * 0.1, 2600 - 2 + i * 0.1, 2600, ts_offset_min=i) for i in range(7)]
    # last bar: range 0.4, fully inside the prior bar's range (prior range was ~0.7 wide at that point)
    narrow = _bar(2600, 2600.2, 2599.8, 2600.1, ts_offset_min=7)
    result = pa.nr7_inside_bar(wide + [narrow], nr_lookback=7)
    assert result.fired is True
    assert result.is_inside_bar is True


# ── Break of structure / CHoCH ───────────────────────────────────────────────


def test_break_of_structure_fires_on_a_decisive_close_beyond_a_swing_high():
    # Build a clean swing high at bar index 4 -- each bar's .high is
    # price+0.5, so the swing point's confirmed price is 2610.5 (the bar's
    # actual high), not the bar's close (2610).
    bars = []
    prices = [2600, 2602, 2605, 2608, 2610, 2607, 2604, 2601]  # swing high at index 4, .high = 2610.5
    for i, p in enumerate(prices):
        bars.append(_bar(p, p + 0.5, p - 0.5, p, ts_offset_min=i))
    # Pad more bars so the swing-point fractal window (lookback=3 each side) can confirm index 4.
    tail = [2599, 2598, 2597, 2596]
    for i, p in enumerate(tail):
        bars.append(_bar(p, p + 0.5, p - 0.5, p, ts_offset_min=len(prices) + i))
    breakout = _bar(2611, 2615, 2611, 2614, ts_offset_min=len(bars))  # decisive close above 2610.5
    result = pa.break_of_structure(bars + [breakout], atr_value=1.0, swing_lookback=3, decisive_atr_mult=0.3)
    assert result.fired is True
    assert result.direction == Direction.UP
    assert result.swing_broken_price == 2610.5


def test_break_of_structure_does_not_fire_without_a_confirmed_swing():
    bars = [_bar(2600 + i * 0.1, 2600.5 + i * 0.1, 2599.5 + i * 0.1, 2600 + i * 0.1, ts_offset_min=i) for i in range(5)]
    result = pa.break_of_structure(bars, atr_value=1.0)
    assert result.fired is False


# ── Indicators ───────────────────────────────────────────────────────────────


def test_vwap_sigma_bands_hand_computed():
    # Two bars, equal volume: typical prices 100 and 102 -> VWAP = 101 exactly.
    b1 = _bar(100, 100, 100, 100, ts_offset_min=0, volume=1.0)
    b2 = _bar(102, 102, 102, 102, ts_offset_min=1, volume=1.0)
    result = ind.vwap_sigma_bands([b1, b2])
    assert result.vwap == 101.0


def test_rsi_is_100_when_every_move_is_a_gain():
    bars = [_bar(2600 + i, 2600 + i, 2600 + i, 2600 + i, ts_offset_min=i) for i in range(20)]
    assert ind.rsi(bars, period=14) == 100.0


def test_rsi_is_neutral_default_with_insufficient_history():
    bars = [_bar(2600, 2600, 2600, 2600, ts_offset_min=0)]
    assert ind.rsi(bars, period=14) == 50.0


def test_ema_matches_hand_computed_two_step_sequence():
    # period=2: seed = avg(close[0], close[1]); then one more EMA step.
    bars = [_bar(100, 100, 100, 100, ts_offset_min=0), _bar(102, 102, 102, 102, ts_offset_min=1), _bar(104, 104, 104, 104, ts_offset_min=2)]
    k = 2.0 / 3.0
    seed = (100 + 102) / 2  # 101
    expected = 104 * k + seed * (1 - k)
    assert abs(ind.ema(bars, period=2) - expected) < 1e-9


# ── Confidence composer ──────────────────────────────────────────────────────


def test_confidence_scorer_weighted_average_hand_computed():
    components = [
        ConfidenceComponent(name="a", value_0_100=100.0, weight=1.0),
        ConfidenceComponent(name="b", value_0_100=0.0, weight=1.0),
        ConfidenceComponent(name="c", value_0_100=50.0, weight=2.0),
    ]
    # (100*1 + 0*1 + 50*2) / (1+1+2) = 200/4 = 50
    result = ConfidenceScorer().score(components)
    assert result.score == 50


def test_confidence_scorer_empty_input_is_neutral_not_zero():
    result = ConfidenceScorer().score([])
    assert result.score == 50
    assert "no confidence components" in result.reasons[0]


def test_confidence_scorer_clamps_to_0_100_range():
    components = [ConfidenceComponent(name="a", value_0_100=500.0, weight=1.0)]
    result = ConfidenceScorer().score(components)
    assert result.score == 100
