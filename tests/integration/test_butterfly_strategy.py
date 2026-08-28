"""
ButterflyWeeklyStrategy end-to-end (2026-08-29, the third multi-leg
strategy and the first DEBIT structure): drives on_bar (range-bound entry
gate, DTE gate, non-positive-debit skip, reward:risk filter, 4-order entry
at 3 distinct strikes) and on_tick (butterfly_value() protective-order
monitoring + exit) against a hand-built fake StrategyContext, same pattern
as test_iron_condor_strategy.py -- proves the strategy's own logic
integrates correctly with multileg.py, multileg_execution.py, and
protective_orders.py's butterfly_value()/butterfly_protective_levels(),
including the split-middle-leg design (two independent 1-lot SHORT legs at
the same strike, see strategies/butterfly_weekly.py's own module docstring
for why) actually isolating a single wing's failure correctly.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

import strategies.butterfly_weekly as bw
from strategies.butterfly_weekly import ButterflyWeeklyStrategy
from xillion.core.events import Bar, Order, OrderRequest, OrderStatus, Side, Tick
from xillion.core.instruments import ResolvedInstrument
from xillion.core.market_calendar import IST

DEFAULT_PARAMS = {p.name: p.default for p in ButterflyWeeklyStrategy.params_schema}
FIXED_NOW = datetime(2026, 1, 6, 10, 0, tzinfo=IST)  # a Tuesday, inside the entry window


async def _fake_now_ist(ctx) -> datetime:
    return FIXED_NOW


class FakeContext:
    """Duck-typed StrategyContext. resolve_strike names legs by role
    (LOWER/MIDDLE/UPPER, decided by strike-offset relative to
    middle_offset_strikes) and option type -- the two middle-strike SHORT
    legs deliberately resolve to the SAME symbol, matching what a real
    resolve_strike() would do (they're the literal same option contract)."""

    LOT_SIZE = 65
    OPTION_PRICE = {
        "NIFTY_LOWER_CE": Decimal("115"),
        "NIFTY_MIDDLE_CE": Decimal("55"),
        "NIFTY_UPPER_CE": Decimal("20"),
    }

    def __init__(self, params: dict, spot=Decimal("24000"), expiry: date | None = None) -> None:
        self.params = params
        self.state: dict = {}
        self.OPTION_PRICE = dict(self.OPTION_PRICE)  # own copy -- avoid cross-test leakage
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
        # Perfectly flat market -- see test_iron_condor_strategy.py's own
        # FakeContext.history for why this specific shape (not just
        # "roughly flat") is what makes EMA20==EMA50==VWAP exactly.
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
        middle_offset = self.params["middle_offset_strikes"]
        if strike_offset == middle_offset:
            role = "MIDDLE"
        elif strike_offset < middle_offset:
            role = "LOWER"
        else:
            role = "UPPER"
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
    monkeypatch.setattr(bw, "_now_ist", _fake_now_ist)
    return FIXED_NOW


@pytest.mark.asyncio
async def test_entry_opens_a_correctly_sized_butterfly_on_a_range_bound_signal():
    params = dict(DEFAULT_PARAMS, wing_offset_strikes=2)
    ctx = FakeContext(params)
    strategy = ButterflyWeeklyStrategy()

    await strategy.on_bar(_entry_bar(ctx._spot), ctx)

    assert ctx.state["open_position"] is not None
    spec_state = ctx.state["open_position"]["spec"]
    # debit = (115+20) - 2*55 = 25; width = 100 (KB D1's own worked example numbers)
    assert Decimal(spec_state["debit"]) == Decimal("25")
    assert Decimal(spec_state["width"]) == Decimal("100")
    # loss/lot = 25*65 = 1625; capital 10L @ 1% risk = 10000 -> floor(10000/1625) = 6 lots
    assert spec_state["qty"] == 390
    # Only 3 distinct strikes -- the two middle-strike legs share one symbol.
    assert len(ctx.subscribed) == 3


@pytest.mark.asyncio
async def test_entry_places_both_wings_before_either_middle_short():
    params = dict(DEFAULT_PARAMS, wing_offset_strikes=2)
    ctx = FakeContext(params)
    strategy = ButterflyWeeklyStrategy()

    await strategy.on_bar(_entry_bar(ctx._spot), ctx)

    assert len(ctx.placed) == 4
    # First two placed are both wings (LONG, buying); last two are both
    # middle-strike shorts (SELL) -- order_entry_sequence's role partition,
    # same convention as the iron condor's two independent pairs.
    assert ctx.placed[0].side == Side.BUY and "MIDDLE" not in ctx.placed[0].symbol
    assert ctx.placed[1].side == Side.BUY and "MIDDLE" not in ctx.placed[1].symbol
    assert ctx.placed[2].side == Side.SELL and ctx.placed[2].symbol == "NIFTY_MIDDLE_CE"
    assert ctx.placed[3].side == Side.SELL and ctx.placed[3].symbol == "NIFTY_MIDDLE_CE"


@pytest.mark.asyncio
async def test_entry_skipped_when_a_clear_trend_is_present():
    params = dict(DEFAULT_PARAMS, wing_offset_strikes=2)
    ctx = FakeContext(params)
    strategy = ButterflyWeeklyStrategy()

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
    params = dict(DEFAULT_PARAMS, wing_offset_strikes=2, risk_pct=0.0001)
    ctx = FakeContext(params)
    strategy = ButterflyWeeklyStrategy()

    await strategy.on_bar(_entry_bar(ctx._spot), ctx)

    assert ctx.state.get("open_position") is None
    assert ctx.placed == []


@pytest.mark.asyncio
async def test_entry_skipped_outside_dte_window():
    params = dict(DEFAULT_PARAMS, wing_offset_strikes=2, entry_dte=1)
    ctx = FakeContext(params, expiry=FIXED_NOW.date() + timedelta(days=10))
    strategy = ButterflyWeeklyStrategy()

    await strategy.on_bar(_entry_bar(ctx._spot), ctx)

    assert ctx.state.get("open_position") is None
    assert ctx.placed == []


@pytest.mark.asyncio
async def test_entry_skipped_on_non_positive_debit():
    """A "butterfly" priced so the middle credit exceeds the wing cost
    isn't a valid long butterfly at all -- must skip, not size a
    nonsensical negative-risk position."""
    params = dict(DEFAULT_PARAMS, wing_offset_strikes=2)
    ctx = FakeContext(params)
    ctx.OPTION_PRICE["NIFTY_MIDDLE_CE"] = Decimal("100")  # 2*100=200 > 115+20=135
    strategy = ButterflyWeeklyStrategy()

    await strategy.on_bar(_entry_bar(ctx._spot), ctx)

    assert ctx.state.get("open_position") is None
    assert ctx.placed == []


@pytest.mark.asyncio
async def test_entry_skipped_when_reward_to_risk_below_minimum():
    params = dict(DEFAULT_PARAMS, wing_offset_strikes=2, min_reward_to_risk=10.0)
    ctx = FakeContext(params)
    strategy = ButterflyWeeklyStrategy()

    await strategy.on_bar(_entry_bar(ctx._spot), ctx)

    # max_profit/debit = 75/25 = 3, below the 10.0 minimum required here.
    assert ctx.state.get("open_position") is None
    assert ctx.placed == []


@pytest.mark.asyncio
async def test_stop_loss_closes_all_legs_middle_shorts_first():
    params = dict(DEFAULT_PARAMS, wing_offset_strikes=2)
    ctx = FakeContext(params)
    strategy = ButterflyWeeklyStrategy()
    await strategy.on_bar(_entry_bar(ctx._spot), ctx)
    assert ctx.state["open_position"] is not None
    ctx.placed.clear()

    # Every leg worthless -- butterfly_value = 2*0-(0+0) = 0 >= stop_value
    # (-6.25, 75% of the 25 debit given back) -> STOP.
    ctx.OPTION_PRICE["NIFTY_LOWER_CE"] = Decimal("0")
    ctx.OPTION_PRICE["NIFTY_MIDDLE_CE"] = Decimal("0")
    ctx.OPTION_PRICE["NIFTY_UPPER_CE"] = Decimal("0")

    now = datetime.now(UTC)
    for sym in ("NIFTY_LOWER_CE", "NIFTY_MIDDLE_CE", "NIFTY_UPPER_CE"):
        await strategy.on_tick(Tick(symbol=sym, ltp=ctx.OPTION_PRICE[sym], ltt=now), ctx)

    assert ctx.state["open_position"] is None  # closed
    assert len(ctx.placed) == 4
    # Shorts-first exit ordering: both middle-strike closing BUYs before
    # both wing closing SELLs.
    assert ctx.placed[0].side == Side.BUY and ctx.placed[0].symbol == "NIFTY_MIDDLE_CE"
    assert ctx.placed[1].side == Side.BUY and ctx.placed[1].symbol == "NIFTY_MIDDLE_CE"
    assert ctx.placed[2].side == Side.SELL and "MIDDLE" not in ctx.placed[2].symbol
    assert ctx.placed[3].side == Side.SELL and "MIDDLE" not in ctx.placed[3].symbol


@pytest.mark.asyncio
async def test_profit_target_closes_position():
    params = dict(DEFAULT_PARAMS, wing_offset_strikes=2)
    ctx = FakeContext(params)
    strategy = ButterflyWeeklyStrategy()
    await strategy.on_bar(_entry_bar(ctx._spot), ctx)
    ctx.placed.clear()

    # Spot pinned exactly at the middle strike at expiry: lower wing worth
    # its full intrinsic (100), middle and upper worth 0.
    # butterfly_value = 2*0-(100+0) = -100 <= target_value (-62.5) -> TARGET.
    ctx.OPTION_PRICE["NIFTY_LOWER_CE"] = Decimal("100")
    ctx.OPTION_PRICE["NIFTY_MIDDLE_CE"] = Decimal("0")
    ctx.OPTION_PRICE["NIFTY_UPPER_CE"] = Decimal("0")

    now = datetime.now(UTC)
    for sym in ("NIFTY_LOWER_CE", "NIFTY_MIDDLE_CE", "NIFTY_UPPER_CE"):
        await strategy.on_tick(Tick(symbol=sym, ltp=ctx.OPTION_PRICE[sym], ltt=now), ctx)

    assert ctx.state["open_position"] is None


@pytest.mark.asyncio
async def test_expiry_day_flatten_time_force_exits_even_without_a_price_trigger(monkeypatch):
    """The whole point of NOT using ProtectiveOrderSpec.time_stop_date
    (see the strategy module's own docstring) -- a position sitting well
    inside its stop/target band must still flatten once the expiry-day
    cutoff time arrives, ahead of X02's 15:15 IST backstop."""
    params = dict(DEFAULT_PARAMS, wing_offset_strikes=2)
    ctx = FakeContext(params)
    strategy = ButterflyWeeklyStrategy()
    await strategy.on_bar(_entry_bar(ctx._spot), ctx)
    spec_state = ctx.state["open_position"]["spec"]
    ctx.placed.clear()

    async def _at_flatten_time(_ctx):
        expiry = date.fromisoformat(spec_state["expiry"])
        return datetime(expiry.year, expiry.month, expiry.day, 15, 10, tzinfo=IST)

    monkeypatch.setattr(bw, "_now_ist", _at_flatten_time)

    now = datetime.now(UTC)
    await strategy.on_tick(Tick(symbol="NIFTY_LOWER_CE", ltp=Decimal("115"), ltt=now), ctx)
    await strategy.on_tick(Tick(symbol="NIFTY_MIDDLE_CE", ltp=Decimal("55"), ltt=now), ctx)
    await strategy.on_tick(Tick(symbol="NIFTY_UPPER_CE", ltp=Decimal("20"), ltt=now), ctx)

    assert ctx.state["open_position"] is None
    assert len(ctx.placed) == 4


@pytest.mark.asyncio
async def test_leg_failure_during_entry_unwinds_the_completed_pair_not_the_other(monkeypatch):
    """The upper wing is rejected outright. The lower wing, having nothing
    to do with that failure, still fills, and its paired middle-strike
    short (protects_leg_index=0) is placed too -- then both get unwound
    cleanly since the whole butterfly couldn't complete. The OTHER
    middle-strike short (protects_leg_index=1, protecting the failed
    upper wing) must NEVER be placed at all -- proving the split-middle-
    leg design (see the strategy's own module docstring) correctly
    isolates a single wing's failure instead of conflating both
    middle-strike shorts into one all-or-nothing 2-lot order."""
    params = dict(DEFAULT_PARAMS, wing_offset_strikes=2)
    ctx = FakeContext(params)
    strategy = ButterflyWeeklyStrategy()

    original_place = ctx.place_order

    async def flaky_place(request: OrderRequest):
        if request.symbol == "NIFTY_UPPER_CE":
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
    lower_orders = [r for r in ctx.placed if r.symbol == "NIFTY_LOWER_CE"]
    middle_orders = [r for r in ctx.placed if r.symbol == "NIFTY_MIDDLE_CE"]
    # NIFTY_LOWER_CE was bought then sold back to flatten.
    assert [o.side for o in lower_orders] == [Side.BUY, Side.SELL]
    # Exactly ONE middle-strike short was ever placed (the one protecting
    # the lower wing, which succeeded) -- opened then unwound. If the
    # split-leg design were broken, this would be 4 orders (both middle
    # legs opened) instead of 2.
    assert [o.side for o in middle_orders] == [Side.SELL, Side.BUY]
