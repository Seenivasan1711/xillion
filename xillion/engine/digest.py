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
from xillion.db.models import FillRecord, OrderRecord, StrategyInstance, SystemLog


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

    if report.errored_instances:
        lines.append(f"⚠️ In error state: {', '.join(report.errored_instances)}")
    if report.error_count:
        lines.append(f"{report.error_count} error/critical log line(s) this period — see Logs.")
    if report.running_instances:
        lines.append(f"Running: {', '.join(report.running_instances)}")
    else:
        lines.append("Nothing currently running.")

    return "\n".join(lines)
