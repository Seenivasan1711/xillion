"""
CreditSpreadWeeklyStrategy end-to-end (CP11 + Options Stage 1 build): drives
on_bar (entry: trend check, DTE gate, credit-adequacy filter, sizing,
multi-leg entry) and on_tick (protective-order monitoring + exit) against a
hand-built fake StrategyContext.

Not run through BacktestEngine: options resolution (get_spot/resolve_strike/
get_option_price) isn't wired into the backtest context yet (a pre-existing
gap, not something this strategy or CP11 fixes -- see the strategy's module
docstring and docs/strategies/credit-spread-weekly.md). This test instead
proves the strategy's own logic integrates correctly with multileg.py,
multileg_execution.py, and protective_orders.py, using a fake broker
callback that fills every leg the way a paper/live broker would.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

import strategies.credit_spread_weekly as csw
from strategies.credit_spread_weekly import CreditSpreadWeeklyStrategy
from xillion.core.events import Bar, Order, OrderRequest, OrderStatus, OrderType, Side, Tick
from xillion.core.instruments import ResolvedInstrument
from xillion.core.market_calendar import IST

DEFAULT_PARAMS = {p.name: p.default for p in CreditSpreadWeeklyStrategy.params_schema}


class FakeContext:
    """Duck-typed StrategyContext -- implements exactly what the strategy
    calls. Fill prices/strikes are fixed so the resulting credit/width are
    known in advance (credit=20, width=100 -> 20% > the 15% minimum;
    loss/lot=(100-20)*65=5200, capital 10L @ 1% risk -> exactly 1 lot)."""

    LOT_SIZE = 65
    OPTION_PRICE = {"NIFTY_SHORT_PE": Decimal("30"), "NIFTY_LONG_PE": Decimal("10")}

    def __init__(self, params: dict, spot=Decimal("24000"), expiry: date | None = None) -> None:
        self.params = params
        self.state: dict = {}
        self.capital_allocated = Decimal("1000000")
        self.mode = "paper"
        self._spot = spot
        self._expiry = expiry or (csw._now_ist().date() + timedelta(days=params["entry_dte"]))
        self.placed: list[OrderRequest] = []
        self.cancelled: list[str] = []
        self.subscribed: list[tuple[str, str]] = []
        self.critical_alerts: list[tuple[str, str]] = []
        self._order_status_override: dict[str, OrderStatus] = {}

    # ── order placement (mirrors a synchronous paper/backtest fill) ────────
    async def place_order(self, request: OrderRequest) -> Order:
        self.placed.append(request)
        now = datetime.now(timezone.utc)
        status = self._order_status_override.get(request.symbol, OrderStatus.FILLED)
        price = self.OPTION_PRICE.get(request.symbol, Decimal("10"))
        return Order(
            client_order_id=request.client_order_id, symbol=request.symbol, side=request.side,
            quantity=request.quantity, order_type=request.order_type, status=status,
            submitted_at=now, updated_at=now, broker_order_id=f"B-{uuid4().hex[:6]}",
            filled_quantity=request.quantity if status == OrderStatus.FILLED else 0,
            avg_fill_price=price if status == OrderStatus.FILLED else None,
        )

    async def cancel_order(self, client_order_id: str) -> bool:
        self.cancelled.append(client_order_id)
        return True

    async def get_order(self, client_order_id: str):
        return None

    async def history(self, symbol: str, timeframe: str, lookback: int) -> list[Bar]:
        # Steady uptrend: close rises 1pt/bar, well above VWAP, 20EMA>50EMA.
        base = float(self._spot) - 60
        start = datetime.now(timezone.utc) - timedelta(minutes=15 * 60)
        return [
            Bar(symbol=symbol, timeframe=timeframe, ts=start + timedelta(minutes=15 * i),
                open=Decimal(str(base + i)), high=Decimal(str(base + i + 1)),
                low=Decimal(str(base + i - 1)), close=Decimal(str(base + i)), volume=1000)
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
            tradingsymbol=symbol, instrument_token=1, exchange="NFO", underlying=underlying,
            expiry=self._expiry, strike=strike, option_type=opt_type, lot_size=self.LOT_SIZE,
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
    now = datetime.now(timezone.utc)
    return Bar(symbol="NIFTY 50", timeframe="15m", ts=now, open=spot, high=spot, low=spot, close=spot, volume=1000)


@pytest.fixture(autouse=True)
def _freeze_entry_window(monkeypatch):
    """Pin wall-clock IST time to 10:00 (inside the 09:45-10:30 entry
    window) so the test is deterministic regardless of when it runs."""
    fixed = datetime(2026, 1, 6, 10, 0, tzinfo=IST)  # a Tuesday
    monkeypatch.setattr(csw, "_now_ist", lambda: fixed)
    return fixed


@pytest.mark.asyncio
async def test_entry_opens_a_correctly_sized_bull_put_spread():
    params = dict(DEFAULT_PARAMS, short_offset_strikes=2, width_strikes=2)
    ctx = FakeContext(params)
    strategy = CreditSpreadWeeklyStrategy()

    await strategy.on_bar(_entry_bar(ctx._spot), ctx)

    assert ctx.state["open_position"] is not None
    spec_state = ctx.state["open_position"]["spec"]
    assert spec_state["side"] == "BULL_PUT"
    assert spec_state["qty"] == 65  # 1 lot @ lot_size 65
    assert Decimal(spec_state["credit"]) == Decimal("20")
    assert Decimal(spec_state["width"]) == Decimal("100")
    # Long placed before short (leg-ordering discipline, CP11).
    assert ctx.placed[0].side == Side.BUY and "LONG" in ctx.placed[0].symbol
    assert ctx.placed[1].side == Side.SELL and "SHORT" in ctx.placed[1].symbol
    # Both legs subscribed for tick-driven protective-order monitoring.
    assert len(ctx.subscribed) == 2


@pytest.mark.asyncio
async def test_entry_skipped_when_position_too_large_for_account():
    params = dict(DEFAULT_PARAMS, short_offset_strikes=2, width_strikes=2, risk_pct=0.0001)
    ctx = FakeContext(params)
    strategy = CreditSpreadWeeklyStrategy()

    await strategy.on_bar(_entry_bar(ctx._spot), ctx)

    assert ctx.state.get("open_position") is None
    assert ctx.placed == []  # sizing rejected before any order was placed


@pytest.mark.asyncio
async def test_entry_skipped_outside_dte_window():
    params = dict(DEFAULT_PARAMS, short_offset_strikes=2, width_strikes=2, entry_dte=4)
    # Expiry 10 days out -> DTE won't equal 4.
    ctx = FakeContext(params, expiry=csw._now_ist().date() + timedelta(days=10))
    strategy = CreditSpreadWeeklyStrategy()

    await strategy.on_bar(_entry_bar(ctx._spot), ctx)

    assert ctx.state.get("open_position") is None
    assert ctx.placed == []


@pytest.mark.asyncio
async def test_stop_loss_closes_position_shorts_first():
    params = dict(DEFAULT_PARAMS, short_offset_strikes=2, width_strikes=2)
    ctx = FakeContext(params)
    strategy = CreditSpreadWeeklyStrategy()
    await strategy.on_bar(_entry_bar(ctx._spot), ctx)
    assert ctx.state["open_position"] is not None
    ctx.placed.clear()

    spec_state = ctx.state["open_position"]["spec"]
    # Spread value must breach 2x credit (20 -> 40) to trigger STOP.
    ctx.OPTION_PRICE[spec_state["short_symbol"]] = Decimal("55")
    ctx.OPTION_PRICE[spec_state["long_symbol"]] = Decimal("10")

    now = datetime.now(timezone.utc)
    await strategy.on_tick(Tick(symbol=spec_state["short_symbol"], ltp=Decimal("55"), ltt=now), ctx)
    await strategy.on_tick(Tick(symbol=spec_state["long_symbol"], ltp=Decimal("10"), ltt=now), ctx)

    assert ctx.state["open_position"] is None  # closed
    # Shorts-first exit ordering: the SHORT leg's closing BUY is placed first.
    assert ctx.placed[0].symbol == spec_state["short_symbol"] and ctx.placed[0].side == Side.BUY
    assert ctx.placed[1].symbol == spec_state["long_symbol"] and ctx.placed[1].side == Side.SELL


@pytest.mark.asyncio
async def test_profit_target_closes_position():
    params = dict(DEFAULT_PARAMS, short_offset_strikes=2, width_strikes=2)
    ctx = FakeContext(params)
    strategy = CreditSpreadWeeklyStrategy()
    await strategy.on_bar(_entry_bar(ctx._spot), ctx)
    spec_state = ctx.state["open_position"]["spec"]
    ctx.placed.clear()

    # Spread value decays to <= 50% of credit (20 -> 10) -> TARGET.
    now = datetime.now(timezone.utc)
    await strategy.on_tick(Tick(symbol=spec_state["short_symbol"], ltp=Decimal("14"), ltt=now), ctx)
    await strategy.on_tick(Tick(symbol=spec_state["long_symbol"], ltp=Decimal("4"), ltt=now), ctx)

    assert ctx.state["open_position"] is None


@pytest.mark.asyncio
async def test_leg_failure_during_entry_does_not_leave_a_naked_short(monkeypatch):
    """The short leg's order is rejected after the long has already filled --
    the executor must retry once, and if that also fails, unwind the long
    rather than ever holding the short alone."""
    params = dict(DEFAULT_PARAMS, short_offset_strikes=2, width_strikes=2)
    ctx = FakeContext(params)
    strategy = CreditSpreadWeeklyStrategy()

    original_place = ctx.place_order

    async def flaky_place(request: OrderRequest):
        if "SHORT" in request.symbol and request.side == Side.SELL:
            now = datetime.now(timezone.utc)
            return Order(
                client_order_id=request.client_order_id, symbol=request.symbol, side=request.side,
                quantity=request.quantity, order_type=request.order_type, status=OrderStatus.REJECTED,
                submitted_at=now, updated_at=now, rejection_reason="simulated broker rejection",
            )
        return await original_place(request)

    monkeypatch.setattr(ctx, "place_order", flaky_place)

    await strategy.on_bar(_entry_bar(ctx._spot), ctx)

    assert ctx.state.get("open_position") is None  # never registered as open
    # Long was bought, then sold back to flatten -- never left holding a
    # naked short at any point.
    long_orders = [r for r in ctx.placed if "LONG" in r.symbol]
    assert [o.side for o in long_orders] == [Side.BUY, Side.SELL]
    short_fills = [r for r in ctx.placed if "SHORT" in r.symbol]
    assert all(r.side == Side.SELL for r in short_fills)  # short was attempted, never actually held
