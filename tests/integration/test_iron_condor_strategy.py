"""
IronCondorWeeklyStrategy end-to-end (2026-08-29, the first 4-leg strategy):
drives on_bar (range-bound entry gate, DTE gate, credit-adequacy filter,
sizing against the wider side, 4-leg entry) and on_tick (condor_value()
protective-order monitoring + 4-leg exit) against a hand-built fake
StrategyContext, same pattern as test_credit_spread_strategy.py -- proves
the strategy's own logic integrates correctly with multileg.py,
multileg_execution.py, and protective_orders.py's condor_value(), using a
fake broker callback that fills every leg the way a paper/live broker would.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

import strategies.iron_condor_weekly as icw
from strategies.iron_condor_weekly import IronCondorWeeklyStrategy
from xillion.core.events import Bar, Order, OrderRequest, OrderStatus, Side, Tick
from xillion.core.instruments import ResolvedInstrument
from xillion.core.market_calendar import IST

DEFAULT_PARAMS = {p.name: p.default for p in IronCondorWeeklyStrategy.params_schema}
FIXED_NOW = datetime(2026, 1, 6, 10, 0, tzinfo=IST)  # a Tuesday, inside the entry window


async def _fake_now_ist(ctx) -> datetime:
    return FIXED_NOW


class FakeContext:
    """Duck-typed StrategyContext. resolve_strike names legs by role
    (SHORT/LONG, decided by strike-offset magnitude matching
    short_offset_strikes) and option type, so all four legs get distinct,
    predictable symbols -- same convention test_credit_spread_strategy.py
    uses for its 2-leg case."""

    LOT_SIZE = 65
    OPTION_PRICE = {
        "NIFTY_SHORT_CE": Decimal("25"),
        "NIFTY_LONG_CE": Decimal("10"),
        "NIFTY_SHORT_PE": Decimal("25"),
        "NIFTY_LONG_PE": Decimal("10"),
    }

    def __init__(self, params: dict, spot=Decimal("24000"), expiry: date | None = None) -> None:
        self.params = params
        self.state: dict = {}
        self.OPTION_PRICE = dict(self.OPTION_PRICE)  # own copy -- see credit spread test's note
        self.capital_allocated = Decimal("1000000")
        self.mode = "paper"
        self._spot = spot
        self._expiry = expiry or (FIXED_NOW.date() + timedelta(days=params["entry_dte"]))
        self.placed: list[OrderRequest] = []
        self.cancelled: list[str] = []
        self.subscribed: list[tuple[str, str]] = []
        self.critical_alerts: list[tuple[str, str]] = []
        self._order_status_override: dict[str, OrderStatus] = {}

    async def place_order(self, request: OrderRequest) -> Order:
        self.placed.append(request)
        now = datetime.now(UTC)
        status = self._order_status_override.get(request.symbol, OrderStatus.FILLED)
        price = self.OPTION_PRICE.get(request.symbol, Decimal("10"))
        return Order(
            client_order_id=request.client_order_id,
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            order_type=request.order_type,
            status=status,
            submitted_at=now,
            updated_at=now,
            broker_order_id=f"B-{uuid4().hex[:6]}",
            filled_quantity=request.quantity if status == OrderStatus.FILLED else 0,
            avg_fill_price=price if status == OrderStatus.FILLED else None,
        )

    async def cancel_order(self, client_order_id: str) -> bool:
        self.cancelled.append(client_order_id)
        return True

    async def get_order(self, client_order_id: str):
        return None

    async def history(self, symbol: str, timeframe: str, lookback: int) -> list[Bar]:
        # Perfectly flat market: every bar identical, so EMA20 == EMA50 ==
        # VWAP == price exactly -- neither the bull nor bear trend
        # condition can hold, the unambiguous range-bound signal this
        # strategy's entry gate needs.
        base = float(self._spot)
        start = datetime.now(UTC) - timedelta(minutes=15 * 60)
        return [
            Bar(
                symbol=symbol,
                timeframe=timeframe,
                ts=start + timedelta(minutes=15 * i),
                open=Decimal(str(base)),
                high=Decimal(str(base)),
                low=Decimal(str(base)),
                close=Decimal(str(base)),
                volume=1000,
            )
            for i in range(59)
        ]

    async def get_spot(self, underlying: str) -> Decimal:
        return self._spot

    async def resolve_strike(self, underlying, expiry_selector, strike_offset, opt_type):
        strike = self._spot + Decimal(strike_offset) * Decimal("50")
        magnitude = abs(strike_offset)
        role = "SHORT" if magnitude == self.params["short_offset_strikes"] else "LONG"
        symbol = f"{underlying}_{role}_{opt_type}"
        return ResolvedInstrument(
            tradingsymbol=symbol,
            instrument_token=1,
            exchange="NFO",
            underlying=underlying,
            expiry=self._expiry,
            strike=strike,
            option_type=opt_type,
            lot_size=self.LOT_SIZE,
        )

    async def get_option_price(self, symbol: str, exchange: str) -> Decimal:
        return self.OPTION_PRICE.get(symbol, Decimal("10"))

    async def subscribe_instrument(self, symbol: str, exchange: str) -> None:
        self.subscribed.append((symbol, exchange))

    def log(self, level: str, message: str, **fields) -> None:
        pass

    async def notify_critical(self, title: str, body: str) -> None:
        self.critical_alerts.append((title, body))


def _entry_bar(spot: Decimal) -> Bar:
    now = datetime.now(UTC)
    return Bar(
        symbol="NIFTY 50",
        timeframe="15m",
        ts=now,
        open=spot,
        high=spot,
        low=spot,
        close=spot,
        volume=1000,
    )


@pytest.fixture(autouse=True)
def _freeze_entry_window(monkeypatch):
    monkeypatch.setattr(icw, "_now_ist", _fake_now_ist)
    return FIXED_NOW


@pytest.mark.asyncio
async def test_entry_opens_a_correctly_sized_condor_on_a_range_bound_signal():
    params = dict(DEFAULT_PARAMS, short_offset_strikes=2, width_strikes=2)
    ctx = FakeContext(params)
    strategy = IronCondorWeeklyStrategy()

    await strategy.on_bar(_entry_bar(ctx._spot), ctx)

    assert ctx.state["open_position"] is not None
    spec_state = ctx.state["open_position"]["spec"]
    # credit = (25-10) + (25-10) = 30; width = max(100, 100) = 100
    assert Decimal(spec_state["credit"]) == Decimal("30")
    assert Decimal(spec_state["width"]) == Decimal("100")
    # loss/lot = (100-30)*65 = 4550; capital 10L @ 1% risk = 10000 -> 2 lots
    assert spec_state["qty"] == 130
    # All four legs subscribed for tick-driven protective-order monitoring.
    assert len(ctx.subscribed) == 4


@pytest.mark.asyncio
async def test_entry_places_both_longs_before_both_shorts():
    params = dict(DEFAULT_PARAMS, short_offset_strikes=2, width_strikes=2)
    ctx = FakeContext(params)
    strategy = IronCondorWeeklyStrategy()

    await strategy.on_bar(_entry_bar(ctx._spot), ctx)

    assert len(ctx.placed) == 4
    sides = [(r.side, "LONG" in r.symbol) for r in ctx.placed]
    # First two placed are both LONG (wing) legs, buying; last two are both
    # SHORT legs, selling -- order_entry_sequence's role partition.
    assert sides[0] == (Side.BUY, True)
    assert sides[1] == (Side.BUY, True)
    assert sides[2] == (Side.SELL, False)
    assert sides[3] == (Side.SELL, False)


@pytest.mark.asyncio
async def test_entry_skipped_when_a_clear_trend_is_present():
    """The opposite gate from the credit spread: a trending market skips
    the condor entirely (KB: 'do not sell a neutral structure into a
    trend day')."""
    params = dict(DEFAULT_PARAMS, short_offset_strikes=2, width_strikes=2)
    ctx = FakeContext(params)
    strategy = IronCondorWeeklyStrategy()

    async def trending_history(symbol, timeframe, lookback):
        base = float(ctx._spot) - 60
        start = datetime.now(UTC) - timedelta(minutes=15 * 60)
        return [
            Bar(
                symbol=symbol,
                timeframe=timeframe,
                ts=start + timedelta(minutes=15 * i),
                open=Decimal(str(base + i)),
                high=Decimal(str(base + i + 1)),
                low=Decimal(str(base + i - 1)),
                close=Decimal(str(base + i)),
                volume=1000,
            )
            for i in range(59)
        ]

    ctx.history = trending_history

    await strategy.on_bar(_entry_bar(ctx._spot), ctx)

    assert ctx.state.get("open_position") is None
    assert ctx.placed == []


@pytest.mark.asyncio
async def test_entry_skipped_when_position_too_large_for_account():
    params = dict(DEFAULT_PARAMS, short_offset_strikes=2, width_strikes=2, risk_pct=0.0001)
    ctx = FakeContext(params)
    strategy = IronCondorWeeklyStrategy()

    await strategy.on_bar(_entry_bar(ctx._spot), ctx)

    assert ctx.state.get("open_position") is None
    assert ctx.placed == []


@pytest.mark.asyncio
async def test_entry_skipped_outside_dte_window():
    params = dict(DEFAULT_PARAMS, short_offset_strikes=2, width_strikes=2, entry_dte=4)
    ctx = FakeContext(params, expiry=FIXED_NOW.date() + timedelta(days=10))
    strategy = IronCondorWeeklyStrategy()

    await strategy.on_bar(_entry_bar(ctx._spot), ctx)

    assert ctx.state.get("open_position") is None
    assert ctx.placed == []


@pytest.mark.asyncio
async def test_stop_loss_closes_all_four_legs_shorts_first():
    params = dict(DEFAULT_PARAMS, short_offset_strikes=2, width_strikes=2)
    ctx = FakeContext(params)
    strategy = IronCondorWeeklyStrategy()
    await strategy.on_bar(_entry_bar(ctx._spot), ctx)
    assert ctx.state["open_position"] is not None
    ctx.placed.clear()

    spec_state = ctx.state["open_position"]["spec"]
    # condor_value must breach 2x credit (30 -> 60) to trigger STOP. Blow
    # out both short legs' prices, holding longs near their entry.
    ctx.OPTION_PRICE[spec_state["short_call_symbol"]] = Decimal("45")
    ctx.OPTION_PRICE[spec_state["long_call_symbol"]] = Decimal("10")
    ctx.OPTION_PRICE[spec_state["short_put_symbol"]] = Decimal("45")
    ctx.OPTION_PRICE[spec_state["long_put_symbol"]] = Decimal("10")

    now = datetime.now(UTC)
    for key in ("short_call_symbol", "long_call_symbol", "short_put_symbol", "long_put_symbol"):
        sym = spec_state[key]
        await strategy.on_tick(Tick(symbol=sym, ltp=ctx.OPTION_PRICE[sym], ltt=now), ctx)

    assert ctx.state["open_position"] is None  # closed
    assert len(ctx.placed) == 4
    # Shorts-first exit ordering: both SHORT closing BUYs before both LONG
    # closing SELLs.
    assert ctx.placed[0].side == Side.BUY and "SHORT" in ctx.placed[0].symbol
    assert ctx.placed[1].side == Side.BUY and "SHORT" in ctx.placed[1].symbol
    assert ctx.placed[2].side == Side.SELL and "LONG" in ctx.placed[2].symbol
    assert ctx.placed[3].side == Side.SELL and "LONG" in ctx.placed[3].symbol


@pytest.mark.asyncio
async def test_profit_target_closes_position():
    params = dict(DEFAULT_PARAMS, short_offset_strikes=2, width_strikes=2)
    ctx = FakeContext(params)
    strategy = IronCondorWeeklyStrategy()
    await strategy.on_bar(_entry_bar(ctx._spot), ctx)
    spec_state = ctx.state["open_position"]["spec"]
    ctx.placed.clear()

    # condor_value must decay to <= 50% of credit (30 -> 15) -> TARGET.
    # (10-3) + (10-3) = 14 <= 15.
    ctx.OPTION_PRICE[spec_state["short_call_symbol"]] = Decimal("10")
    ctx.OPTION_PRICE[spec_state["long_call_symbol"]] = Decimal("3")
    ctx.OPTION_PRICE[spec_state["short_put_symbol"]] = Decimal("10")
    ctx.OPTION_PRICE[spec_state["long_put_symbol"]] = Decimal("3")

    now = datetime.now(UTC)
    for key in ("short_call_symbol", "long_call_symbol", "short_put_symbol", "long_put_symbol"):
        sym = spec_state[key]
        await strategy.on_tick(Tick(symbol=sym, ltp=ctx.OPTION_PRICE[sym], ltt=now), ctx)

    assert ctx.state["open_position"] is None


@pytest.mark.asyncio
async def test_leg_failure_during_entry_unwinds_the_completed_pair_not_just_one_leg(monkeypatch):
    """The put side's long is rejected outright -- the call side, having
    nothing to do with that failure, still fills, then gets unwound
    cleanly since the whole 4-leg condor couldn't complete. This is
    exactly the multileg_execution.py bug found while building this
    strategy: the old code would never even have attempted the put side's
    short, let alone correctly unwound the call side."""
    params = dict(DEFAULT_PARAMS, short_offset_strikes=2, width_strikes=2)
    ctx = FakeContext(params)
    strategy = IronCondorWeeklyStrategy()

    original_place = ctx.place_order

    async def flaky_place(request: OrderRequest):
        if request.symbol == "NIFTY_LONG_PE":
            now = datetime.now(UTC)
            return Order(
                client_order_id=request.client_order_id,
                symbol=request.symbol,
                side=request.side,
                quantity=request.quantity,
                order_type=request.order_type,
                status=OrderStatus.REJECTED,
                submitted_at=now,
                updated_at=now,
                rejection_reason="simulated broker rejection",
            )
        return await original_place(request)

    monkeypatch.setattr(ctx, "place_order", flaky_place)

    await strategy.on_bar(_entry_bar(ctx._spot), ctx)

    assert ctx.state.get("open_position") is None  # never registered as open
    # NIFTY_LONG_CE was bought then sold back to flatten; NIFTY_SHORT_CE
    # was sold (opened) then bought back to close -- the call side
    # genuinely opened and was unwound cleanly, never left naked.
    long_call_orders = [r for r in ctx.placed if r.symbol == "NIFTY_LONG_CE"]
    short_call_orders = [r for r in ctx.placed if r.symbol == "NIFTY_SHORT_CE"]
    assert [o.side for o in long_call_orders] == [Side.BUY, Side.SELL]
    assert [o.side for o in short_call_orders] == [Side.SELL, Side.BUY]
    # NIFTY_SHORT_PE must NEVER have been placed -- its protecting long
    # (NIFTY_LONG_PE) already failed.
    assert all(r.symbol != "NIFTY_SHORT_PE" for r in ctx.placed)
