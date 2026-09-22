"""
Gold Sweep-Reversal -- session-liquidity-sweep fade on XAUUSD.

Full rules: docs/strategies/gold-xauusd-sweep-reversal.md. Mode-aware:
- **alert** (the live instance running since 2026-09-21): a Telegram
  notification with full reasoning (via ctx.alert_entry's `reason`), no
  order placement. Tracks a lightweight virtual position per entry (in
  ctx.state, no real order behind it) purely so on_tick can watch for
  TP/SL being crossed and send a matching ctx.alert_exit() -- added
  2026-09-22 after the entry alert was found to be genuinely one-shot
  (no way to know from Telegram alone when a signal actually resolved).
- **paper / backtest / live**: a real fire-and-forget entry (ctx.buy/sell,
  fixed lot_size converted to hundredths-of-a-lot quantity -- see
  params_schema), software SL/TP monitoring in on_tick (no broker-native
  bracket assumed, matching this codebase's protective_orders.py pattern
  elsewhere), and a Telegram notification on both entry and exit/outcome
  via ctx.notify -- separate from alert mode's ctx.alert_entry path.

Live data comes from brokers/twelve_data_feed.py (Twelve Data's free
intraday feed) for the alert instance, or data_providers/twelve_data_history.py
for backtests -- not the Funding Pips MT5 broker either way; execution
here (paper mode) is broker-agnostic (any connected broker's PaperBroker
substitute), so there's still no Wine/MT5 terminal dependency for any of
this. See the strategy doc's Section 7 for the feed-divergence caveat
alert mode's live data implies.

Mechanical rules, mechanically applied:
  - 4 daily levels: Asian session high/low (00:00-07:00 UTC by default =
    05:30-12:30 IST) and the previous trading day's high/low (whole
    calendar day, whichever trading day actually has bars -- walks back
    over closed weekends automatically).
  - Only inside the trading window (07:00-13:00 UTC by default =
    12:30-18:30 IST).
  - Trigger: price trades beyond a line (a "sweep"), the very next M5
    candle closes back inside it -> enter at that close, opposite the
    sweep direction (fade).
  - SL: sl_buffer_pts beyond the sweep's wick extreme, minimum min_sl_pts
    (whichever is further from entry).
  - TP: fixed tp_pts.
  - Max max_trades_per_day ENTER alerts/day, with a cooldown_minutes gap
    after any entry -- the card's own FundingPips-rule mapping ("10-min
    same-direction grouping rule -- handled by 'never re-enter'").

Known, stated simplifications vs. the reference backtest
(scripts/gold_sweep_backtest.py) -- see the strategy doc's Section 7 for
the full writeup, not hidden here:
  - Session-level marking uses M5 bars (this feed's only granularity), not
    M1 -- slightly coarser wick precision on the 4 lines than the
    backtest's M1-derived levels.
  - Alert mode tracks no real *broker* position -- "max trades/day" there
    is a pure count plus a cooldown, not "wait for the open trade to
    actually resolve" the way the reference backtest's busy_until models
    a real single-position account, and a new entry can still fire while
    an earlier one is unresolved (up to max_trades_per_day of them). It
    does now track each entry's price/SL/TP as a virtual position purely
    to fire the matching exit alert (see on_tick) -- that bookkeeping
    doesn't gate new entries, it only watches for TP/SL being crossed.
    Paper/live/backtest modes DO track a real open position (see on_tick)
    and gate new entries on it being closed first, closer to busy_until's
    intent, but still not identical -- e.g. no max_hold_min timeout; a
    position just sits until SL or TP hits, however long that takes,
    since the card doesn't specify one.
  - SL/TP checks in backtest mode only happen once per bar, at that bar's
    close (see BacktestEngine.run's on_tick synthesis) -- not true
    intrabar wicks. Same honest limitation credit-spread-weekly's
    protective-order monitoring already has; a live/paper position gets
    checked on every real tick instead.
  - Spread filter (the card's "skip if spread > 0.30") is NOT applied --
    Twelve Data's time_series endpoint returns OHLC only, no bid/ask, so
    there's no spread figure available to check.
  - News veto (no entry within 15 min of a red-folder USD release) is a
    stub, `_news_veto_active` below, until the Finnhub ritual check (G3)
    is wired -- always returns False (never vetoes) rather than silently
    pretending to check something real.
  - On a freshly started instance, `ctx.history()` only has whatever bars
    have accumulated live in memory (see xillion/data/history.py) plus
    whatever's in the DB warehouse for this symbol/exchange, which is
    unverified for XAUUSD/Twelve Data in this repo -- the first day or
    two of running may have incomplete daily levels (fewer than 4 lines)
    until enough live M5 bars have actually been seen. Logged, not
    silently guessed at.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from xillion.core.events import Bar, Side, Tick
from xillion.core.strategy_base import ParamSpec, Strategy, StrategyContext

_LEVEL_ASIAN_HIGH = "Asian High"
_LEVEL_ASIAN_LOW = "Asian Low"
_LEVEL_PD_HIGH = "PD High"
_LEVEL_PD_LOW = "PD Low"
# Opt-in richer level set (params: use_session_levels, prev_day_lookback_days
# -- both default to the original behavior, see params_schema), added
# 2026-09-22 per Rakesh's queued analysis item #2: previous-day levels
# broken out per named session, not just the whole day.
_LEVEL_PD_LONDON_HIGH = "PD London High"
_LEVEL_PD_LONDON_LOW = "PD London Low"
_LEVEL_PD_NY_HIGH = "PD NY-overlap High"
_LEVEL_PD_NY_LOW = "PD NY-overlap Low"

# How far back _roll_day looks for real (already-traded) bars -- 700 M5
# bars is ~58 hours of actual market time, comfortably covering a Monday's
# "previous day" reaching back through a closed weekend to Friday, since
# history() only returns bars that actually traded (no bars during a
# closed weekend consume any of this budget).
_LEVEL_LOOKBACK_BARS = 700
_PREV_DAY_SEARCH_DAYS = 5


def _news_veto_active(ctx: StrategyContext) -> bool:
    """Stub for the news/econ-calendar ritual check (G3, Finnhub) -- not
    wired yet. Always False (no veto) rather than silently pretending to
    check something real. See the strategy doc's Section 7."""
    return False


