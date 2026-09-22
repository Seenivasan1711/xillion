"""
Cost model for the XAUUSD scalping research harness. Costs are the whole
game at this timeframe (per the build spec) -- this is deliberately a
function of session + volatility bucket, not a single constant, since real
spread widens dramatically at London open and around news, exactly when a
scalping strategy trades most.

Spread table below is a PESSIMISTIC ASSUMPTION, not measured from a
real broker feed -- Dukascopy's public tick feed (used for OHLC bars) does
not expose retail-broker spread history for free, so this is stated
explicitly as an assumption rather than presented as measured fact. Revisit
by cross-referencing a real FundingPips/broker spread log once one exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Session(str, Enum):
    ASIA = "asia"
    LONDON = "london"
    LONDON_NY_OVERLAP = "london_ny_overlap"
    NY = "ny"
    DEAD_ZONE = "dead_zone"


def session_for(ts: datetime) -> Session:
    """UTC-hour session tagging. Matches the build spec's session reference
    table: London/NY overlap (13:00-17:00 UTC) is the best-liquidity window,
    Asia (22:30-05:30 UTC wrap) the worst."""
    hour = ts.hour + ts.minute / 60.0
    if 7.0 <= hour < 13.0:
        return Session.LONDON
    if 13.0 <= hour < 17.0:
        return Session.LONDON_NY_OVERLAP
    if 17.0 <= hour < 22.5:
        return Session.NY
    # 22:30 UTC through 07:00 UTC wraps midnight -- Asia, with a genuine
    # dead zone (22:30-00:00) called out separately since spreads there are
    # often the single worst window of the day, not just "Asia."
    if hour >= 22.5 or hour < 5.5:
        return Session.DEAD_ZONE if hour >= 22.5 else Session.ASIA
    return Session.ASIA  # 5.5-7.0 UTC: late Asia, pre-London


class VolBucket(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


def vol_bucket_for(atr_percentile: float) -> VolBucket:
    """`atr_percentile` is the current ATR's percentile rank within its own
    recent history (e.g. trailing 500 bars) -- 0.0-1.0. Terciles, matching
    the build spec's "ATR percentile terciles" requirement for the regime
    breakdown in P3."""
    if atr_percentile < 1 / 3:
        return VolBucket.LOW
    if atr_percentile < 2 / 3:
        return VolBucket.MEDIUM
    return VolBucket.HIGH


# Spread in price points (XAUUSD: 1 point = $0.01, so 30 = $0.30/oz spread).
# PESSIMISTIC ASSUMPTION -- see module docstring.
_SPREAD_TABLE: dict[tuple[Session, VolBucket], float] = {
    (Session.LONDON_NY_OVERLAP, VolBucket.LOW): 18.0,
    (Session.LONDON_NY_OVERLAP, VolBucket.MEDIUM): 25.0,
    (Session.LONDON_NY_OVERLAP, VolBucket.HIGH): 45.0,
    (Session.LONDON, VolBucket.LOW): 20.0,
    (Session.LONDON, VolBucket.MEDIUM): 28.0,
    (Session.LONDON, VolBucket.HIGH): 50.0,
    (Session.NY, VolBucket.LOW): 22.0,
    (Session.NY, VolBucket.MEDIUM): 30.0,
    (Session.NY, VolBucket.HIGH): 55.0,
    (Session.ASIA, VolBucket.LOW): 30.0,
    (Session.ASIA, VolBucket.MEDIUM): 40.0,
    (Session.ASIA, VolBucket.HIGH): 70.0,
    (Session.DEAD_ZONE, VolBucket.LOW): 45.0,
    (Session.DEAD_ZONE, VolBucket.MEDIUM): 60.0,
    (Session.DEAD_ZONE, VolBucket.HIGH): 100.0,
}


@dataclass(frozen=True)
class CostModel:
    commission_per_lot_per_side: float = 3.50  # USD, parameterised per spec
    entry_slippage_pts: float = 3.0  # market-order entry slippage, price points
    exit_slippage_pts: float = 5.0  # stop-out slippage is worse than entry -- spec's own note
    news_slippage_multiplier: float = 3.0  # applied during a news blackout window if a strategy still fires
    spread_table: dict[tuple[Session, VolBucket], float] | None = None  # None -> module default

    @classmethod
    def zero(cls) -> "CostModel":
        """All costs zero -- exists specifically so a test can diff a zero-
        cost run against a real-cost run and assert the difference equals
        the exact modelled cost, not an approximation (see
        test_costed_vs_zero_cost_differs_by_exact_cost)."""
        zero_table = {k: 0.0 for k in _SPREAD_TABLE}
        return cls(
            commission_per_lot_per_side=0.0,
            entry_slippage_pts=0.0,
            exit_slippage_pts=0.0,
            news_slippage_multiplier=1.0,
            spread_table=zero_table,
        )

    def spread_pts(self, session: Session, vol_bucket: VolBucket) -> float:
        table = self.spread_table if self.spread_table is not None else _SPREAD_TABLE
        return table[(session, vol_bucket)]

    def entry_cost_pts(self, session: Session, vol_bucket: VolBucket, is_news_window: bool = False) -> float:
        slip = self.entry_slippage_pts * (self.news_slippage_multiplier if is_news_window else 1.0)
        return self.spread_pts(session, vol_bucket) / 2 + slip

    def exit_cost_pts(self, session: Session, vol_bucket: VolBucket, is_news_window: bool = False) -> float:
        slip = self.exit_slippage_pts * (self.news_slippage_multiplier if is_news_window else 1.0)
        return self.spread_pts(session, vol_bucket) / 2 + slip

    def commission_usd(self, lots: float) -> float:
        """Round-trip commission (both sides) for a given lot size."""
        return self.commission_per_lot_per_side * lots * 2
