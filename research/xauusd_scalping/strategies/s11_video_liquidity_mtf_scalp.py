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

## v2 restructure (2026-09-24) -- read this before changing anything

v1 of this strategy produced 1 trade in 6.5 months. That was an encoding
bug, not a market finding, and it was diagnosed by instrumenting every
gate and counting survivors (see 03d_s11_video_strategy_result.md and
s11_funnel.py): v1 required, ON THE SAME BAR, a 15m break-of-structure to
be *firing* AND price to be *simultaneously inside the order block that
caused that break*. Those are near-mutually-exclusive by construction --
a BOS fires precisely because price moved decisively AWAY from that zone.
Only 82 of 8,767 qualifying bars (0.9%) ever cleared it, and only 1 of
those 82 became a trade.

The video describes a SEQUENCE UNFOLDING OVER TIME, not a conjunction of
simultaneous conditions:
    structure shifts (a STATE that persists until invalidated)
      -> price LATER pulls back into the marked zone
        -> THEN a liquidity sweep of a nearby level
          -> THEN a confirmation candle
            -> entry

v2 encodes exactly that as an explicit state machine (IDLE -> ARMED ->
MITIGATED -> entry). The key correctness fix: **bias and the marked zone
are persistent state**, updated when a BOS fires and then remembered,
rather than re-required to be firing on every subsequent bar. This is a
correctness fix, not a loosening -- "the structure has officially shifted
bullish, now look for longs" is a state in the source material, and v1
encoded it as an instantaneous event.

Ambiguities resolved when turning the video transcript into precise
rules (flagged per this project's own "don't silently invent a rule"
practice):
1. The video treats 1H/15m alignment as a SOFT filter (its own second
   example trade explicitly ignores it). This implementation makes it a
   HARD filter -- no trade unless both timeframes' most recent structural
   bias agrees -- for a first, unambiguous, mechanical version. A
   soft-filter variant (trade misaligned setups at reduced size) is a
   plausible S11b, not built here.
2. The video offers an "aggressive" (sweep + one confirmation candle) and
   a "conservative" (sweep + a further internal market-shift + pullback)
   entry variant. Only the aggressive variant is implemented -- the
   conservative variant needs a second, even-lower-timeframe structure
   check whose parameters the video never specifies, and inventing them
   would be exactly the "silently invent a rule" failure this project
   avoids.
3. The video's own live execution shows the trader REMOVING the stop-loss
   mid-trade on discretion in one of its two example trades -- explicitly
   NOT implemented (see the consolidated doc's section 8.1: this project's
   own real MT5 trade log shows exactly that behavior producing the
   largest real losses in a real account).
4. "Nearby unswept swing extreme" (the sweep target) is resolved as the
   most recent swing low (bullish bias) or high (bearish bias) in the
   trailing `swing_search_bars` M1 bars at the moment the zone is
   mitigated. The video gives no explicit lookback, so this is a
   documented default.
5. NEW in v2 -- the video never says how long a marked zone stays valid
   while waiting for price to return to it, nor how long to wait for a
   sweep after mitigation. Both need *some* finite value or the state
   machine leaks stale setups forever. Defaults below are stated in
   round, human-plausible trading terms (roughly a session, roughly an
   hour) rather than swept for a best-performing value -- they have NOT
   been tuned against backtest results, and changing them to chase P&L
   would violate this project's honesty clause.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.backtest_engine import Bar, Side, Signal
from signals.indicators import IndicatorSignals
from signals.price_action import Direction, PriceActionSignals

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
    swing_search_bars: int = 300  # trailing M1 bars scanned for the sweep target at mitigation
    # Ambiguity #5 -- finite lifetimes the video doesn't specify. Stated in
    # round trading terms, not swept for a best value.
    max_arm_bars: int = 1440  # ~1 trading day for price to return to a marked zone
    max_wait_after_mitigation_bars: int = 60  # ~1 hour for a sweep to follow mitigation


