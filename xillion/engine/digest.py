"""
Daily/weekly maintenance digest (CP10) -- the thing that's supposed to make
"3-6 hrs/week" real: instead of the user opening the UI to check what
happened, a scheduled Telegram message tells them. Reuses the same FIFO
fill-matching xillion/api/trades.py's GET /api/trades already does, since
that's the only place real live/paper P&L (as opposed to backtest metrics
or alert-mode target/stop outcomes -- see xillion/engine/journal.py's own
docstring on why those two don't carry real fill data) actually lives.
"""

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select

from xillion.api.trades import _match_fills
from xillion.db.models import FillRecord, OrderRecord, SignalLog, StrategyInstance, SystemLog


@dataclass
class DigestReport:
    period_label: str
    since: str
    trade_count: int
    win_count: int
    loss_count: int
    total_pnl: float
    by_instance: dict = field(default_factory=dict)
    error_count: int = 0
    running_instances: list = field(default_factory=list)
    errored_instances: list = field(default_factory=list)
    # 2026-09-21 (migration 020): alert-mode ENTER signals this period --
    # Gold Sweep-Reversal and friends place no real order, so their
    # "outcome" is the self-reported taken/skipped + win/loss/breakeven on
    # signal_log, not a fill -- a separate figure from trade_count/total_pnl
    # above, which come from real FillRecord rows.
    alert_signal_count: int = 0
    alert_taken: int = 0
    alert_skipped: int = 0
    alert_pending: int = 0  # ENTER fired, no taken/skipped response yet
    alert_wins: int = 0
    alert_losses: int = 0
    alert_breakeven: int = 0
    alert_outcome_pending: int = 0  # taken, but no outcome recorded yet


async def build_digest(session_factory, *, since: datetime, period_label: str) -> DigestReport:
    since_iso = since.isoformat()
    async with session_factory() as db:
        stmt = (
            select(
                FillRecord,
                OrderRecord.strategy_instance_id,
                StrategyInstance.name,
                StrategyInstance.mode,
            )
            .join(OrderRecord, FillRecord.order_id == OrderRecord.id)
            .outerjoin(StrategyInstance, OrderRecord.strategy_instance_id == StrategyInstance.id)
            .where(FillRecord.ts >= since_iso)
        )
        rows = (await db.execute(stmt)).all()
        trades = _match_fills(list(rows))

        error_result = await db.execute(
            select(SystemLog).where(
                SystemLog.ts >= since_iso, SystemLog.level.in_(("error", "critical"))
            )
        )
        error_count = len(error_result.scalars().all())

        inst_result = await db.execute(select(StrategyInstance))
        instances = inst_result.scalars().all()

        signal_result = await db.execute(
            select(SignalLog).where(SignalLog.signal_type == "ENTER", SignalLog.ts >= since_iso)
        )
        alert_signals = signal_result.scalars().all()

    alert_taken = sum(1 for s in alert_signals if s.user_action == "TAKEN")
    alert_skipped = sum(1 for s in alert_signals if s.user_action == "SKIPPED")
    alert_pending = sum(1 for s in alert_signals if s.user_action is None)
    alert_wins = sum(1 for s in alert_signals if s.outcome == "WIN")
    alert_losses = sum(1 for s in alert_signals if s.outcome == "LOSS")
    alert_breakeven = sum(1 for s in alert_signals if s.outcome == "BREAKEVEN")
    alert_outcome_pending = sum(
        1 for s in alert_signals if s.user_action == "TAKEN" and s.outcome is None
    )

    win_count = sum(1 for t in trades if t["pnl"] > 0)
    loss_count = sum(1 for t in trades if t["pnl"] <= 0)
    total_pnl = round(sum(t["pnl"] for t in trades), 2)

    by_instance: dict = {}
    for t in trades:
        by_instance[t["instance_name"]] = round(
            by_instance.get(t["instance_name"], 0.0) + t["pnl"], 2
        )

    return DigestReport(
        period_label=period_label,
        since=since_iso,
        trade_count=len(trades),
        win_count=win_count,
        loss_count=loss_count,
        total_pnl=total_pnl,
        by_instance=by_instance,
        error_count=error_count,
        running_instances=[i.name for i in instances if i.status == "running"],
        errored_instances=[i.name for i in instances if i.status == "error"],
        alert_signal_count=len(alert_signals),
        alert_taken=alert_taken,
        alert_skipped=alert_skipped,
        alert_pending=alert_pending,
        alert_wins=alert_wins,
        alert_losses=alert_losses,
        alert_breakeven=alert_breakeven,
        alert_outcome_pending=alert_outcome_pending,
    )


def _fmt_signed_inr(amount: float) -> str:
    sign = "+" if amount >= 0 else "-"
    return f"{sign}₹{abs(amount):,.2f}"


def format_digest_message(report: DigestReport) -> str:
    lines = [f"*{report.period_label} digest*"]

    if report.trade_count == 0:
        lines.append("No closed trades.")
    else:
        lines.append(
            f"{report.trade_count} trade(s) · {report.win_count}W/{report.loss_count}L · "
            f"P&L {_fmt_signed_inr(report.total_pnl)}"
        )
        for name, pnl in sorted(report.by_instance.items(), key=lambda kv: -abs(kv[1])):
            lines.append(f"  • {name}: {_fmt_signed_inr(pnl)}")

    if report.alert_signal_count:
        resolved = report.alert_wins + report.alert_losses + report.alert_breakeven
        line = (
            f"Alert calls: {report.alert_signal_count} · {report.alert_taken} taken / "
            f"{report.alert_skipped} skipped"
        )
        if report.alert_pending:
            line += f" / {report.alert_pending} unmarked"
        lines.append(line)
        if resolved:
            win_rate = round(100 * report.alert_wins / resolved, 1)
            lines.append(
                f"  • {report.alert_wins}W/{report.alert_losses}L/{report.alert_breakeven}BE "
                f"({win_rate}% win rate of resolved calls)"
            )
        if report.alert_outcome_pending:
            lines.append(f"  • {report.alert_outcome_pending} taken, outcome not logged yet")

    if report.errored_instances:
        lines.append(f"⚠️ In error state: {', '.join(report.errored_instances)}")
    if report.error_count:
        lines.append(f"{report.error_count} error/critical log line(s) this period — see Logs.")
    if report.running_instances:
        lines.append(f"Running: {', '.join(report.running_instances)}")
    else:
        lines.append("Nothing currently running.")

    return "\n".join(lines)
