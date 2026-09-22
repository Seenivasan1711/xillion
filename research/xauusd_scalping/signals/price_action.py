"""
Price-action / market-structure signal detectors -- the PRIMARY trigger
layer for all 10 shortlisted strategies (01_shortlist_v2.md), per Rakesh's
explicit direction that price action/institutional-liquidity concepts
should lead, with indicators (indicators.py) demoted to a confidence layer.

Every method is independently callable and takes plain `Bar` objects from
`engine.backtest_engine` (or any object with .open/.high/.low/.close/.ts) --
no method depends on another being called first, and no method holds
hidden state between calls. This is deliberate: a future LLM/JEV
orchestrator should be able to call `.liquidity_sweep(...)` on its own
without needing `.displacement_candle(...)` to have run, even though a
specific strategy module (strategies/*.py) might compose several of these
in sequence for its own entry rule.

Every rule is numerically concrete (a threshold + a default + no vague
"significant level" language) per the P1 spec's own hard_constraints --
matching the exact parameter defaults stated in each candidate's spec card
in 01_shortlist_v2.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from engine.backtest_engine import Bar


class Direction(str, Enum):
    UP = "up"
    DOWN = "down"


@dataclass(frozen=True)
class LevelSweepResult:
    fired: bool
    level_price: float = 0.0
    extreme_price: float = 0.0  # how far price traded beyond the level
    reclaimed: bool = False  # closed back inside the level on this or a later bar
    direction: Direction | None = None  # direction of the SWEEP itself (UP = swept a high)
    reason: str = ""


@dataclass(frozen=True)
class DisplacementResult:
    fired: bool
    direction: Direction | None = None
    body_size: float = 0.0
    avg_body_size: float = 0.0
    close_position_pct: float = 0.0  # 0 = closed at the low of its range, 100 = at the high
    reason: str = ""


@dataclass(frozen=True)
class FVGResult:
    fired: bool
    gap_low: float = 0.0
    gap_high: float = 0.0
    direction: Direction | None = None
    filled_pct: float = 0.0  # 0-100, how much of the gap has since been traded through
    reason: str = ""


@dataclass(frozen=True)
class SwingPoint:
    index: int
    price: float
    is_high: bool


@dataclass(frozen=True)
class BOSResult:
    fired: bool
    direction: Direction | None = None
    swing_broken_price: float = 0.0
    decisive_margin_pts: float = 0.0  # how far past the swing point the close was
    order_block_bar_index: int | None = None  # index of the last opposite-color candle before the impulse
    reason: str = ""


@dataclass(frozen=True)
class CHoCHResult:
    fired: bool
    direction: Direction | None = None
    swing_broken_price: float = 0.0
    reason: str = ""


@dataclass(frozen=True)
class OrderBlockResult:
    fired: bool  # True if price has retested (touched) the order block zone
    zone_low: float = 0.0
    zone_high: float = 0.0
    direction: Direction | None = None
    reason: str = ""


@dataclass(frozen=True)
class NR7Result:
    fired: bool
    bar_range: float = 0.0
    is_inside_bar: bool = False
    reason: str = ""


@dataclass(frozen=True)
class RangeSpringResult:
    fired: bool
    range_high: float = 0.0
    range_low: float = 0.0
    direction: Direction | None = None  # UP = upthrust (swept the range high), DOWN = spring
    reclaimed: bool = False
    reason: str = ""


@dataclass(frozen=True)
class EqualLevelsResult:
    fired: bool
    level_price: float = 0.0  # the shared (averaged) price of the equal levels
    touch_indices: list[int] = field(default_factory=list)
    is_high: bool = True
    reason: str = ""


@dataclass(frozen=True)
class LiquidityRunResult:
    fired: bool
    levels_taken: int = 0
    direction: Direction | None = None
    final_extreme: float = 0.0
    reason: str = ""


class PriceActionSignals:
    """Stateless detectors -- every method takes the bars it needs as an
    argument and returns a fresh, immutable result. No instance state."""

    # ── Liquidity sweep (candidates #1, #9, #10's building block) ──────────

    def liquidity_sweep(
        self, bars: list[Bar], level_price: float, level_is_high: bool
    ) -> LevelSweepResult:
        """Did the most recent bar trade beyond `level_price` (a sweep), and
        has price since closed back inside it (a reclaim)? `level_is_high`
        selects whether we're checking a resistance-style level (sweep =
        trade above it) or support-style (sweep = trade below it)."""
        if not bars:
            return LevelSweepResult(fired=False, reason="no bars")
        last = bars[-1]
        if level_is_high:
            swept = last.high > level_price
            extreme = last.high
            reclaimed = last.close < level_price
            direction = Direction.UP
        else:
            swept = last.low < level_price
            extreme = last.low
            reclaimed = last.close > level_price
            direction = Direction.DOWN
        if not swept:
            return LevelSweepResult(fired=False, reason="level not swept")
        return LevelSweepResult(
            fired=True,
            level_price=level_price,
            extreme_price=extreme,
            reclaimed=reclaimed,
            direction=direction,
            reason=f"swept {level_price:.2f}, extreme {extreme:.2f}, reclaimed={reclaimed}",
        )

    # ── Displacement (candidates #1, #9's confirmation) ─────────────────────

    def displacement_candle(
        self,
        bars: list[Bar],
        avg_body_lookback: int = 20,
        body_mult: float = 1.5,
        close_pct_threshold: float = 25.0,
        direction: Direction | None = None,
    ) -> DisplacementResult:
        """Is the most recent bar an aggressive displacement candle: body
        >= `body_mult` x the average body of the prior `avg_body_lookback`
        bars, closing within `close_pct_threshold`% of its own extreme in
        `direction` (or either direction if None)? Defaults match
        candidate #1's spec card (1.5x, top/bottom 25%)."""
        if len(bars) < avg_body_lookback + 1:
            return DisplacementResult(fired=False, reason="not enough history")
        window = bars[-(avg_body_lookback + 1) : -1]
        avg_body = sum(abs(b.close - b.open) for b in window) / len(window)
        last = bars[-1]
        body = abs(last.close - last.open)
        bar_range = last.high - last.low
        if bar_range <= 0 or avg_body <= 0:
            return DisplacementResult(fired=False, reason="degenerate bar")

        is_bullish = last.close > last.open
        # 0% = closed at the bar's low, 100% = closed at the bar's high
        close_pct = ((last.close - last.low) / bar_range) * 100.0

        big_enough = body >= body_mult * avg_body
        if is_bullish:
            forceful_close = close_pct >= (100.0 - close_pct_threshold)
            bar_direction = Direction.UP
        else:
            forceful_close = close_pct <= close_pct_threshold
            bar_direction = Direction.DOWN

        if direction is not None and bar_direction != direction:
            return DisplacementResult(fired=False, reason="wrong direction")
        if not (big_enough and forceful_close):
            return DisplacementResult(
                fired=False,
                body_size=body,
                avg_body_size=avg_body,
                close_position_pct=close_pct,
                reason="body/close-position threshold not met",
            )
        return DisplacementResult(
            fired=True,
            direction=bar_direction,
            body_size=body,
            avg_body_size=avg_body,
            close_position_pct=close_pct,
            reason=f"body {body:.2f} ({body / avg_body:.2f}x avg), closed at {close_pct:.0f}% of range",
        )

    # ── Fair value gap (candidate #1's entry zone) ──────────────────────────

    def fair_value_gap(self, bars: list[Bar]) -> FVGResult:
        """3-candle FVG: a gap between candle[-3]'s high/low and candle[-1]'s
        low/high that candle[-2] (the displacement candle) never traded
        through. Bullish FVG: candle[-3].high < candle[-1].low. Bearish:
        candle[-3].low > candle[-1].high."""
        if len(bars) < 3:
            return FVGResult(fired=False, reason="not enough history")
        c1, _, c3 = bars[-3], bars[-2], bars[-1]
        if c3.low > c1.high:
            return FVGResult(
                fired=True,
                gap_low=c1.high,
                gap_high=c3.low,
                direction=Direction.UP,
                reason=f"bullish FVG {c1.high:.2f}-{c3.low:.2f}",
            )
        if c3.high < c1.low:
            return FVGResult(
                fired=True,
                gap_low=c3.high,
                gap_high=c1.low,
                direction=Direction.DOWN,
                reason=f"bearish FVG {c3.high:.2f}-{c1.low:.2f}",
            )
        return FVGResult(fired=False, reason="no gap")

    def fvg_retest(self, bars: list[Bar], fvg: FVGResult) -> bool:
        """Has the most recent bar touched back into a previously-identified
        FVG zone? Used as the actual entry trigger (candidate #1), separate
        from `fair_value_gap` itself (which only identifies the zone)."""
        if not fvg.fired or not bars:
            return False
        last = bars[-1]
        return last.low <= fvg.gap_high and last.high >= fvg.gap_low

    # ── Break of structure / change of character (candidates #2, #3, #8) ──

    def _find_swing_points(self, bars: list[Bar], swing_lookback: int = 3) -> list[SwingPoint]:
        """A swing high/low needs `swing_lookback` bars strictly lower/higher
        on both sides -- the standard fractal definition."""
        swings: list[SwingPoint] = []
        n = len(bars)
        for i in range(swing_lookback, n - swing_lookback):
            window = bars[i - swing_lookback : i + swing_lookback + 1]
            center = bars[i]
            if all(center.high >= b.high for b in window) and center.high > max(
                b.high for b in window if b is not center
            ):
                swings.append(SwingPoint(index=i, price=center.high, is_high=True))
            if all(center.low <= b.low for b in window) and center.low < min(
                b.low for b in window if b is not center
            ):
                swings.append(SwingPoint(index=i, price=center.low, is_high=False))
        return swings

    def break_of_structure(
        self,
        bars: list[Bar],
        atr_value: float,
        swing_lookback: int = 3,
        decisive_atr_mult: float = 0.3,
    ) -> BOSResult:
        """Has the most recent bar closed decisively (>= `decisive_atr_mult`
        x ATR) beyond the most recent confirmed swing high/low? Also
        identifies the order-block candle: the last opposite-color candle
        before the impulse leg that caused the break (candidate #3)."""
        swings = self._find_swing_points(bars[:-1], swing_lookback)
        if not swings or atr_value <= 0:
            return BOSResult(fired=False, reason="no confirmed swing points yet")
        last = bars[-1]
        recent_high = max((s for s in swings if s.is_high), key=lambda s: s.index, default=None)
        recent_low = max((s for s in swings if not s.is_high), key=lambda s: s.index, default=None)

        if recent_high is not None and last.close > recent_high.price + decisive_atr_mult * atr_value:
            ob_index = self._last_opposite_color_before(bars, recent_high.index, bullish=True)
            return BOSResult(
                fired=True,
                direction=Direction.UP,
                swing_broken_price=recent_high.price,
                decisive_margin_pts=last.close - recent_high.price,
                order_block_bar_index=ob_index,
                reason=f"closed {last.close:.2f} beyond swing high {recent_high.price:.2f}",
            )
        if recent_low is not None and last.close < recent_low.price - decisive_atr_mult * atr_value:
            ob_index = self._last_opposite_color_before(bars, recent_low.index, bullish=False)
            return BOSResult(
                fired=True,
                direction=Direction.DOWN,
                swing_broken_price=recent_low.price,
                decisive_margin_pts=recent_low.price - last.close,
                order_block_bar_index=ob_index,
                reason=f"closed {last.close:.2f} beyond swing low {recent_low.price:.2f}",
            )
        return BOSResult(fired=False, reason="no decisive break")

    def _last_opposite_color_before(self, bars: list[Bar], swing_index: int, bullish: bool) -> int | None:
        """Walk back from `swing_index` to find the last candle of the
        OPPOSITE color to the impulse direction -- the SMC "order block"
        definition."""
        for i in range(swing_index, -1, -1):
            b = bars[i]
            is_bull = b.close > b.open
            if bullish and not is_bull:
                return i
            if not bullish and is_bull:
                return i
        return None

    def order_block_zone(self, bars: list[Bar], bos: BOSResult) -> OrderBlockResult:
        """Given a confirmed BOS, returns the order-block candle's own
        high/low as the retest zone, and whether the most recent bar has
        touched back into it (candidate #3's entry trigger)."""
        if not bos.fired or bos.order_block_bar_index is None:
            return OrderBlockResult(fired=False, reason="no BOS/order block identified")
        ob_bar = bars[bos.order_block_bar_index]
        zone_low, zone_high = min(ob_bar.open, ob_bar.close), max(ob_bar.open, ob_bar.close)
        last = bars[-1]
        touched = last.low <= zone_high and last.high >= zone_low
        return OrderBlockResult(
            fired=touched,
            zone_low=zone_low,
            zone_high=zone_high,
            direction=bos.direction,
            reason=f"order block zone {zone_low:.2f}-{zone_high:.2f}, touched={touched}",
        )

    def change_of_character(self, bars: list[Bar], swing_lookback: int = 3) -> CHoCHResult:
        """A CHoCH is the first swing point broken AGAINST the immediately
        prior trend direction (as opposed to a BOS, which breaks WITH it) --
        candidate #2's lower-timeframe confirmation. Approximated here as:
        determine the prior trend from the last two confirmed swing highs/
        lows (higher-highs/higher-lows = up, and vice versa), then check
        whether the most recent bar closed beyond the swing point that
        would invalidate that trend."""
        swings = self._find_swing_points(bars[:-1], swing_lookback)
        highs = sorted((s for s in swings if s.is_high), key=lambda s: s.index)
        lows = sorted((s for s in swings if not s.is_high), key=lambda s: s.index)
        if len(highs) < 2 or len(lows) < 2:
            return CHoCHResult(fired=False, reason="not enough swing history to establish a trend")

        last = bars[-1]
        uptrend = highs[-1].price > highs[-2].price and lows[-1].price > lows[-2].price
        downtrend = highs[-1].price < highs[-2].price and lows[-1].price < lows[-2].price

        if uptrend and last.close < lows[-1].price:
            return CHoCHResult(
                fired=True,
                direction=Direction.DOWN,
                swing_broken_price=lows[-1].price,
                reason=f"uptrend CHoCH: closed below {lows[-1].price:.2f}",
            )
        if downtrend and last.close > highs[-1].price:
            return CHoCHResult(
                fired=True,
                direction=Direction.UP,
                swing_broken_price=highs[-1].price,
                reason=f"downtrend CHoCH: closed above {highs[-1].price:.2f}",
            )
        return CHoCHResult(fired=False, reason="no character change")

    # ── NR7 / inside bar compression (candidate #5) ─────────────────────────

    def nr7_inside_bar(self, bars: list[Bar], nr_lookback: int = 7) -> NR7Result:
        """Is the most recent bar the narrowest range of the last
        `nr_lookback` bars, AND also fully contained within the PRIOR bar's
        range (an inside bar)?"""
        if len(bars) < nr_lookback + 1:
            return NR7Result(fired=False, reason="not enough history")
        window = bars[-nr_lookback:]
        last = window[-1]
        prior = bars[-2]
        last_range = last.high - last.low
        is_narrowest = all(last_range <= (b.high - b.low) for b in window)
        is_inside = last.high <= prior.high and last.low >= prior.low
        return NR7Result(
            fired=is_narrowest and is_inside,
            bar_range=last_range,
            is_inside_bar=is_inside,
            reason=f"range {last_range:.2f}, narrowest={is_narrowest}, inside={is_inside}",
        )

    # ── Wyckoff spring/upthrust (candidate #4) ──────────────────────────────

    def range_spring_upthrust(
        self,
        daily_bars: list[Bar],
        intraday_bars: list[Bar],
        range_min_days: int = 5,
        range_tolerance_pct: float = 1.5,
    ) -> RangeSpringResult:
        """`daily_bars` are one-bar-per-day OHLC (the caller resamples --
        this method doesn't do timeframe conversion itself, keeping it a
        pure function of whatever bars it's handed, same as every other
        method here). Detects a multi-day range (each day's high/low within
        `range_tolerance_pct`% of the range's own overall high/low), then
        checks whether the most recent intraday bar swept beyond that range
        and reclaimed."""
        if len(daily_bars) < range_min_days:
            return RangeSpringResult(fired=False, reason="not enough daily history")
        window = daily_bars[-range_min_days:]
        range_high = max(b.high for b in window)
        range_low = min(b.low for b in window)
        span = range_high - range_low
        if span <= 0:
            return RangeSpringResult(fired=False, reason="degenerate range")
        tolerance = span * (range_tolerance_pct / 100.0)
        is_real_range = all(
            (range_high - b.high) <= tolerance and (b.low - range_low) <= tolerance for b in window
        )
        if not is_real_range or not intraday_bars:
            return RangeSpringResult(fired=False, reason="not a tight enough range")

        last = intraday_bars[-1]
        if last.high > range_high:
            return RangeSpringResult(
                fired=True,
                range_high=range_high,
                range_low=range_low,
                direction=Direction.UP,
                reclaimed=last.close < range_high,
                reason=f"upthrust beyond {range_high:.2f}",
            )
        if last.low < range_low:
            return RangeSpringResult(
                fired=True,
                range_high=range_high,
                range_low=range_low,
                direction=Direction.DOWN,
                reclaimed=last.close > range_low,
                reason=f"spring beyond {range_low:.2f}",
            )
        return RangeSpringResult(fired=False, range_high=range_high, range_low=range_low, reason="range holding")

    # ── Equal highs/lows (candidates #2, #10) ───────────────────────────────

    def equal_highs_lows(
        self, bars: list[Bar], tolerance_pct: float = 0.1, lookback: int = 50, swing_lookback: int = 3
    ) -> list[EqualLevelsResult]:
        """Finds clusters of 2+ swing highs (or lows) within `tolerance_pct`%
        of each other in the last `lookback` bars -- a liquidity pool by
        definition (multiple stop clusters at nearly the same price)."""
        window = bars[-lookback:] if len(bars) > lookback else bars
        swings = self._find_swing_points(window, swing_lookback)
        results: list[EqualLevelsResult] = []
        for is_high in (True, False):
            points = sorted((s for s in swings if s.is_high == is_high), key=lambda s: s.price)
            used: set[int] = set()
            for i, p in enumerate(points):
                if i in used:
                    continue
                cluster = [p]
                for j in range(i + 1, len(points)):
                    if j in used:
                        continue
                    tol = p.price * (tolerance_pct / 100.0)
                    if abs(points[j].price - p.price) <= tol:
                        cluster.append(points[j])
                        used.add(j)
                if len(cluster) >= 2:
                    avg_price = sum(c.price for c in cluster) / len(cluster)
                    results.append(
                        EqualLevelsResult(
                            fired=True,
                            level_price=avg_price,
                            touch_indices=[c.index for c in cluster],
                            is_high=is_high,
                            reason=f"{len(cluster)} equal {'highs' if is_high else 'lows'} near {avg_price:.2f}",
                        )
                    )
        return results

    # ── Multi-level liquidity run (candidate #9) ────────────────────────────

    def liquidity_run(
        self, bars: list[Bar], levels: list[float], level_is_high: list[bool], min_levels_in_run: int = 2
    ) -> LiquidityRunResult:
        """Has price taken out `min_levels_in_run` or more of the given
        `levels` (each flagged high/low in `level_is_high`) in the SAME
        direction within the bars provided -- a "run," not a single sweep?
        `levels`/`level_is_high` are parallel lists (e.g. Asian High/Low,
        PD High/Low) -- caller supplies whichever levels are marked for the
        day, same as `strategies/gold_sweep_reversal.py`'s own level dict."""
        if not bars:
            return LiquidityRunResult(fired=False, reason="no bars")
        session_high = max(b.high for b in bars)
        session_low = min(b.low for b in bars)

        taken_up = [lvl for lvl, is_high in zip(levels, level_is_high, strict=True) if is_high and session_high > lvl]
        taken_down = [
            lvl for lvl, is_high in zip(levels, level_is_high, strict=True) if not is_high and session_low < lvl
        ]

        if len(taken_up) >= min_levels_in_run:
            return LiquidityRunResult(
                fired=True,
                levels_taken=len(taken_up),
                direction=Direction.UP,
                final_extreme=session_high,
                reason=f"ran through {len(taken_up)} levels to the upside, extreme {session_high:.2f}",
            )
        if len(taken_down) >= min_levels_in_run:
            return LiquidityRunResult(
                fired=True,
                levels_taken=len(taken_down),
                direction=Direction.DOWN,
                final_extreme=session_low,
                reason=f"ran through {len(taken_down)} levels to the downside, extreme {session_low:.2f}",
            )
        return LiquidityRunResult(fired=False, reason="no multi-level run yet")
