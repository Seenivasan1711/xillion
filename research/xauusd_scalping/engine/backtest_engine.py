"""
Event-driven backtest engine for the XAUUSD scalping research harness.
Custom-built rather than wrapping backtesting.py/vectorbt: this project's
correctness requirements are unusual enough (pessimistic same-bar SL/TP
resolution as a first-class, auditable flag; session/regime-tagged cost
model; ambiguous-bar counting) that a thin wrapper would spend as much
effort fighting the wrapped library's own assumptions as a lean
custom loop costs to write and prove correct via the synthetic tests in
tests/test_engine.py. ~250 lines, every line exercised by a test with a
hand-computed expected answer.

Strategy contract: a strategy is any object with
`on_bar(bar: Bar, ctx: StrategyContext) -> Signal | None`. The engine calls
this once per CLOSED bar -- a strategy never sees bar[i] until bar[i] has
fully closed, so there is no lookahead by construction (see
test_lookahead_detection in tests/test_engine.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

import bisect
from collections import deque

from .cost_model import POINT_SIZE, CostModel, Session, VolBucket, session_for, vol_bucket_for


class Side(str, Enum):
    LONG = "long"
    SHORT = "short"


@dataclass(frozen=True)
class Bar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass
class Signal:
    """A strategy's requested action for the bar just closed."""

    side: Side
    stop_price: float
    target_price: float
    reason: str = ""
    partial_r: float | None = None  # take X% off at 1R, if set (see Position)
    partial_pct: float = 0.5


@dataclass
class Trade:
    entry_ts: datetime
    side: Side
    entry_price: float
    exit_ts: datetime | None = None
    exit_price: float | None = None
    exit_reason: str = ""
    stop_price: float = 0.0
    target_price: float = 0.0
    lots: float = 0.0
    mae_pts: float = 0.0  # max adverse excursion
    mfe_pts: float = 0.0  # max favourable excursion
    r_multiple: float = 0.0
    spread_paid_pts: float = 0.0
    commission_usd: float = 0.0
    session: str = ""
    bars_held: int = 0
    ambiguous_bar: bool = False  # True if a single bar's range contained both stop and target
    pnl_usd: float = 0.0


@dataclass
class Position:
    side: Side
    entry_price: float
    stop_price: float
    target_price: float
    lots: float
    entry_ts: datetime
    original_lots: float
    partial_taken: bool = False
    breakeven_moved: bool = False
    bars_held: int = 0
    mae_pts: float = 0.0
    mfe_pts: float = 0.0
    entry_session: str = ""
    entry_spread_pts: float = 0.0


class StrategyContext:
    """Read-only view a strategy gets each bar -- history only, no future
    bars, no direct access to the engine's internal position state (a
    strategy proposes signals; it never mutates positions itself)."""

    def __init__(self, history: list[Bar], has_open_position: bool) -> None:
        self._history = history
        self.has_open_position = has_open_position

    def bars(self, lookback: int) -> list[Bar]:
        """Up to `lookback` most recent CLOSED bars, oldest first. Never
        includes the bar currently being evaluated in on_bar -- that bar
        IS the last element the strategy is being asked to react to, and
        is already included in `history` by the time on_bar is called."""
        return self._history[-lookback:]


@dataclass
class SizingConfig:
    mode: str = "fixed_lot"  # "fixed_lot" | "fixed_fractional"
    fixed_lots: float = 0.08
    risk_pct: float = 0.005  # 0.5% of equity per trade, if fixed_fractional
    point_value_usd: float = 1.0  # USD P&L per point per 1.0 lot (XAUUSD: 1 lot = 100oz, 1 pt = $0.01 -> $1/lot/pt)


@dataclass
class RiskLimits:
    max_trades_per_session: int | None = None
    daily_loss_cap_usd: float | None = None
    consecutive_loss_halt: int | None = None
    max_spread_pts: float | None = None  # skip new entries above this spread
    # Cost-clearing stop/target floor, enforced ENGINE-SIDE against the
    # actual fill price (see _open_position). Moved here 2026-09-24 after
    # finding that applying it strategy-side against the pre-cost reference
    # price silently inverted the intended risk/reward -- a designed 2:1
    # became an actual 0.90:1 once the fill markup was subtracted from the
    # target and added to the stop. See 06_rr_geometry_finding_and_plan.md.
    min_sl_pts: float | None = 40.0
    min_target_pts: float | None = 80.0


