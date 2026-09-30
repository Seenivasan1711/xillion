"""
Prop-firm account limits (2026-09-26 app plan, step 4): where Rakesh's
FundingPips 2-Step Flex account stands against its rules, computed from his
CLOSED trades in My Trades (imported MT5 reports + manual entries).

Honest scope: closed trades only. FundingPips measures the daily limit on
EQUITY (open trades included), which needs a live MT5 connection; this is
the after-the-fact view Rakesh chose first (2026-09-30). Everything here is
therefore "realized", and the UI says so.

Rules (FundingPips 2-Step Flex, looked up 2026-09-25, docs/status/manual-tasks.md):
  - daily loss 4%, from the day's opening balance (they use the higher of
    opening balance/equity; without equity, opening balance), resetting at
    00:00 platform time = EET/EEST (Europe/Helsinki -- the same server clock
    measured for MT5 imports)
  - max loss 12%, static from the starting balance
  - profit target 10% (phase 1) / 6% (phase 2), none on master
  - Rakesh's own stop: $50/day, tighter than the firm's
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

SERVER_TZ = ZoneInfo("Europe/Helsinki")
PHASE_TARGET_PCT = {"phase1": 10.0, "phase2": 6.0, "master": None}
LEVELS = ("ok", "warn", "breach")


@dataclass(frozen=True)
class PropConfig:
    account: str = (
        ""  # My Trades account key (the MT5 login); "" = the account with the most trades
    )
    firm: str = "FundingPips"
    program: str = "2-Step Flex"
    phase: str = "phase1"  # phase1 | phase2 | master
    start_balance: float = 5000.0
    start_date: str = "2026-01-01"  # ISO date the current phase began (server day)
    daily_loss_pct: float = 4.0
    max_loss_pct: float = 12.0
    personal_daily_stop_usd: float = 50.0
    warn_at_pct: float = 80.0  # warn when a limit is this % used
    min_profitable_day_pct: float = 0.5  # 95%-split rule: days >= 0.5% count

    @property
    def profit_target_pct(self) -> float | None:
        return PHASE_TARGET_PCT.get(self.phase)


@dataclass(frozen=True)
class ClosedTrade:
    close_time: datetime  # tz-aware
    net_pnl: float


@dataclass
class Limit:
    name: str
    limit_usd: float
    used_usd: float
    level: str = "ok"

    @property
    def used_pct(self) -> float:
        return 100 * self.used_usd / self.limit_usd if self.limit_usd > 0 else 0.0


@dataclass
class PropStatus:
    server_day: str
    balance: float
    today_pnl: float
    total_pnl: float
    limits: list[Limit] = field(default_factory=list)
    target_usd: float | None = None
    target_progress_pct: float | None = None
    trading_days: int = 0
    profitable_days: int = 0
    trades_counted: int = 0

    @property
    def level(self) -> str:
        return max((lim.level for lim in self.limits), key=LEVELS.index, default="ok")


def server_day(ts: datetime) -> str:
    return ts.astimezone(SERVER_TZ).date().isoformat()


def _level(used: float, limit: float, warn_at_pct: float) -> str:
    if limit <= 0:
        return "ok"
    if used >= limit:
        return "breach"
    return "warn" if 100 * used / limit >= warn_at_pct else "ok"


def compute_status(
    cfg: PropConfig, trades: Iterable[ClosedTrade], now: datetime | None = None
) -> PropStatus:
    now = now or datetime.now(UTC)
    today = server_day(now)
    counted = sorted(
        (t for t in trades if server_day(t.close_time) >= cfg.start_date),
        key=lambda t: t.close_time,
    )
    by_day: dict[str, float] = {}
    for t in counted:
        d = server_day(t.close_time)
        by_day[d] = by_day.get(d, 0.0) + t.net_pnl
    total = sum(by_day.values())
    today_pnl = by_day.get(today, 0.0)
    opening = cfg.start_balance + total - today_pnl
    balance = cfg.start_balance + total

    daily_limit = cfg.daily_loss_pct / 100 * opening
    max_limit = cfg.max_loss_pct / 100 * cfg.start_balance
    today_loss = max(0.0, -today_pnl)
    drawdown = max(0.0, cfg.start_balance - balance)
    limits = [
        Limit("Your daily stop", cfg.personal_daily_stop_usd, today_loss),
        Limit(f"Daily loss {cfg.daily_loss_pct:g}%", daily_limit, today_loss),
        Limit(f"Max loss {cfg.max_loss_pct:g}%", max_limit, drawdown),
    ]
    for lim in limits:
        lim.level = _level(lim.used_usd, lim.limit_usd, cfg.warn_at_pct)

    target_pct = cfg.profit_target_pct
    target_usd = target_pct / 100 * cfg.start_balance if target_pct else None
    min_day = cfg.min_profitable_day_pct / 100 * cfg.start_balance
    return PropStatus(
        server_day=today,
        balance=round(balance, 2),
        today_pnl=round(today_pnl, 2),
        total_pnl=round(total, 2),
        limits=limits,
        target_usd=target_usd,
        target_progress_pct=round(100 * total / target_usd, 1) if target_usd else None,
        trading_days=len(by_day),
        profitable_days=sum(1 for v in by_day.values() if v >= min_day),
        trades_counted=len(counted),
    )


def crossed(before: PropStatus, after: PropStatus) -> list[Limit]:
    """Limits whose level got WORSE between two snapshots -- what a Telegram
    warning should mention (a level only ever alerts once per change)."""
    prev = {lim.name: lim.level for lim in before.limits}
    return [
        lim
        for lim in after.limits
        if LEVELS.index(lim.level) > LEVELS.index(prev.get(lim.name, "ok"))
    ]


def warning_text(cfg: PropConfig, status: PropStatus, limits: list[Limit]) -> str:
    lines = [f"{cfg.firm} {cfg.program} ({cfg.phase}) — server day {status.server_day}"]
    for lim in limits:
        verb = "BREACHED" if lim.level == "breach" else f"{lim.used_pct:.0f}% used"
        lines.append(f"• {lim.name}: ${lim.used_usd:,.2f} of ${lim.limit_usd:,.2f} — {verb}")
    lines.append(
        f"Today {status.today_pnl:+,.2f} · balance ${status.balance:,.2f} (closed trades only)"
    )
    return "\n".join(lines)


def next_reset(now: datetime | None = None) -> datetime:
    now = (now or datetime.now(UTC)).astimezone(SERVER_TZ)
    return (
        (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    )
