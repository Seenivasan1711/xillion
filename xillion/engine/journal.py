"""
Strategy journal (CP6): links every signal to its outcome, across the two
places outcomes actually live today --

  - signal_log (CP4, alert mode): an ENTER row carries target_price and
    stop_loss_price; its linked EXIT row (parent_signal_id) carries the
    price it actually closed at. We can compare the two and know for
    certain whether the target or the stop was what ended it.
  - backtest_trade (CP3): has real entry/exit price and computed P&L, but
    -- honestly -- no target/stop-loss on record at all, because ctx.buy()/
    ctx.sell() (what backtest/paper/live actually execute) never carried
    those fields; only ctx.alert_entry() does, and alert mode never fills
    an order. So a backtest loss can be tagged "win"/"loss" with real
    numbers, never "stopped_out" vs "target_missed" -- claiming otherwise
    would be inventing certainty the data doesn't support.

Failure modes this module can auto-classify with actual evidence:
stopped_out, target_hit, win, loss. Everything else in the docs/strategies
template's taxonomy (late_entry, slippage, no_fill, gap, regime_change,
data_gap, system_error) needs data this system doesn't capture yet
(tick-level timing, broker fill/rejection records) -- those stay
`unclassified` here and are meant for a human to set via journal_note
(see xillion/api/journal.py), not for this module to guess at.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import select

from xillion.db.models import BacktestRun, BacktestTrade, SignalLog

# Set with real evidence behind them -- see module docstring.
AUTO_CLASSIFIABLE_OUTCOMES = ("stopped_out", "target_hit", "win", "loss")
UNCLASSIFIED = "unclassified"
STILL_OPEN = "still_open"


@dataclass
class JournalEntry:
    source: str          # "signal_log" | "backtest_trade"
    source_id: str        # str(id), source-specific
    strategy_name: Optional[str]
    strategy_instance_id: Optional[str]
    symbol: str
    side: Optional[str]
    entry_price: Optional[float]
    exit_price: Optional[float]
    entry_ts: Optional[str]
    exit_ts: Optional[str]
    pnl: Optional[float]
    target_price: Optional[float]
    stop_loss_price: Optional[float]
    outcome: str
    tag: Optional[str]


def classify_signal_outcome(
    side: Optional[str],
    exit_price: Optional[float],
    target_price: Optional[float],
    stop_loss_price: Optional[float],
) -> str:
    """For a signal_log ENTER/EXIT pair with a real exit price. Only
    returns stopped_out/target_hit when the exit price actually crossed
    that specific level -- otherwise unclassified (e.g. a manual exit
    between the two levels, or no target/stop was ever set)."""
    if exit_price is None:
        return STILL_OPEN
    if side == "BUY":  # long: target above entry, stop below
        if stop_loss_price is not None and exit_price <= stop_loss_price:
            return "stopped_out"
        if target_price is not None and exit_price >= target_price:
            return "target_hit"
    elif side == "SELL":  # short: target below entry, stop above
        if stop_loss_price is not None and exit_price >= stop_loss_price:
            return "stopped_out"
        if target_price is not None and exit_price <= target_price:
            return "target_hit"
    return UNCLASSIFIED


def classify_trade_outcome(pnl: Optional[float]) -> str:
    if pnl is None:
        return UNCLASSIFIED
    return "win" if pnl > 0 else "loss"


async def _signal_log_entries(session_factory, strategy_instance_id: Optional[str], limit: int) -> list[JournalEntry]:
    async with session_factory() as session:
        stmt = select(SignalLog).where(SignalLog.signal_type == "ENTER")
        if strategy_instance_id:
            stmt = stmt.where(SignalLog.strategy_instance_id == strategy_instance_id)
        stmt = stmt.order_by(SignalLog.id.desc()).limit(limit)
        entries = (await session.execute(stmt)).scalars().all()
        if not entries:
            return []

        entry_ids = [e.id for e in entries]
        exits = (await session.execute(
            select(SignalLog).where(SignalLog.parent_signal_id.in_(entry_ids))
        )).scalars().all()
        exit_by_parent = {e.parent_signal_id: e for e in exits}

    out = []
    for entry in entries:
        exit_row = exit_by_parent.get(entry.id)
        exit_price = float(exit_row.price) if exit_row and exit_row.price is not None else None
        outcome = classify_signal_outcome(
            entry.side,
            exit_price,
            float(entry.target_price) if entry.target_price is not None else None,
            float(entry.stop_loss_price) if entry.stop_loss_price is not None else None,
        )
        out.append(JournalEntry(
            source="signal_log", source_id=str(entry.id),
            strategy_name=None, strategy_instance_id=entry.strategy_instance_id,
            symbol=entry.underlying_symbol, side=entry.side,
            entry_price=float(entry.price) if entry.price is not None else None,
            exit_price=exit_price,
            entry_ts=entry.ts, exit_ts=exit_row.ts if exit_row else None,
            pnl=None,
            target_price=float(entry.target_price) if entry.target_price is not None else None,
            stop_loss_price=float(entry.stop_loss_price) if entry.stop_loss_price is not None else None,
            outcome=outcome, tag=entry.tag,
        ))
    return out


async def _backtest_trade_entries(session_factory, strategy_class_id: Optional[int], limit: int) -> list[JournalEntry]:
    async with session_factory() as session:
        stmt = select(BacktestTrade, BacktestRun.strategy_class_id).join(
            BacktestRun, BacktestTrade.run_id == BacktestRun.id
        ).where(BacktestTrade.exit_price.is_not(None))
        if strategy_class_id is not None:
            stmt = stmt.where(BacktestRun.strategy_class_id == strategy_class_id)
        stmt = stmt.order_by(BacktestTrade.id.desc()).limit(limit)
        rows = (await session.execute(stmt)).all()

    out = []
    for trade, _cls_id in rows:
        pnl = float(trade.pnl) if trade.pnl is not None else None
        out.append(JournalEntry(
            source="backtest_trade", source_id=str(trade.id),
            strategy_name=None, strategy_instance_id=None,
            symbol=trade.symbol, side=trade.side,
            entry_price=float(trade.entry_price), exit_price=float(trade.exit_price),
            entry_ts=trade.entry_ts, exit_ts=trade.exit_ts,
            pnl=pnl, target_price=None, stop_loss_price=None,
            outcome=classify_trade_outcome(pnl), tag=trade.tag,
        ))
    return out


async def build_journal(
    session_factory,
    *,
    strategy_instance_id: Optional[str] = None,
    strategy_class_id: Optional[int] = None,
    limit: int = 200,
) -> list[JournalEntry]:
    """Combined, outcome-classified journal from both sources, newest first
    by entry_ts. `strategy_instance_id` filters signal_log (alert mode is
    always tied to a running instance); `strategy_class_id` filters
    backtest_trade (a backtest has no instance, only a strategy class)."""
    signals = await _signal_log_entries(session_factory, strategy_instance_id, limit)
    trades = await _backtest_trade_entries(session_factory, strategy_class_id, limit)
    combined = signals + trades
    combined.sort(key=lambda e: e.entry_ts or "", reverse=True)
    return combined[:limit]