def _cooldown_active(ctx: StrategyContext, bar: Bar) -> bool:
    cooldown_until = ctx.state.get("cooldown_until")
    return bool(cooldown_until) and bar.ts.isoformat() < cooldown_until


def _confidence_score(
    sl_pts: float,
    min_sl_pts: float,
    max_sl_pts: float,
    reclaim_bars: int,
    sweep_lookback_bars: int,
    recent_losses_in_a_row: int,
) -> tuple[int, list[str]]:
    """0-100 rule-based setup-confidence score -- informational only, never
    a hard gate on whether an entry fires (see enable_confidence_score's
    own doc: "a real decision on whether the score is a hard gate or just
    extra context" was explicitly not made yet, so this defaults to the
    lower-risk option). Grounded in this strategy's own real 6-month
    backtest findings, 2026-09-22 (see docs/strategies/gold-xauusd-sweep-
    reversal.md Section 3): realized SL width -- not win rate -- is what
    actually destroys this strategy's R:R (assumed 2.5:1, realized
    ~0.46:1), across every SL/TP/session-window/level-richness combination
    tried. So SL quality dominates the score; reclaim speed and recent
    streak are secondary, unvalidated-on-their-own signals included as a
    starting point, not because they were independently proven predictive
    -- that would need a proper labeled correlation study against real
    signals, which hasn't been done. Revisit once enough real signals
    exist to check this score against actual outcomes (the Journal already
    tracks self-reported outcomes per signal -- see docs/status/
    task-tracker.md's JEV item for the planned next step: an LLM proposing
    refinements to this scoring, gated on Rakesh's approval, not doing it
    unsupervised)."""
    reasons: list[str] = []
    score = 100.0

    sl_range = max(max_sl_pts - min_sl_pts, 0.01)
    sl_fraction = min(max((sl_pts - min_sl_pts) / sl_range, 0.0), 1.0)
    score -= sl_fraction * 55  # dominant weight -- see docstring
    reasons.append(
        f"{'wide' if sl_fraction > 0.5 else 'tight'} stop ({sl_pts:.1f}pts, "
        f"{sl_fraction * 100:.0f}% of the min-max range)"
    )

    reclaim_fraction = min(max(reclaim_bars / max(sweep_lookback_bars, 1), 0.0), 1.0)
    score -= reclaim_fraction * 25
    reasons.append(f"reclaimed in {reclaim_bars} bar(s)")

    streak_penalty = min(recent_losses_in_a_row * 5, 20)
    score -= streak_penalty
    if recent_losses_in_a_row > 0:
        reasons.append(f"{recent_losses_in_a_row} loss(es) in a row")

    return max(0, min(100, round(score))), reasons