@dataclass
class BacktestResult:
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)
    ambiguous_bar_count: int = 0
    halted_days: list[str] = field(default_factory=list)


class BacktestEngine:
    def __init__(
        self,
        cost_model: CostModel,
        sizing: SizingConfig | None = None,
        risk: RiskLimits | None = None,
        pessimistic_same_bar_resolution: bool = True,
        news_windows: list[tuple[datetime, datetime]] | None = None,
        atr_period: int = 14,
        vol_percentile_window: int = 500,
    ) -> None:
        self.cost_model = cost_model
        self.sizing = sizing or SizingConfig()
        self.risk = risk or RiskLimits()
        self.pessimistic = pessimistic_same_bar_resolution
        self.news_windows = news_windows or []
        # Volatility-bucket inputs: ATR period, and the trailing window the
        # current ATR is percentile-ranked within (the cost model's own
        # docstring specifies "percentile rank within its own recent
        # history (e.g. trailing 500 bars)").
        self.atr_period = atr_period
        self.vol_percentile_window = vol_percentile_window

    def _is_news_window(self, ts: datetime) -> bool:
        return any(start <= ts <= end for start, end in self.news_windows)

    def _lots_for(self, equity: float, entry: float, stop: float) -> float:
        if self.sizing.mode == "fixed_lot":
            return self.sizing.fixed_lots
        risk_usd = equity * self.sizing.risk_pct
        stop_pts = abs(entry - stop) / POINT_SIZE
        if stop_pts <= 0:
            return 0.0
        return risk_usd / (stop_pts * self.sizing.point_value_usd)

    def run(self, bars: list[Bar], strategy, initial_equity: float = 5000.0) -> BacktestResult:
        result = BacktestResult()
        equity = initial_equity
        position: Position | None = None
        history: list[Bar] = []

        trades_today = 0
        current_day: str | None = None
        daily_pnl = 0.0
        consecutive_losses = 0
        halted_today = False

        # Rolling ATR-percentile state, for the volatility bucket the cost
        # model has always taken but never actually received (it was
        # hardcoded to MEDIUM at both call sites until 2026-09-24, making
        # `vol_bucket_for` dead code and the documented
        # "session x volatility" cost model effectively session-only).
        # O(1) amortised: a running true-range sum for the ATR, plus a
        # sorted window for its percentile rank (bisect/insort are C-level,
        # so this stays cheap enough to run on every bar).
        tr_window: deque[float] = deque(maxlen=self.atr_period)
        tr_sum = 0.0
        atr_window: deque[float] = deque(maxlen=self.vol_percentile_window)
        atr_sorted: list[float] = []
        prev_close: float | None = None
        vol_bucket = VolBucket.MEDIUM

        for i, bar in enumerate(bars):
            history.append(bar)

            # ── Update the volatility bucket from THIS bar's true range ──
            true_range = (
                bar.high - bar.low
                if prev_close is None
                else max(bar.high - bar.low, abs(bar.high - prev_close), abs(bar.low - prev_close))
            )
            prev_close = bar.close
            if len(tr_window) == tr_window.maxlen:
                tr_sum -= tr_window[0]
            tr_window.append(true_range)
            tr_sum += true_range
            if len(tr_window) == tr_window.maxlen:
                atr = tr_sum / len(tr_window)
                if len(atr_window) == atr_window.maxlen:
                    oldest = atr_window[0]
                    idx = bisect.bisect_left(atr_sorted, oldest)
                    if idx < len(atr_sorted) and atr_sorted[idx] == oldest:
                        atr_sorted.pop(idx)
                atr_window.append(atr)
                bisect.insort(atr_sorted, atr)
                if len(atr_sorted) >= 30:  # enough history for a meaningful rank
                    rank = bisect.bisect_left(atr_sorted, atr) / len(atr_sorted)
                    vol_bucket = vol_bucket_for(rank)
            day_key = bar.ts.date().isoformat()
            if day_key != current_day:
                current_day = day_key
                trades_today = 0
                daily_pnl = 0.0
                halted_today = False
                consecutive_losses = 0

            # ── Manage an open position first, using THIS bar's range ──
            if position is not None:
                position.bars_held += 1
                exit_price, exit_reason, ambiguous = self._resolve_intrabar(bar, position)
                if ambiguous:
                    result.ambiguous_bar_count += 1

                favourable = (
                    bar.high - position.entry_price
                    if position.side == Side.LONG
                    else position.entry_price - bar.low
                )
                adverse = (
                    position.entry_price - bar.low
                    if position.side == Side.LONG
                    else bar.high - position.entry_price
                )
                position.mfe_pts = max(position.mfe_pts, favourable / POINT_SIZE)
                position.mae_pts = max(position.mae_pts, adverse / POINT_SIZE)

                if exit_price is not None:
                    trade = self._close_position(
                        position, bar.ts, exit_price, exit_reason, ambiguous, bar, vol_bucket
                    )
                    result.trades.append(trade)
                    equity += trade.pnl_usd
                    daily_pnl += trade.pnl_usd
                    if trade.pnl_usd < 0:
                        consecutive_losses += 1
                    else:
                        consecutive_losses = 0
                    position = None

            # ── Halt checks (before considering a new entry) ──
            if self.risk.daily_loss_cap_usd is not None and daily_pnl <= -abs(self.risk.daily_loss_cap_usd):
                halted_today = True
            if (
                self.risk.consecutive_loss_halt is not None
                and consecutive_losses >= self.risk.consecutive_loss_halt
            ):
                halted_today = True
            if halted_today and day_key not in result.halted_days:
                result.halted_days.append(day_key)

            # ── Ask the strategy for a signal, only on a closed bar, only
            #    if flat and not halted ──
            if position is None and not halted_today:
                if self.risk.max_trades_per_session is None or trades_today < self.risk.max_trades_per_session:
                    sess = session_for(bar.ts)
                    spread = self.cost_model.spread_pts(sess, vol_bucket)
                    spread_ok = self.risk.max_spread_pts is None or spread <= self.risk.max_spread_pts
                    if spread_ok:
                        # `history` is passed by reference, not copied: copying
                        # it every flat bar was O(n) per call and O(n^2) over a
                        # run (a real, measured cause of multi-minute backtests
                        # even for trivial strategies). StrategyContext never
                        # exposes the list itself -- `bars()` returns a fresh
                        # slice -- so there is nothing for a strategy to mutate.
                        ctx = StrategyContext(history=history, has_open_position=False)
                        signal = strategy.on_bar(bar, ctx)
                        if signal is not None:
                            position = self._open_position(
                                bar, signal, equity, sess, spread, vol_bucket
                            )
                            trades_today += 1

            result.equity_curve.append(equity)

        return result

    def _open_position(
        self, bar: Bar, signal: Signal, equity: float, session: Session, spread_pts: float,
        vol_bucket: VolBucket = VolBucket.MEDIUM,
    ) -> Position:
        # Deferred import: signals.risk_floor imports Side from this module,
        # so a module-level import here would be circular. apply_floor is a
        # pure geometry helper with its own tests -- reused rather than
        # duplicated, just called from the right place now (see below).
        from signals.risk_floor import apply_floor

        is_news = self._is_news_window(bar.ts)
        entry_cost = self.cost_model.entry_cost_pts(session, vol_bucket, is_news) * POINT_SIZE
        entry_price = (
            bar.close + entry_cost if signal.side == Side.LONG else bar.close - entry_cost
        )
        # Enforce the cost-clearing floor against the ACTUAL FILL, not the
        # strategy's pre-cost reference price. Doing this strategy-side (as
        # it was until 2026-09-24) meant the fill markup was subtracted from
        # the target and added to the stop simultaneously, turning a
        # designed 2:1 into a realised 0.90:1 -- proven by the exact
        # identity stop_dist + target_dist == 40+80 on 90/90 S11 trades.
        # Widen-only semantics are preserved; only the reference changed.
        stop_price, target_price = signal.stop_price, signal.target_price
        if self.risk.min_sl_pts is not None and self.risk.min_target_pts is not None:
            stop_price, target_price = apply_floor(
                entry_price, stop_price, target_price, signal.side,
                min_sl_pts=self.risk.min_sl_pts * POINT_SIZE,
                min_target_pts=self.risk.min_target_pts * POINT_SIZE,
            )
        lots = self._lots_for(equity, entry_price, stop_price)
        return Position(
            side=signal.side,
            entry_price=entry_price,
            stop_price=stop_price,
            target_price=target_price,
            lots=lots,
            original_lots=lots,
            entry_ts=bar.ts,
            entry_session=session.value,
            entry_spread_pts=spread_pts,
        )

    def _resolve_intrabar(self, bar: Bar, position: Position) -> tuple[float | None, str, bool]:
        """Returns (exit_price, reason, was_ambiguous). exit_price is None
        if the position stays open through this bar.

        Gap handling: if the bar's OPEN already jumped past the stop/target
        (not just the high/low touching it), fill at the open, not at the
        stop/target price -- a real order resting at a stop level fills at
        whatever price the market actually gaps to, which can be materially
        worse than the stop itself. See test_gap_through_stop_fills_at_gap
        in tests/test_engine.py."""
        if position.side == Side.LONG:
            gapped_through_stop = bar.open <= position.stop_price
            gapped_through_target = bar.open >= position.target_price
            hit_stop = bar.low <= position.stop_price
            hit_target = bar.high >= position.target_price
        else:
            gapped_through_stop = bar.open >= position.stop_price
            gapped_through_target = bar.open <= position.target_price
            hit_stop = bar.high >= position.stop_price
            hit_target = bar.low <= position.target_price

        if hit_stop and hit_target:
            # Pessimistic rule: if a single bar's range contains both the
            # stop and the target, record the STOP as hit. This is the
            # spec's own required default -- flagged, not silently assumed.
            if self.pessimistic:
                fill = bar.open if gapped_through_stop else position.stop_price
                return fill, "stop", True
            fill = bar.open if gapped_through_target else position.target_price
            return fill, "target", True
        if hit_stop:
            fill = bar.open if gapped_through_stop else position.stop_price
            return fill, "stop", False
        if hit_target:
            fill = bar.open if gapped_through_target else position.target_price
            return fill, "target", False
        return None, "", False

    def _close_position(
        self,
        position: Position,
        exit_ts: datetime,
        exit_price: float,
        reason: str,
        ambiguous: bool,
        bar: Bar,
        vol_bucket: VolBucket = VolBucket.MEDIUM,
    ) -> Trade:
        session = session_for(exit_ts)
        is_news = self._is_news_window(exit_ts)
        # Volatility bucket AT EXIT TIME (not entry): the spread you actually
        # pay getting out is the one prevailing then, which can differ from
        # entry on a trade held across a volatility change.
        exit_cost = self.cost_model.exit_cost_pts(session, vol_bucket, is_news) * POINT_SIZE
        # exit_cost widens the exit further against the position -- this is
        # the pessimistic "you pay the spread/slippage getting out too" rule.
        adj_exit = exit_price - exit_cost if position.side == Side.LONG else exit_price + exit_cost

        gross_pts = (
            (adj_exit - position.entry_price)
            if position.side == Side.LONG
            else (position.entry_price - adj_exit)
        ) / POINT_SIZE
        gross_usd = gross_pts * position.lots * self.sizing.point_value_usd
        commission = self.cost_model.commission_usd(position.lots)
        net_usd = gross_usd - commission

        stop_pts = abs(position.entry_price - position.stop_price) / POINT_SIZE
        r_multiple = gross_pts / stop_pts if stop_pts else 0.0

        return Trade(
            entry_ts=position.entry_ts,
            side=position.side,
            entry_price=position.entry_price,
            exit_ts=exit_ts,
            exit_price=adj_exit,
            exit_reason=reason,
            stop_price=position.stop_price,
            target_price=position.target_price,
            lots=position.lots,
            mae_pts=position.mae_pts,
            mfe_pts=position.mfe_pts,
            r_multiple=r_multiple,
            spread_paid_pts=position.entry_spread_pts,
            commission_usd=commission,
            session=position.entry_session,
            bars_held=position.bars_held,
            ambiguous_bar=ambiguous,
            pnl_usd=net_usd,
        )
