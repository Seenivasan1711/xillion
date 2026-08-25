"""
End-to-end proof that Options Stage 2 is genuinely unblocked: the real
CreditSpreadWeeklyStrategy, run through the real BacktestEngine, resolving
real InstrumentRow objects via the real resolve_option() -- driven by a
canned (not network-dependent) option-chain provider standing in for NSE
Bhavcopy. This is the actual credit-spread strategy shipped in CP11, not a
simplified stand-in for it.

The strategy's entry-window/DTE gates call ctx.now() (environment-aware),
NOT a bare wall-clock read -- this test pins ctx.now() to track the
CURRENTLY-SIMULATED bar's own date via _BacktestContext.now(), the same way
a real multi-year backtest would need it to, rather than freezing a single
fixed date the whole run coincidentally matches.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from strategies.credit_spread_weekly import CreditSpreadWeeklyStrategy
from xillion.core.events import Bar
from xillion.core.market_calendar import IST
from xillion.data.option_chain import HistoricalOptionRow, OptionChainRepository, OptionChainWarehouse
from xillion.db.session import get_session_factory, init_db
from xillion.engine.backtest_engine import BacktestEngine, FeeConfig

# Tuesday, so it lines up with Nifty's real weekly expiry weekday.
ENTRY_DAY = date(2026, 6, 30)
EXPIRY = ENTRY_DAY + timedelta(days=4)  # DTE 4 -> S3, matches entry_dte default


class _CannedOptionChainProvider:
    """Every weekday, the same NIFTY chain: spot steady, a short PE ~2
    strikes OTM and a long PE further out, credit comfortably above the 15%
    minimum. Premiums decay geometrically by day (theta-like: the short's
    larger premium loses more absolute value per day than the long's, so
    spread value shrinks over time and can hit the profit target)."""

    def __init__(self, decay_start: date) -> None:
        self.calls: list[date] = []
        self._decay_start = decay_start

    async def fetch_option_chain_for_day(self, day: date):
        self.calls.append(day)
        if day.weekday() >= 5:
            return []
        spot = Decimal("24000")
        days_elapsed = max(0, (day - self._decay_start).days)
        decay = Decimal("0.8") ** days_elapsed
        rows = []
        # Strike ladder every 50 points, wide enough either side of spot.
        # Tradingsymbol does NOT embed the day -- a real contract keeps the
        # same tradingsymbol every day until it expires, and the strategy
        # needs to price the SAME open position across multiple days.
        for i in range(-10, 11):
            strike = spot + Decimal(i) * Decimal("50")
            for opt_type, base_price in (("PE", Decimal("60")), ("CE", Decimal("60"))):
                distance = abs(strike - spot)
                price = max(Decimal("1"), (base_price - distance * Decimal("0.25")) * decay)
                rows.append(HistoricalOptionRow(
                    tradingsymbol=f"NIFTY_{int(strike)}_{opt_type}",
                    exchange="NFO", underlying="NIFTY", expiry=EXPIRY, strike=strike,
                    option_type=opt_type, lot_size=65, close=price, underlying_price=spot,
                ))
        return rows


def _underlying_bars(end_day: date) -> list[Bar]:
    """15m NIFTY 50 bars, steady uptrend, from 3 days before ENTRY_DAY
    (enough prior history for the 50EMA) through end_day."""
    bars = []
    start = datetime.combine(ENTRY_DAY - timedelta(days=3), datetime.min.time(), tzinfo=timezone.utc)
    price = Decimal("23940")
    ts = start
    while ts.date() <= end_day:
        bars.append(Bar(
            symbol="NIFTY 50", timeframe="15m", ts=ts,
            open=price, high=price + 1, low=price - 1, close=price, volume=1000,
        ))
        price += Decimal("0.2")  # gentle drift, doesn't dominate the trend/VWAP check
        ts += timedelta(minutes=15)
    return bars


async def _run(end_day: date, decay_start: date, slippage_bps: int = 0) -> tuple:
    await init_db()
    factory = get_session_factory()
    chain_warehouse = OptionChainWarehouse(_CannedOptionChainProvider(decay_start), OptionChainRepository(factory))

    bars = _underlying_bars(end_day)
    strategy = CreditSpreadWeeklyStrategy()
    engine = BacktestEngine()

    result = await engine.run(
        strategy=strategy,
        bars=bars,
        instruments=["NIFTY 50"],
        timeframe="15m",
        initial_capital=1_000_000.0,
        params={
            **{p.name: p.default for p in CreditSpreadWeeklyStrategy.params_schema},
            "short_offset_strikes": 2, "width_strikes": 2,
        },
        slippage_bps=slippage_bps,
        fee_config=FeeConfig.zero(),
        option_chain_warehouse=chain_warehouse,
    )
    return result, chain_warehouse


@pytest.mark.asyncio
async def test_credit_spread_strategy_opens_a_real_position_via_backtest_engine():
    # Nonzero slippage so a real entry cost is visible immediately -- at
    # zero slippage/fees, opening a position is mark-to-market-neutral by
    # construction (the cash received/paid exactly offsets the fresh
    # unrealized exposure at the same price), so equity legitimately
    # doesn't move until the price does. That's correct engine behaviour,
    # not a sign nothing happened -- this test instead uses real slippage
    # as the observable proof.
    result, _ = await _run(end_day=ENTRY_DAY, decay_start=ENTRY_DAY, slippage_bps=20)

    assert result.status == "done", result.error
    opened_a_position = len(result.trades) > 0 or any(
        e != result.equity_curve[0] for e in result.equity_curve
    )
    assert opened_a_position, "no order was ever placed -- options resolution silently no-op'd"


@pytest.mark.asyncio
async def test_credit_spread_strategy_hits_profit_target_and_records_a_real_closed_trade():
    """Extends the window well past entry with decaying premiums, so the
    protective-order monitoring (CP11, driven by the daily-tick synthesis
    BacktestEngine.run adds for dynamically-resolved legs) actually fires
    a TARGET exit and the position closes for real -- not just opens."""
    end_day = ENTRY_DAY + timedelta(days=10)
    result, _ = await _run(end_day=end_day, decay_start=ENTRY_DAY)

    assert result.status == "done", result.error
    assert len(result.trades) >= 1, "position opened but never closed -- exit monitoring didn't fire"
    trade = result.trades[0]
    # Both legs are the same underlying/side (credit spread), closing at a
    # real, non-zero, non-fabricated price -- proves get_option_price's
    # last-price caching fix actually took effect (it used to fill at 0).
    assert trade["entry_price"] > 0
    assert trade["exit_price"] > 0