class GoldSweepReversal(Strategy):
    name = "Gold Sweep-Reversal"
    version = "1.0.0"
    description = (
        "XAUUSD session-liquidity-sweep fade, alert-only. Sweeps of the Asian "
        "high/low or previous-day high/low, faded on an M5 close back inside, "
        "trading-window only. See docs/strategies/gold-xauusd-sweep-reversal.md."
    )
    author = "Rakesh"
    timeframe = "5m"
    instruments = ["XAUUSD"]

    params_schema = [
        ParamSpec(
            "tp_pts",
            "float",
            default=7.5,
            min=1.0,
            max=50.0,
            description="Fixed take-profit, in points",
        ),
        ParamSpec(
            "min_sl_pts",
            "float",
            default=3.0,
            min=0.5,
            max=20.0,
            description="Minimum stop-loss distance, in points",
        ),
        ParamSpec(
            "sl_buffer_pts",
            "float",
            default=0.5,
            min=0.0,
            max=5.0,
            description="Buffer beyond the sweep's wick extreme for the stop",
        ),
        ParamSpec(
            "max_trades_per_day",
            "int",
            default=2,
            min=1,
            max=10,
            description="Max ENTER alerts per day",
        ),
        ParamSpec(
            "cooldown_minutes",
            "int",
            default=10,
            min=0,
            max=120,
            description="Minimum gap after any ENTER before the next one",
        ),
        ParamSpec(
            "sweep_lookback_bars",
            "int",
            default=3,
            min=1,
            max=20,
            description="How many M5 bars a sweep stays 'live' waiting for the reclaim close",
        ),
        ParamSpec(
            "session_start_utc_hour",
            "float",
            default=7.0,
            min=0.0,
            max=23.5,
            description="Trading window start, UTC hour (7.0 = 12:30 IST)",
        ),
        ParamSpec(
            "session_end_utc_hour",
            "float",
            default=13.0,
            min=0.0,
            max=24.0,
            description="Trading window end, UTC hour (13.0 = 18:30 IST)",
        ),
        ParamSpec(
            "asian_start_utc_hour",
            "float",
            default=0.0,
            min=0.0,
            max=23.5,
            description="Asian session start, UTC hour (0.0 = 05:30 IST)",
        ),
        ParamSpec(
            "asian_end_utc_hour",
            "float",
            default=7.0,
            min=0.0,
            max=24.0,
            description="Asian session end, UTC hour (7.0 = 12:30 IST)",
        ),
        ParamSpec(
            "lot_size",
            "float",
            default=0.08,
            min=0.01,
            max=1.0,
            description=(
                "Fixed lot size for real orders (paper/live/backtest modes only -- "
                "alert mode places no order). Converted to whole-unit quantity as "
                "round(lot_size * 100), the same hundredths-of-a-lot convention "
                "brokers/mt5_funding_pips.py already uses, so this stays "
                "unit-compatible with a real MT5 fill later."
            ),
        ),
        ParamSpec(
            "max_sl_pts",
            "float",
            default=100.0,
            min=3.0,
            max=200.0,
            description=(
                "Hard cap on the stop-loss distance, regardless of how far the "
                "sweep's wick extreme is. The card's own SL rule (buffer beyond "
                "the wick extreme, minimum min_sl_pts) has no upper bound -- a "
                "violent sweep can put the real SL 50-75+ pts away, which the "
                "first real 6-month backtest (2026-09-22) showed dominates the "
                "strategy's real economics far more than min_sl_pts does. "
                "Default (100.0) is comfortably above every SL seen in that "
                "backtest, so it changes nothing unless deliberately lowered "
                "-- this is an optimizable lever, not a live behavior change."
            ),
        ),
        ParamSpec(
            "use_session_levels",
            "bool",
            default=False,
            description=(
                "Add the previous trading day's London-session and "
                "NY-overlap-session high/low as extra tradeable levels, "
                "alongside the existing Asian High/Low + whole-day PD "
                "High/Low. Opt-in (default off, no live behavior change) "
                "-- added 2026-09-22 to make Rakesh's 'richer level data' "
                "analysis item sweepable rather than a one-off script."
            ),
        ),
        ParamSpec(
            "ny_start_utc_hour",
            "float",
            default=13.0,
            min=0.0,
            max=23.5,
            description="NY-overlap session start, UTC hour, for use_session_levels",
        ),
        ParamSpec(
            "ny_end_utc_hour",
            "float",
            default=17.0,
            min=0.0,
            max=24.0,
            description="NY-overlap session end, UTC hour, for use_session_levels",
        ),
        ParamSpec(
            "prev_day_lookback_days",
            "int",
            default=1,
            min=1,
            max=5,
            description=(
                "How many prior trading days' combined range PD High/PD Low "
                "spans. 1 (default) matches the original card exactly -- "
                "just yesterday's whole-day high/low. >1 widens it to the "
                "highest-high/lowest-low across that many prior days."
            ),
        ),
        ParamSpec(
            "enable_confidence_score",
            "bool",
            default=False,
            description=(
                "Append a 0-100 rule-based setup-confidence score (and the "
                "reasons behind it) to the entry's reasoning text. "
                "Informational only -- never gates whether an entry fires, "
                "by design (see _confidence_score's docstring). Opt-in "
                "(default off, no live behavior change) -- added "
                "2026-09-22 as a first cut at Rakesh's queued 'confidence "
                "%' concept, grounded in this strategy's own finding that "
                "SL width (not win rate) drives its real R:R."
            ),
        ),
    ]

    async def on_start(self, ctx: StrategyContext) -> None:
        ctx.state.setdefault("trade_date", None)  # UTC date (ISO) of the last daily reset
        ctx.state.setdefault("trades_today", 0)
        ctx.state.setdefault("levels", {})  # name -> {"price": float, "kind": "res"|"sup"}
        ctx.state.setdefault("pending", {})  # name -> {"bar_index": int, "extreme": float}
        ctx.state.setdefault("bar_index", 0)
        ctx.state.setdefault("cooldown_until", None)  # ISO timestamp string
        # Real open position for non-alert modes only (paper/live/backtest) --
        # alert mode never sets this, it only ever emits ctx.alert_entry().
        # {symbol, side, qty, entry, sl, tp, level, entry_time} or None.
        ctx.state.setdefault("open_position", None)
        # Alert-mode-only: one entry per list item (no qty/real order), so
        # on_tick can watch for TP/SL and fire the matching ctx.alert_exit().
        # A list, not a single slot, because alert mode can have more than
        # one unresolved entry at once (see the module docstring).
        ctx.state.setdefault("alert_positions", [])
        # Rolling recent WIN/LOSS outcomes (both alert-virtual and real
        # closes append here), used only by the opt-in confidence score's
        # streak component -- see enable_confidence_score/_confidence_score.
        ctx.state.setdefault("recent_outcomes", [])
        ctx.log("info", f"{self.name} started (mode={ctx.mode})", params=ctx.params)

    async def on_bar(self, bar: Bar, ctx: StrategyContext) -> None:
        # Use bar.timeframe, not self.timeframe -- a hardcoded-timeframe
        # check here has silently produced 0-trade backtests before.
        if bar.timeframe != self.timeframe:
            return

        p = ctx.params
        bar_date = bar.ts.date().isoformat()
        hour = bar.ts.hour + bar.ts.minute / 60.0

        # Roll only once we've reached the trading window's own start hour,
        # not on the calendar day's first bar (typically ~00:00 UTC, deep
        # inside the Asian session) -- found 2026-09-22 running a real
        # backtest: rolling at day-start meant TODAY's own Asian-session
        # bars were never yet in ctx.history() (they hadn't been processed
        # yet), so Asian High/Low came back missing on every single day of
        # a 6-month backtest, not just as a first-day bootstrap artifact.
        # Waiting until the trading window's start hour means the day's
        # earlier (Asian-session) bars have each already been processed
        # via their own on_bar call by then, so they're genuinely visible
        # in history when levels are actually computed.
        if ctx.state.get("trade_date") != bar_date and hour >= p["session_start_utc_hour"]:
            await self._roll_day(bar, ctx, bar_date)

        ctx.state["bar_index"] = ctx.state.get("bar_index", 0) + 1
        bar_index = ctx.state["bar_index"]

        if not (p["session_start_utc_hour"] <= hour < p["session_end_utc_hour"]):
            return  # outside the trading window: no observation, no trade

        levels: dict = ctx.state.get("levels") or {}
        if not levels:
            return  # no daily levels yet -- see the module docstring's bootstrap caveat

        # Gates below suppress FIRING a new entry, not the underlying sweep/
        # reclaim tracking -- price still sweeps and reclaims levels during a
        # cooldown, and that pending state must survive to be evaluated once
        # the cooldown clears, rather than being silently dropped (found via
        # testing: gating the whole loop on these caused a bar right at the
        # cooldown boundary to look like a fresh one-bar sweep+reclaim
        # instead of continuing a sweep that started during the cooldown).
        can_fire = (
            ctx.state["trades_today"] < p["max_trades_per_day"]
            and not _cooldown_active(ctx, bar)
            and not _news_veto_active(ctx)
            # Alert mode tracks no real position (never has -- it's a
            # notify-only signal, see the module docstring), so this gate
            # doesn't apply there. Paper/live/backtest track a real fill,
            # and only ever hold one position at a time, matching a real
            # single account -- a second entry while one is still open
            # isn't meaningful until the first one closes via on_tick.
            and (ctx.mode == "alert" or ctx.state.get("open_position") is None)
        )

        pending: dict = ctx.state.setdefault("pending", {})
        for level_name, level in levels.items():
            price = level["price"]
            kind = level["kind"]
            poked = float(bar.high) > price if kind == "res" else float(bar.low) < price
            closed_inside = float(bar.close) < price if kind == "res" else float(bar.close) > price

            if poked:
                extreme = float(bar.high) if kind == "res" else float(bar.low)
                prior = pending.get(level_name)
                if prior is None:
                    pending[level_name] = {"bar_index": bar_index, "extreme": extreme}
                else:
                    new_extreme = (
                        max(prior["extreme"], extreme)
                        if kind == "res"
                        else min(prior["extreme"], extreme)
                    )
                    pending[level_name] = {"bar_index": prior["bar_index"], "extreme": new_extreme}

            live = pending.get(level_name)
            if live is None:
                continue
            if bar_index - live["bar_index"] > p["sweep_lookback_bars"]:
                pending.pop(level_name, None)
                continue
            if not closed_inside:
                continue

            pending.pop(level_name, None)
            if can_fire:
                reclaim_bars = bar_index - live["bar_index"]
                await self._fire_entry(bar, ctx, level_name, kind, live["extreme"], reclaim_bars)
                break  # one trigger per bar -- matches the reference backtest's behaviour

    async def _roll_day(self, bar: Bar, ctx: StrategyContext, bar_date: str) -> None:
        ctx.state["trade_date"] = bar_date
        ctx.state["trades_today"] = 0
        ctx.state["pending"] = {}
        ctx.state["cooldown_until"] = None

        p = ctx.params
        history = await ctx.history(bar.symbol, bar.timeframe, lookback=_LEVEL_LOOKBACK_BARS)
        if not history:
            ctx.state["levels"] = {}
            ctx.log("warning", "no history available yet for daily levels", date=bar_date)
            return

        today = bar.ts.date()

        def _hour(b: Bar) -> float:
            return b.ts.hour + b.ts.minute / 60.0

        asian_bars = [
            b
            for b in history
            if b.ts.date() == today
            and p["asian_start_utc_hour"] <= _hour(b) < p["asian_end_utc_hour"]
        ]

        # Previous N trading days (N = prev_day_lookback_days, default 1) --
        # whole calendar days, walking back from yesterday collecting
        # trading days until N are found or the search budget runs out, so
        # a Monday reaches back through a closed weekend to Friday instead
        # of finding nothing. N=1 (default) is exactly the original
        # behavior: just yesterday's whole-day bars.
        prev_days_bars: list[Bar] = []
        probe = today - timedelta(days=1)
        days_found = 0
        lookback_days = int(p["prev_day_lookback_days"])
        for _ in range(_PREV_DAY_SEARCH_DAYS * max(lookback_days, 1)):
            if days_found >= lookback_days:
                break
            candidates = [b for b in history if b.ts.date() == probe]
            if candidates:
                prev_days_bars.extend(candidates)
                days_found += 1
            probe -= timedelta(days=1)
        # Most recent single prior trading day only -- used for the optional
        # session-level breakdown below, which is about *yesterday's*
        # session structure specifically, not blended across N days the way
        # PD High/Low above can be.
        prev_single_day_bars = [
            b
            for b in prev_days_bars
            if b.ts.date() == max((b.ts.date() for b in prev_days_bars), default=today)
        ]

        levels: dict[str, dict] = {}
        if asian_bars:
            levels[_LEVEL_ASIAN_HIGH] = {
                "price": float(max(b.high for b in asian_bars)),
                "kind": "res",
            }
            levels[_LEVEL_ASIAN_LOW] = {
                "price": float(min(b.low for b in asian_bars)),
                "kind": "sup",
            }
        if prev_days_bars:
            levels[_LEVEL_PD_HIGH] = {
                "price": float(max(b.high for b in prev_days_bars)),
                "kind": "res",
            }
            levels[_LEVEL_PD_LOW] = {
                "price": float(min(b.low for b in prev_days_bars)),
                "kind": "sup",
            }
        if p["use_session_levels"] and prev_single_day_bars:
            london_bars = [
                b
                for b in prev_single_day_bars
                if p["session_start_utc_hour"] <= _hour(b) < p["session_end_utc_hour"]
            ]
            ny_bars = [
                b
                for b in prev_single_day_bars
                if p["ny_start_utc_hour"] <= _hour(b) < p["ny_end_utc_hour"]
            ]
            if london_bars:
                levels[_LEVEL_PD_LONDON_HIGH] = {
                    "price": float(max(b.high for b in london_bars)),
                    "kind": "res",
                }
                levels[_LEVEL_PD_LONDON_LOW] = {
                    "price": float(min(b.low for b in london_bars)),
                    "kind": "sup",
                }
            if ny_bars:
                levels[_LEVEL_PD_NY_HIGH] = {
                    "price": float(max(b.high for b in ny_bars)),
                    "kind": "res",
                }
                levels[_LEVEL_PD_NY_LOW] = {
                    "price": float(min(b.low for b in ny_bars)),
                    "kind": "sup",
                }

        # Expected level count: the original 4 (Asian High/Low, PD High/Low)
        # plus 4 more when use_session_levels is on (PD London/NY High/Low)
        # -- not a hardcoded 4, since that undercounted "missing" once this
        # became opt-in-extendable, 2026-09-22.
        expected = 4 + (4 if p["use_session_levels"] else 0)
        ctx.state["levels"] = levels
        ctx.log(
            "info",
            "daily levels marked",
            date=bar_date,
            levels={k: v["price"] for k, v in levels.items()},
            missing=expected - len(levels),
        )

    async def _fire_entry(
        self,
        bar: Bar,
        ctx: StrategyContext,
        level_name: str,
        kind: str,
        extreme: float,
        reclaim_bars: int,
    ) -> None:
        p = ctx.params
        entry = float(bar.close)
        if kind == "res":
            side = Side.SELL
            sl = max(extreme + p["sl_buffer_pts"], entry + p["min_sl_pts"])
            sl = min(sl, entry + p["max_sl_pts"])  # hard cap, see max_sl_pts's own doc
            tp = entry - p["tp_pts"]
            direction = "SHORT -- fading the sweep up through resistance"
        else:
            side = Side.BUY
            sl = min(extreme - p["sl_buffer_pts"], entry - p["min_sl_pts"])
            sl = max(sl, entry - p["max_sl_pts"])  # hard cap, see max_sl_pts's own doc
            tp = entry + p["tp_pts"]
            direction = "LONG -- fading the sweep down through support"
        sl_pts = abs(sl - entry)
        rr = p["tp_pts"] / sl_pts if sl_pts else 0.0

        trades_today = ctx.state["trades_today"] + 1
        remaining = p["max_trades_per_day"] - trades_today
        progress = (
            f"{remaining} left after this one."
            if remaining > 0
            else "last one allowed today. Two losses today = done, close the platform."
        )
        reason = (
            f"Swept {level_name} at {extreme:.2f}, M5 candle closed back inside at "
            f"{entry:.2f} -- {direction}.\n"
            f"Entry {entry:.2f} | SL {sl:.2f} ({sl_pts:.2f} pts) | "
            f"TP {tp:.2f} ({p['tp_pts']:.1f} pts) | R:R {rr:.2f}:1\n"
            f"Trade {trades_today}/{p['max_trades_per_day']} today -- {progress}\n"
            f"Fixed {p['lot_size']:.2f} lot. Never move the stop. No partials. "
            "No re-entry on this line today."
        )
        if p["enable_confidence_score"]:
            recent = ctx.state.get("recent_outcomes") or []
            losses_in_a_row = 0
            for outcome in reversed(recent):
                if outcome != "LOSS":
                    break
                losses_in_a_row += 1
            score, score_reasons = _confidence_score(
                sl_pts,
                p["min_sl_pts"],
                p["max_sl_pts"],
                reclaim_bars,
                p["sweep_lookback_bars"],
                losses_in_a_row,
            )
            reason += f"\nSetup confidence: {score}/100 ({'; '.join(score_reasons)}) -- informational only, does not gate this entry."

        if ctx.mode == "alert":
            # Notify-only, no order -- the live path this strategy has run
            # since 2026-09-21.
            await ctx.alert_entry(
                bar.symbol,
                side,
                price=Decimal(str(round(entry, 2))),
                target=Decimal(str(round(tp, 2))),
                stop_loss=Decimal(str(round(sl, 2))),
                tag=level_name,
                reason=reason,
            )
            # Track it as a virtual position purely so on_tick can notice
            # TP/SL being crossed and fire the matching exit alert -- added
            # 2026-09-22, see the module docstring. `tag=level_name` matches
            # alert_entry's tag above; _handle_alert_signal already pairs an
            # EXIT to the most recent unclosed ENTER with the same tag, so
            # reusing level_name across days/trades is safe.
            ctx.state.setdefault("alert_positions", []).append(
                {
                    "symbol": bar.symbol,
                    "side": side.value,
                    "entry": entry,
                    "sl": sl,
                    "tp": tp,
                    "level": level_name,
                }
            )
        else:
            # Real fire-and-forget entry (paper/live/backtest) -- SL/TP are
            # tracked in ctx.state and enforced in on_tick below, not by the
            # broker (mirrors the rest of this codebase's software-stop
            # pattern, e.g. protective_orders.py, rather than assuming
            # broker-native bracket support exists for this instrument).
            qty = max(1, round(p["lot_size"] * 100))
            place = ctx.buy if side == Side.BUY else ctx.sell
            order = await place(bar.symbol, qty, tag=level_name)
            fill_price = float(order.avg_fill_price) if order.avg_fill_price else entry
            ctx.state["open_position"] = {
                "symbol": bar.symbol,
                "side": side.value,
                "qty": qty,
                "entry": fill_price,
                "sl": sl,
                "tp": tp,
                "level": level_name,
                "entry_time": bar.ts.isoformat(),
            }
            await ctx.notify(f"Entered {side.value} {bar.symbol}", reason)

        ctx.state["trades_today"] = trades_today
        cooldown_until = bar.ts + timedelta(minutes=p["cooldown_minutes"])
        ctx.state["cooldown_until"] = cooldown_until.isoformat()
        ctx.log(
            "info",
            "sweep-reversal ENTER fired",
            swept_level=level_name,
            side=side.value,
            entry=entry,
            sl=sl,
            tp=tp,
            trades_today=trades_today,
        )

    async def on_tick(self, tick: Tick, ctx: StrategyContext) -> None:
        """TP/SL monitoring, both mode paths driven by the same real ticks.
        In backtest mode this only ever sees one synthetic tick per bar, at
        that bar's close (see BacktestEngine.run) -- an honest
        bar-close-only precision limit, same one credit-spread-weekly's
        protective-order monitoring already lives with, not unique to this
        strategy."""
        if ctx.mode == "alert":
            await self._check_alert_exits(tick, ctx)
            return

        pos = ctx.state.get("open_position")
        if pos is None or tick.symbol != pos["symbol"]:
            return

        price = float(tick.ltp)
        side = pos["side"]
        if side == "BUY":
            hit_tp, hit_sl = price >= pos["tp"], price <= pos["sl"]
        else:
            hit_tp, hit_sl = price <= pos["tp"], price >= pos["sl"]
        if not (hit_tp or hit_sl):
            return

        close = ctx.sell if side == "BUY" else ctx.buy
        order = await close(pos["symbol"], pos["qty"], tag=pos["level"])
        exit_price = float(order.avg_fill_price) if order.avg_fill_price else price
        pnl_pts = (exit_price - pos["entry"]) if side == "BUY" else (pos["entry"] - exit_price)
        outcome = "WIN" if hit_tp else "LOSS"
        recent = ctx.state.setdefault("recent_outcomes", [])
        recent.append(outcome)
        ctx.state["recent_outcomes"] = recent[-20:]  # cap growth on a long-running instance

        ctx.state["open_position"] = None
        await ctx.notify(
            f"{outcome}: closed {side} {pos['symbol']}",
            f"{pos['level']} | entry {pos['entry']:.2f} -> exit {exit_price:.2f} "
            f"({pnl_pts:+.2f} pts, {'target hit' if hit_tp else 'stopped out'})",
            severity="info" if hit_tp else "warn",
        )
        ctx.log(
            "info",
            "sweep-reversal position closed",
            swept_level=pos["level"],
            side=side,
            entry=pos["entry"],
            exit=exit_price,
            pnl_pts=pnl_pts,
            outcome=outcome,
        )

    async def _check_alert_exits(self, tick: Tick, ctx: StrategyContext) -> None:
        """Alert mode's equivalent of the real on_tick close above -- fires
        a ctx.alert_exit() (a real Telegram message, paired to its entry via
        `tag`) instead of placing an order. Uses the actual tick price that
        crossed TP/SL as the exit reference, not the exact TP/SL level
        itself -- a live tick can jump past it, same honest gap-fill
        assumption the real close path makes via avg_fill_price."""
        positions: list = ctx.state.get("alert_positions") or []
        if not positions:
            return

        price = float(tick.ltp)
        still_open = []
        for pos in positions:
            if tick.symbol != pos["symbol"]:
                still_open.append(pos)
                continue

            side = pos["side"]
            if side == "BUY":
                hit_tp, hit_sl = price >= pos["tp"], price <= pos["sl"]
            else:
                hit_tp, hit_sl = price <= pos["tp"], price >= pos["sl"]
            if not (hit_tp or hit_sl):
                still_open.append(pos)
                continue

            outcome = "WIN" if hit_tp else "LOSS"
            recent = ctx.state.setdefault("recent_outcomes", [])
            recent.append(outcome)
            ctx.state["recent_outcomes"] = recent[-20:]
            pnl_pts = (price - pos["entry"]) if side == "BUY" else (pos["entry"] - price)
            exit_side = Side.SELL if side == "BUY" else Side.BUY
            await ctx.alert_exit(
                pos["symbol"],
                exit_side,
                price=Decimal(str(round(price, 2))),
                tag=pos["level"],
                reason=(
                    f"{outcome}: {pos['level']} | entry {pos['entry']:.2f} -> "
                    f"exit {price:.2f} ({pnl_pts:+.2f} pts, "
                    f"{'target hit' if hit_tp else 'stopped out'})"
                ),
            )
            ctx.log(
                "info",
                "sweep-reversal alert exit fired",
                swept_level=pos["level"],
                side=side,
                entry=pos["entry"],
                exit=price,
                pnl_pts=pnl_pts,
                outcome=outcome,
            )

        ctx.state["alert_positions"] = still_open