@dataclass
class _Setup:
    """One armed setup, walked through the sequence in on_bar."""

    direction: Direction
    zone_low: float
    zone_high: float
    bars_armed: int = 0
    mitigated: bool = False
    bars_since_mitigation: int = 0
    sweep_level: float | None = None


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
        # Persistent structural bias per timeframe -- the v2 correctness fix.
        # Updated when a BOS fires, then REMEMBERED; never re-required to be
        # firing on a later bar.
        self._h1_bias: Direction | None = None
        self._m15_bias: Direction | None = None
        self._setup: _Setup | None = None

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
        m15_resampled = self._cached_resample(ctx.bars(self.p.m15_bars_window), 15, "m15")
        if len(m15_resampled) < 30:
            return None

        # ── Update persistent structural bias (the v2 fix) ──────────────
        h1_atr = ind.atr(h1_resampled, period=14)
        if h1_atr > 0:
            h1_bos = pa.break_of_structure(
                h1_resampled, atr_value=h1_atr, swing_lookback=self.p.swing_lookback,
                decisive_atr_mult=self.p.decisive_atr_mult,
            )
            if h1_bos.fired:
                self._h1_bias = h1_bos.direction

        m15_atr = ind.atr(m15_resampled, period=14)
        m15_bos = None
        if m15_atr > 0:
            m15_bos = pa.break_of_structure(
                m15_resampled, atr_value=m15_atr, swing_lookback=self.p.swing_lookback,
                decisive_atr_mult=self.p.decisive_atr_mult,
            )
            if m15_bos.fired:
                self._m15_bias = m15_bos.direction

        # ── Stage A: arm a new setup when 15m structure breaks in the ───
        # direction the 1H bias already established. The zone is recorded
        # NOW and waited on LATER -- never required to be touched on this
        # same bar (that conjunction was v1's bug).
        if (
            m15_bos is not None
            and m15_bos.fired
            and self._h1_bias is not None
            and m15_bos.direction == self._h1_bias  # ambiguity #1: hard alignment
        ):
            zone = pa.order_block_zone(m15_resampled, m15_bos)
            if zone.zone_low > 0 and zone.zone_high > zone.zone_low:
                # A fresh structural break supersedes any older un-entered setup.
                self._setup = _Setup(
                    direction=m15_bos.direction, zone_low=zone.zone_low, zone_high=zone.zone_high
                )

        setup = self._setup
        if setup is None:
            return None

        # ── Invalidation: structure flipped against the armed setup ─────
        if self._h1_bias is not None and self._h1_bias != setup.direction:
            self._setup = None
            return None

        # ── Stage B: wait for price to return to (mitigate) the zone ────
        if not setup.mitigated:
            setup.bars_armed += 1
            if setup.bars_armed > self.p.max_arm_bars:
                self._setup = None
                return None
            touched = bar.low <= setup.zone_high and bar.high >= setup.zone_low
            if not touched:
                return None
            setup.mitigated = True
            # Pick the nearby unswept swing extreme to watch (ambiguity #4).
            swings = pa._find_swing_points(ctx.bars(self.p.swing_search_bars), self.p.swing_lookback)
            want_high = setup.direction == Direction.DOWN
            candidates = [s for s in swings if s.is_high == want_high]
            if not candidates:
                self._setup = None
                return None
            setup.sweep_level = max(candidates, key=lambda s: s.index).price
            return None

        # ── Stage C: zone mitigated -- wait for the liquidity sweep ─────
        setup.bars_since_mitigation += 1
        if setup.bars_since_mitigation > self.p.max_wait_after_mitigation_bars:
            self._setup = None
            return None
        if setup.sweep_level is None:
            self._setup = None
            return None

        recent = ctx.bars(3)
        if len(recent) < 2:
            return None
        sweep = pa.liquidity_sweep(
            recent, level_price=setup.sweep_level, level_is_high=(setup.direction == Direction.DOWN)
        )
        if not sweep.fired:
            return None

        # ── Stage D: one same-direction confirmation candle, then enter ─
        last = recent[-1]
        is_bull_candle = last.close > last.open
        if setup.direction == Direction.UP and not is_bull_candle:
            return None
        if setup.direction == Direction.DOWN and is_bull_candle:
            return None

        return self._fire_entry(bar, setup.direction, sweep.extreme_price, m15_resampled)

    def _fire_entry(
        self, bar: Bar, direction: Direction, sweep_extreme: float, m15_resampled: list[Bar]
    ) -> Signal:
        self._setup = None
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
            f"1H bias {direction.value}, 15m zone mitigated then swept {sweep_extreme:.2f}, "
            f"confirmation candle closed, target {target:.2f}"
        )
        # NOTE: the cost-clearing stop/target floor is enforced ENGINE-SIDE
        # as of 2026-09-24 (BacktestEngine._open_position), against the
        # actual fill price. Applying it here against the pre-cost
        # reference silently inverted the intended risk/reward -- see
        # 06_rr_geometry_finding_and_plan.md. Strategies now express
        # structural intent only; the engine enforces viability.
        return Signal(side=side, stop_price=stop, target_price=target, reason=reason)
