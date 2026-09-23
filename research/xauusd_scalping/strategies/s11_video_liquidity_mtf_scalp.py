"""
S11 -- video-sourced candidate (05_consolidated_findings_and_strategy_
request.md section 8.1). Multi-timeframe liquidity-sweep + market-
structure scalp: 1H structure sets bias, a 15m order block (demand/supply
zone) is the point of interest (POI), a liquidity sweep of a nearby
unswept swing extreme after POI mitigation is the entry trigger, one
same-direction confirmation candle before entry, stop beyond the sweep
extreme, target the nearest opposing 15m swing point.

Composes existing primitives only -- no new detectors:
PriceActionSignals.break_of_structure (1H bias, 15m structure),
.order_block_zone (the 15m POI), .liquidity_sweep (the entry trigger),
._find_swing_points (the opposing-swing target). Multi-timeframe bars via
timeframe_experiment.resample_bars, imported not duplicated.

Ambiguities resolved when turning the video transcript into precise
rules (flagged per this project's own "don't silently invent a rule"
practice):
1. The video treats 1H/15m alignment as a SOFT filter (its own second
   example trade explicitly ignores it). This implementation makes it a
   HARD filter -- no trade unless both timeframes agree -- for a first,
   unambiguous, mechanical version. A soft-filter variant (trade
   misaligned setups at reduced size/confidence) is a plausible S11b, not
   built here.
2. The video offers an "aggressive" (sweep + one confirmation candle) and
   a "conservative" (sweep + a further internal market-shift + pullback)
   entry variant. Only the aggressive variant is implemented here -- the
   conservative variant requires a second, even-lower-timeframe structure
   check the video doesn't fully specify the parameters for, and building
   a plausible-but-unspecified version of it risked exactly the "silently
   invent a rule" failure mode this project avoids elsewhere.
3. The video's own live execution shows the trader REMOVING the stop-loss
   mid-trade on discretion in one of its two example trades -- explicitly
   NOT implemented here (see the consolidated doc's section 8.1 for why:
   this project's own real MT5 trade log shows exactly this behavior
   producing the largest real losses in a real account).
4. "Nearby unswept swing extreme" (the liquidity-sweep target) is resolved
   as the most recent swing low/high (opposite the bias direction's
   'floor', i.e. the nearest swing LOW for a bullish setup) found in the
   trailing `swing_search_bars` M1 bars once the POI is mitigated -- the
   video doesn't give an exact "how far back to look" rule, so this is a
   deliberate, documented default, not a value chosen to fit backtest
   results.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.backtest_engine import Bar, Side, Signal
from signals.indicators import IndicatorSignals
from signals.price_action import Direction, PriceActionSignals
from signals.risk_floor import apply_floor

from timeframe_experiment import resample_bars

pa = PriceActionSignals()
ind = IndicatorSignals()


@dataclass
class Params:
    min_sl_pts: float = 3.0
    sl_buffer_pts: float = 0.5
    h1_bars_window: int = 20000  # ~13.9 trading days of M1 -> ample 1H history
    m15_bars_window: int = 20000
    swing_lookback: int = 3
    decisive_atr_mult: float = 0.3
    swing_search_bars: int = 300  # trailing M1 bars scanned for the sweep target once POI is mitigated
    stale_pending_bars: int = 500  # give up on a mitigated-but-unswept POI after this many bars


@dataclass
class _Pending:
    direction: Direction
    swept_level: float
    bars_since: int = 0


class VideoLiquidityMtfScalpStrategy:
    name = "S11 Video Multi-Timeframe Liquidity + Market Structure Scalp"

    def __init__(self, params: Params | None = None) -> None:
        self.p = params or Params()
        self._h1_cached_date = None
        self._h1_cached_historical: list[Bar] = []
        self._h1_today_split = 0
        self._m15_cached_date = None
        self._m15_cached_historical: list[Bar] = []
        self._m15_today_split = 0
        self._pending: _Pending | None = None

    def _cached_resample(self, bars: list[Bar], interval_minutes: int, state_prefix: str) -> list[Bar]:
        """Same per-calendar-day caching pattern as s04_wyckoff_spring_
        upthrust.py -- resampling a large M1 window on every single bar was
        a real, found performance bug there (~40min/run); reused here
        rather than rediscovering it."""
        today = bars[-1].ts.date()
        cached_date_attr = f"_{state_prefix}_cached_date"
        cached_hist_attr = f"_{state_prefix}_cached_historical"
        split_attr = f"_{state_prefix}_today_split"

        if getattr(self, cached_date_attr) != today:
            split = 0
            for i in range(len(bars) - 1, -1, -1):
                if bars[i].ts.date() != today:
                    split = i + 1
                    break
            setattr(self, cached_hist_attr, resample_bars(bars[:split], interval_minutes))
            setattr(self, split_attr, split)
            setattr(self, cached_date_attr, today)

        split = getattr(self, split_attr)
        todays_bars = bars[split:]
        today_resampled = resample_bars(todays_bars, interval_minutes) if todays_bars else []
        return getattr(self, cached_hist_attr) + today_resampled

    def on_bar(self, bar: Bar, ctx) -> Signal | None:
        if ctx.has_open_position:
            return None

        h1_bars = ctx.bars(self.p.h1_bars_window)
        if len(h1_bars) < 100:
            return None
        h1_resampled = self._cached_resample(h1_bars, 60, "h1")
        if len(h1_resampled) < 30:
            return None
        h1_atr = ind.atr(h1_resampled, period=14)
        if h1_atr <= 0:
            return None
        h1_bos = pa.break_of_structure(
            h1_resampled, atr_value=h1_atr, swing_lookback=self.p.swing_lookback,
            decisive_atr_mult=self.p.decisive_atr_mult,
        )
        if not h1_bos.fired:
            self._pending = None
            return None
        bias = h1_bos.direction

        m15_bars = ctx.bars(self.p.m15_bars_window)
        m15_resampled = self._cached_resample(m15_bars, 15, "m15")
        if len(m15_resampled) < 30:
            return None
        m15_atr = ind.atr(m15_resampled, period=14)
        if m15_atr <= 0:
            return None
        m15_bos = pa.break_of_structure(
            m15_resampled, atr_value=m15_atr, swing_lookback=self.p.swing_lookback,
            decisive_atr_mult=self.p.decisive_atr_mult,
        )
        # Ambiguity #1: hard alignment filter, not the video's soft one.
        if not m15_bos.fired or m15_bos.direction != bias:
            self._pending = None
            return None

        # A pending sweep-watch, once set, must NOT depend on the POI still
        # being touched on the current bar -- price necessarily moves away
        # from the POI zone to go sweep a different nearby level, so
        # gating this whole branch on `poi.fired` (true only while price
        # is literally inside the zone) meant the sweep-watch code could
        # never actually run once set -- found via a 0-trade smoke test,
        # same bug class as S02's original zero-signal issue earlier this
        # session (two conditions required simultaneously that structurally
        # can't both hold at once).
        if self._pending is not None:
            self._pending.bars_since += 1
            if self._pending.bars_since > self.p.stale_pending_bars:
                self._pending = None
            else:
                bars = ctx.bars(3)
                if len(bars) < 2:
                    return None
                sweep = pa.liquidity_sweep(
                    bars, level_price=self._pending.swept_level, level_is_high=(bias == Direction.DOWN)
                )
                if not sweep.fired:
                    return None
                last = bars[-1]
                is_bull_candle = last.close > last.open
                if bias == Direction.UP and not is_bull_candle:
                    return None
                if bias == Direction.DOWN and is_bull_candle:
                    return None
                return self._fire_entry(bar, bias, sweep.extreme_price, m15_resampled)

        poi = pa.order_block_zone(m15_resampled, m15_bos)
        if not poi.fired:
            # POI identified but not yet mitigated -- keep waiting, no pending sweep state yet.
            return None

        # POI just mitigated this bar -- look for a nearby unswept swing extreme
        # to watch for the liquidity sweep (ambiguity #4).
        search_window = ctx.bars(self.p.swing_search_bars)
        swings = pa._find_swing_points(search_window, self.p.swing_lookback)
        want_high = bias == Direction.DOWN  # bearish bias -- sweep a recent swing HIGH
        candidates = [s for s in swings if s.is_high == want_high]
        if not candidates:
            return None
        target = max(candidates, key=lambda s: s.index)  # most recent
        self._pending = _Pending(direction=bias, swept_level=target.price)
        return None

    def _fire_entry(self, bar: Bar, direction: Direction, sweep_extreme: float, m15_resampled: list[Bar]) -> Signal:
        self._pending = None
        entry = bar.close
        m15_swings = pa._find_swing_points(m15_resampled, self.p.swing_lookback)
        if direction == Direction.UP:
            side = Side.LONG
            stop = min(sweep_extreme - self.p.sl_buffer_pts, entry - self.p.min_sl_pts)
            opposing = [s for s in m15_swings if s.is_high and s.price > entry]
            target = min((s.price for s in opposing), default=entry + 2 * (entry - stop))
        else:
            side = Side.SHORT
            stop = max(sweep_extreme + self.p.sl_buffer_pts, entry + self.p.min_sl_pts)
            opposing = [s for s in m15_swings if not s.is_high and s.price < entry]
            target = max((s.price for s in opposing), default=entry - 2 * (stop - entry))
        reason = (
            f"1H bias {direction.value}, 15m POI mitigated, swept {sweep_extreme:.2f}, "
            f"confirmation candle closed, target {target:.2f}"
        )
        stop, target = apply_floor(entry, stop, target, side)
        return Signal(side=side, stop_price=stop, target_price=target, reason=reason)

