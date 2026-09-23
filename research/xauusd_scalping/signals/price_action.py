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
from signals.indicators import IndicatorSignals

_ind = IndicatorSignals()


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
    # Diagnostics from the 3-gate redesign (2026-09-23 -- see
    # research/xauusd_scalping/S04_range_detection_design_question.md for
    # the external design review this implements). Logged so the "gate
    # should pass on 10-25% of real windows" prior-expectation check is
    # auditable against real data rather than just asserted.
    efficiency_ratio: float = 0.0
    span_atr_ratio: float = 0.0
    upper_touches: int = 0
    lower_touches: int = 0
    gate_failed: str = ""  # "G1_trending" | "G2_uncontained" | "G3_untested" | ""


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

    # Measured 2026-09-23 from real XAUUSD daily-resampled bars
    # (research/xauusd_scalping/data/xauusd/*.parquet, 2026-03-01 to
    # 2026-09-16, 167 resampled daily bars):
    #   ATR14.mean() / close.pct_change().std() / close.mean() = 1.4628
    # This is a measured property of gold's own daily volatility structure
    # (how large a "typical" true range runs relative to daily % volatility),
    # not a fitted parameter -- see S04_range_detection_design_question.md
    # section A2 for why that distinction matters. Recompute if the
    # instrument or timeframe changes; never retune this to move backtest
    # P&L.
    _MEASURED_SIGMA_TO_ATR = 1.4628

    def range_spring_upthrust(
        self,
        daily_bars: list[Bar],
        intraday_bars: list[Bar],
        range_min_days: int = 5,
        trend_lookback_days: int = 10,  # n: the (broader) ER trend-context window, >= range_min_days
        atr_period: int = 14,
        edge_zone_atr_mult: float = 0.5,
        min_edge_touches: int = 2,
        min_penetration_atr: float = 0.10,
        max_penetration_atr: float = 0.75,
        reclaim_within_bars: int = 15,
        sigma_to_atr: float = _MEASURED_SIGMA_TO_ATR,
    ) -> RangeSpringResult:
        """Three independent gates replace the old "every day touches both
        extremes" check (which required each of `range_min_days` days to
        have its high near the top AND its low near the bottom of the
        window simultaneously -- confirmed by direct tracing against real
        data to fail 852/873 real windows; see the design doc referenced
        above for the full derivation of everything below).

        Two windows are used deliberately, not one: `trend_lookback_days`
        (broader, default 10) asks "is the recent regime trending at all,"
        while `range_min_days` (tighter, default 5, and always the more
        recent sub-window) defines the actual tradeable range boundaries
        that G2/G3 and the entry/target logic use. A range that only holds
        for the last 5 of a trending 10 days should still be rejected by
        G1's broader-context check.

        G1 (not trending): Kaufman Efficiency Ratio over `trend_lookback_days`
        -- net close displacement / sum of ABSOLUTE close-to-close changes
        (not the sum of daily high-low ranges, which inflates the
        denominator ~2-3x on gold and crushes the ratio toward zero for
        every window regardless of regime -- the bug in the originally
        rejected version of this idea). Threshold `1/sqrt(n)` is the ER a
        driftless random walk produces -- not fitted to this dataset, and
        it independently reproduces Kaufman's own conventional 0.30 cutoff
        at n=10 (1/sqrt(10) = 0.316).

        G2 (contained): the `range_min_days`-day span must sit at or under
        a random walk's expected range envelope,
        `ATR14 * (1 + 1.15*sqrt(range_min_days-1))` -- a trend blows past
        this; a genuine range doesn't.

        G3 (boundaries real): at least `min_edge_touches` distinct days
        must have their high within `edge_zone_atr_mult * ATR14` of the
        range top, and at least `min_edge_touches` distinct days within
        that same zone of the range bottom -- two points define a level. A
        day whose own range spans both edge zones (an outside day) counts
        toward neither, since it doesn't establish either boundary
        specifically.

        Penetration must be `min_penetration_atr..max_penetration_atr` x
        ATR14 beyond the range (below the floor is spread noise; above the
        ceiling is a real breakout, not a false one), and the CURRENT bar
        (`intraday_bars[-1]`) must have closed back inside the range for
        `fired` to be True -- a penetration still awaiting reclaim reports
        `fired=False, reclaimed=False`, not a half-true state the caller
        has to interpret.

        The G2/G3 boundary window deliberately EXCLUDES the most recent
        daily bar (today, possibly still forming): a range that included
        today's own action could never be "penetrated" by today's intraday
        bars, since today's high/low would already BE part of whatever
        range_high/range_low that included it -- a tautology found
        2026-09-23 by tracing why gates could pass (12.2% of real windows,
        exactly the predicted band) yet zero penetrations were ever found
        even scanning a full day back. `daily_bars[-1]` is reserved for
        "today," tested against the range established by the
        `range_min_days` days strictly before it -- `trend_lookback_days`
        (G1) intentionally still runs through today, since the broader
        trend-context question ("is the current regime trending") should
        include the latest data, unlike the range boundaries a fresh
        breakout needs room to actually break."""
        needed = max(range_min_days, trend_lookback_days) + atr_period + 2
        if len(daily_bars) < needed:
            return RangeSpringResult(fired=False, reason="not enough daily history")

        atr = _ind.atr(daily_bars, period=atr_period)
        if atr <= 0:
            return RangeSpringResult(fired=False, reason="degenerate ATR")

        # ── G1: not trending (broader trend_lookback_days window, through today) ──
        trend_window = daily_bars[-(trend_lookback_days + 1):]
        net_move = abs(trend_window[-1].close - trend_window[0].close)
        volatility_sum = sum(
            abs(trend_window[i].close - trend_window[i - 1].close) for i in range(1, len(trend_window))
        )
        efficiency_ratio = (net_move / volatility_sum) if volatility_sum > 0 else 0.0
        er_threshold = 1.0 / (trend_lookback_days**0.5)
        if efficiency_ratio >= er_threshold:
            return RangeSpringResult(
                fired=False,
                efficiency_ratio=efficiency_ratio,
                gate_failed="G1_trending",
                reason=f"trending: ER {efficiency_ratio:.3f} >= {er_threshold:.3f}",
            )

        # ── G2 + G3: range_min_days immediately BEFORE today (today excluded) ──
        window = daily_bars[-(range_min_days + 1) : -1]
        range_high = max(b.high for b in window)
        range_low = min(b.low for b in window)
        span = range_high - range_low
        if span <= 0:
            return RangeSpringResult(
                fired=False, efficiency_ratio=efficiency_ratio, reason="degenerate range"
            )
        span_atr_ratio = span / atr
        # Derivation (design doc section A2): E[range over N steps] ~=
        # 1.6*sigma*sqrt(N-1) for a driftless random walk, plus ~1 ATR of
        # slack for intraday extremes closes don't capture:
        #   span_expected ~= ATR*(1 + (1.6/sigma_to_atr)*sqrt(N-1))
        # The doc's own worked example used a placeholder sigma_to_atr=1.4
        # (giving a 1.6/1.4=1.143~=1.15 coefficient); with the actually
        # measured 1.4628 (see _MEASURED_SIGMA_TO_ATR above) the coefficient
        # is derived here, not hardcoded, so a future re-measurement of
        # sigma_to_atr automatically re-derives the right threshold instead
        # of silently going stale.
        containment_coeff = 1.6 / sigma_to_atr
        max_span = atr * (1.0 + containment_coeff * ((range_min_days - 1) ** 0.5))
        if span > max_span:
            return RangeSpringResult(
                fired=False,
                efficiency_ratio=efficiency_ratio,
                span_atr_ratio=span_atr_ratio,
                gate_failed="G2_uncontained",
                reason=f"uncontained: span {span:.2f} > {max_span:.2f} (={span_atr_ratio:.2f}x ATR)",
            )

        zone = edge_zone_atr_mult * atr
        upper_touches = 0
        lower_touches = 0
        for b in window:
            near_top = b.high >= range_high - zone
            near_bottom = b.low <= range_low + zone
            if near_top and near_bottom:
                continue  # outside day -- doesn't establish either boundary specifically
            if near_top:
                upper_touches += 1
            if near_bottom:
                lower_touches += 1
        if upper_touches < min_edge_touches or lower_touches < min_edge_touches:
            return RangeSpringResult(
                fired=False,
                efficiency_ratio=efficiency_ratio,
                span_atr_ratio=span_atr_ratio,
                upper_touches=upper_touches,
                lower_touches=lower_touches,
                gate_failed="G3_untested",
                reason=f"untested boundaries: {upper_touches} upper / {lower_touches} lower touches",
            )

        diagnostics = dict(
            efficiency_ratio=efficiency_ratio,
            span_atr_ratio=span_atr_ratio,
            upper_touches=upper_touches,
            lower_touches=lower_touches,
        )

        # ── Penetration + same-bar-or-later reclaim, scanned as a pure ──
        # function over the trailing reclaim_within_bars intraday bars ──
        if not intraday_bars:
            return RangeSpringResult(
                fired=False, range_high=range_high, range_low=range_low, reason="no intraday bars", **diagnostics
            )
        scan_window = intraday_bars[-(reclaim_within_bars + 1):]
        now = scan_window[-1]
        penetration_direction: Direction | None = None
        for b in scan_window:
            if b.high > range_high:
                excursion = b.high - range_high
                if min_penetration_atr * atr <= excursion <= max_penetration_atr * atr:
                    penetration_direction = Direction.UP
            if b.low < range_low:
                excursion = range_low - b.low
                if min_penetration_atr * atr <= excursion <= max_penetration_atr * atr:
                    penetration_direction = Direction.DOWN

        if penetration_direction is None:
            return RangeSpringResult(
                fired=False,
                range_high=range_high,
                range_low=range_low,
                reason="no qualifying penetration in window",
                **diagnostics,
            )

        if penetration_direction is Direction.UP:
            reclaimed = now.close < range_high
            reason = f"upthrust beyond {range_high:.2f}, reclaimed={reclaimed}"
        else:
            reclaimed = now.close > range_low
            reason = f"spring beyond {range_low:.2f}, reclaimed={reclaimed}"

        return RangeSpringResult(
            fired=reclaimed,
            range_high=range_high,
            range_low=range_low,
            direction=penetration_direction,
            reclaimed=reclaimed,
            reason=reason,
            **diagnostics,
        )

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
