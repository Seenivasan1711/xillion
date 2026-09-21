"""
GoldSweepReversal (Gold Lane B1, Sweep-Reversal card): drives on_bar
directly against a hand-built fake StrategyContext, proving the sweep-
detection/reclaim/sizing math matches the card exactly and that the daily
gates (session window, max trades/day, cooldown) actually bind. Mirrors
tests/integration/test_credit_spread_strategy.py's FakeContext pattern.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from strategies.gold_sweep_reversal import GoldSweepReversal
from xillion.core.events import Bar, Order, OrderRequest, OrderStatus, OrderType, Side, Tick

DEFAULT_PARAMS = {p.name: p.default for p in GoldSweepReversal.params_schema}
SYMBOL = "XAUUSD"
TF = "5m"


class FakeContext:
    """Duck-typed StrategyContext -- implements exactly what the strategy
    calls. `history()` returns a fixed bar list covering "yesterday" (a
    known high/low) and "today's" Asian session (a different known
    high/low), regardless of the requested lookback, so daily-level math is
    deterministic and independently checkable by hand."""

    def __init__(self, params: dict, history_bars: list[Bar], mode: str = "alert") -> None:
        self.params = dict(params)
        self.state: dict = {}
        self.mode = mode
        self._history_bars = history_bars
        self.placed: list[OrderRequest] = []
        self.notifications: list[tuple[str, str, str]] = []
        # Tests set this before triggering a bar/tick that should fill --
        # buy()/sell() below are market orders (no price param), so this is
        # how a test controls what "fill price" the strategy sees.
        self.next_fill_price: Decimal | None = None

    async def place_order(self, request: OrderRequest) -> Order:
        self.placed.append(request)
        now = datetime.now(UTC)
        return Order(
            client_order_id=request.client_order_id,
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            order_type=request.order_type,
            status=OrderStatus.PENDING,
            submitted_at=now,
            updated_at=now,
        )

    async def alert_entry(
        self, symbol, side, *, price=None, target=None, stop_loss=None, tag=None, reason=None
    ) -> Order:
        return await self.place_order(
            OrderRequest(
                symbol=symbol,
                side=side,
                quantity=1,
                order_type=OrderType.MARKET,
                price=price,
                tag=tag,
                signal_type="ENTER",
                target_price=target,
                stop_loss_price=stop_loss,
                reason=reason,
            )
        )

    async def _fill(self, symbol, side, qty, tag) -> Order:
        order = await self.place_order(
            OrderRequest(
                symbol=symbol, side=side, quantity=qty, order_type=OrderType.MARKET, tag=tag
            )
        )
        order.avg_fill_price = self.next_fill_price
        return order

    async def buy(self, symbol, qty, *, price=None, tag=None) -> Order:
        return await self._fill(symbol, Side.BUY, qty, tag)

    async def sell(self, symbol, qty, *, price=None, tag=None) -> Order:
        return await self._fill(symbol, Side.SELL, qty, tag)

    async def notify(self, title: str, body: str, severity: str = "info") -> None:
        self.notifications.append((title, body, severity))

    async def history(self, symbol: str, timeframe: str, lookback: int) -> list[Bar]:
        return self._history_bars

    def log(self, level: str, message: str, **fields) -> None:
        pass


def _bar(ts: datetime, o: float, h: float, low: float, c: float) -> Bar:
    return Bar(
        symbol=SYMBOL,
        timeframe=TF,
        ts=ts,
        open=Decimal(str(o)),
        high=Decimal(str(h)),
        low=Decimal(str(low)),
        close=Decimal(str(c)),
        volume=0,
    )


# Previous day (2026-01-05, whole day): high 2650.00 / low 2590.00.
# Today's Asian session (2026-01-06, 00:00-07:00 UTC): high 2630.00 / low 2610.00.
# Neither range overlaps the other, so each of the 4 levels is independently
# checkable.
def _base_history() -> list[Bar]:
    bars = []
    prev_day = datetime(2026, 1, 5, tzinfo=UTC)
    bars.append(_bar(prev_day.replace(hour=10), 2600, 2650, 2595, 2620))  # prev-day high
    bars.append(_bar(prev_day.replace(hour=14), 2610, 2615, 2590, 2600))  # prev-day low
    today_asian = datetime(2026, 1, 6, tzinfo=UTC)
    bars.append(_bar(today_asian.replace(hour=2), 2615, 2630, 2612, 2620))  # asian high
    bars.append(_bar(today_asian.replace(hour=5), 2618, 2622, 2610, 2615))  # asian low
    return bars


def _london(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 1, 6, hour, minute, tzinfo=UTC)


@pytest.mark.asyncio
async def test_sweep_above_asian_high_fires_short_with_correct_math():
    strat = GoldSweepReversal()
    ctx = FakeContext(DEFAULT_PARAMS, _base_history())
    await strat.on_start(ctx)

    # First bar of the day, inside the London window (07:00-13:00 UTC) --
    # triggers _roll_day, then itself pokes above Asian High (2630).
    await strat.on_bar(_bar(_london(9, 0), 2629, 2632, 2628, 2631.5), ctx)
    assert ctx.state["levels"]["Asian High"]["price"] == 2630.0
    assert ctx.state["levels"]["Asian Low"]["price"] == 2610.0
    assert ctx.state["levels"]["PD High"]["price"] == 2650.0
    assert ctx.state["levels"]["PD Low"]["price"] == 2590.0
    assert not ctx.placed  # still outside (2631.5 > 2630) -- pending, no trigger yet

    # Reclaim close back inside -- fires.
    await strat.on_bar(_bar(_london(9, 5), 2630.5, 2629.5, 2628.5, 2629.0), ctx)

    assert len(ctx.placed) == 1
    req = ctx.placed[0]
    assert req.side == Side.SELL
    assert req.signal_type == "ENTER"
    assert req.tag == "Asian High"
    assert float(req.price) == 2629.0
    # extreme = 2632.0 (the sweep bar's high); sl = max(2632.5, 2629+3.0=2632.0) = 2632.5
    assert float(req.stop_loss_price) == 2632.5
    # tp = entry - 7.5
    assert float(req.target_price) == pytest.approx(2621.5)
    assert "Asian High" in req.reason
    assert "SHORT" in req.reason
    assert "2632.00" in req.reason  # the extreme, spelled out in the explanation
    assert ctx.state["trades_today"] == 1


@pytest.mark.asyncio
async def test_sweep_below_asian_low_fires_long_with_correct_math():
    strat = GoldSweepReversal()
    ctx = FakeContext(DEFAULT_PARAMS, _base_history())
    await strat.on_start(ctx)

    await strat.on_bar(_bar(_london(9, 0), 2611, 2612, 2607.0, 2608.5), ctx)  # pokes below 2610
    assert not ctx.placed

    await strat.on_bar(
        _bar(_london(9, 5), 2608.5, 2609.5, 2608, 2611.0), ctx
    )  # reclaims above 2610

    assert len(ctx.placed) == 1
    req = ctx.placed[0]
    assert req.side == Side.BUY
    assert req.tag == "Asian Low"
    assert float(req.price) == 2611.0
    # extreme = 2607.0; sl = min(2606.5, 2611-3.0=2608.0) = 2606.5
    assert float(req.stop_loss_price) == 2606.5
    assert float(req.target_price) == pytest.approx(2618.5)
    assert "LONG" in req.reason


@pytest.mark.asyncio
async def test_no_trigger_outside_trading_window():
    strat = GoldSweepReversal()
    ctx = FakeContext(DEFAULT_PARAMS, _base_history())
    await strat.on_start(ctx)

    # 14:00 UTC is past the 07:00-13:00 window -- same sweep+reclaim shape
    # as the passing test above, but must NOT fire.
    outside = datetime(2026, 1, 6, 14, 0, tzinfo=UTC)
    await strat.on_bar(_bar(outside, 2629, 2632, 2628, 2631.5), ctx)
    await strat.on_bar(_bar(outside + timedelta(minutes=5), 2630.5, 2629.5, 2628.5, 2629.0), ctx)

    assert ctx.placed == []


@pytest.mark.asyncio
async def test_max_trades_per_day_caps_entries():
    strat = GoldSweepReversal()
    params = dict(DEFAULT_PARAMS)
    params["max_trades_per_day"] = 1
    params["cooldown_minutes"] = 0
    ctx = FakeContext(params, _base_history())
    await strat.on_start(ctx)

    # First sweep -- fires (uses up the day's one allowed trade).
    await strat.on_bar(_bar(_london(9, 0), 2629, 2632, 2628, 2631.5), ctx)
    await strat.on_bar(_bar(_london(9, 5), 2630.5, 2629.5, 2628.5, 2629.0), ctx)
    assert len(ctx.placed) == 1

    # Second, independent sweep (Asian Low) later the same day -- must be
    # suppressed by the daily cap.
    await strat.on_bar(_bar(_london(10, 0), 2611, 2612, 2607.0, 2608.5), ctx)
    await strat.on_bar(_bar(_london(10, 5), 2608.5, 2609.5, 2608, 2611.0), ctx)
    assert len(ctx.placed) == 1


@pytest.mark.asyncio
async def test_cooldown_blocks_immediate_second_entry():
    strat = GoldSweepReversal()
    params = dict(DEFAULT_PARAMS)
    params["cooldown_minutes"] = 10
    ctx = FakeContext(params, _base_history())
    await strat.on_start(ctx)

    await strat.on_bar(_bar(_london(9, 0), 2629, 2632, 2628, 2631.5), ctx)
    await strat.on_bar(_bar(_london(9, 5), 2630.5, 2629.5, 2628.5, 2629.0), ctx)
    assert len(ctx.placed) == 1

    # A fresh Asian-Low sweep+reclaim completes at 09:09 -- still inside the
    # 10-min cooldown from the 09:05 entry (clears at 09:15), so it must be
    # suppressed even though the mechanical trigger condition is met.
    await strat.on_bar(_bar(_london(9, 7), 2611, 2612, 2607.0, 2608.5), ctx)
    await strat.on_bar(_bar(_london(9, 9), 2608.5, 2609.5, 2608, 2611.0), ctx)
    assert len(ctx.placed) == 1


def _tick(ts: datetime, ltp: float) -> Tick:
    return Tick(symbol=SYMBOL, ltp=Decimal(str(ltp)), ltt=ts)


@pytest.mark.asyncio
async def test_paper_mode_places_real_entry_and_notifies_instead_of_alerting():
    strat = GoldSweepReversal()
    ctx = FakeContext(DEFAULT_PARAMS, _base_history(), mode="paper")
    ctx.next_fill_price = Decimal("2629.0")
    await strat.on_start(ctx)

    await strat.on_bar(_bar(_london(9, 0), 2629, 2632, 2628, 2631.5), ctx)
    await strat.on_bar(_bar(_london(9, 5), 2630.5, 2629.5, 2628.5, 2629.0), ctx)

    assert len(ctx.placed) == 1
    req = ctx.placed[0]
    assert req.side == Side.SELL
    assert req.signal_type is None  # a real buy/sell, not alert_entry's OrderRequest shape
    # lot_size 0.08 -> 8 (hundredths-of-a-lot, same convention as MT5)
    assert req.quantity == 8

    pos = ctx.state["open_position"]
    assert pos == {
        "symbol": "XAUUSD",
        "side": "SELL",
        "qty": 8,
        "entry": 2629.0,
        "sl": 2632.5,
        "tp": 2621.5,
        "level": "Asian High",
        "entry_time": pos["entry_time"],  # just check it's present/consistent
    }
    assert len(ctx.notifications) == 1
    title, body, severity = ctx.notifications[0]
    assert "Entered SELL" in title
    assert severity == "info"


@pytest.mark.asyncio
async def test_paper_mode_on_tick_closes_on_target_hit_and_notifies_win():
    strat = GoldSweepReversal()
    ctx = FakeContext(DEFAULT_PARAMS, _base_history(), mode="paper")
    ctx.next_fill_price = Decimal("2629.0")
    await strat.on_start(ctx)
    await strat.on_bar(_bar(_london(9, 0), 2629, 2632, 2628, 2631.5), ctx)
    await strat.on_bar(_bar(_london(9, 5), 2630.5, 2629.5, 2628.5, 2629.0), ctx)
    assert ctx.state["open_position"] is not None

    # SHORT entry, tp=2621.5 -- price falling to/through it should close as a win.
    ctx.next_fill_price = Decimal("2621.5")
    await strat.on_tick(_tick(_london(9, 30), 2621.5), ctx)

    assert ctx.state["open_position"] is None
    # 2 placed orders total: the entry + the closing exit.
    assert len(ctx.placed) == 2
    assert ctx.placed[1].side == Side.BUY  # closing a short = buy back
    assert ctx.placed[1].quantity == 8

    assert len(ctx.notifications) == 2
    title, body, severity = ctx.notifications[1]
    assert "WIN" in title
    assert "target hit" in body
    assert severity == "info"


@pytest.mark.asyncio
async def test_paper_mode_on_tick_closes_on_stop_hit_and_notifies_loss():
    strat = GoldSweepReversal()
    ctx = FakeContext(DEFAULT_PARAMS, _base_history(), mode="paper")
    ctx.next_fill_price = Decimal("2629.0")
    await strat.on_start(ctx)
    await strat.on_bar(_bar(_london(9, 0), 2629, 2632, 2628, 2631.5), ctx)
    await strat.on_bar(_bar(_london(9, 5), 2630.5, 2629.5, 2628.5, 2629.0), ctx)

    # SHORT entry, sl=2632.5 -- price rising through it should close as a loss.
    ctx.next_fill_price = Decimal("2632.5")
    await strat.on_tick(_tick(_london(9, 10), 2632.5), ctx)

    assert ctx.state["open_position"] is None
    title, body, severity = ctx.notifications[1]
    assert "LOSS" in title
    assert "stopped out" in body
    assert severity == "warn"


@pytest.mark.asyncio
async def test_paper_mode_ignores_ticks_when_no_position_open():
    strat = GoldSweepReversal()
    ctx = FakeContext(DEFAULT_PARAMS, _base_history(), mode="paper")
    await strat.on_start(ctx)
    # No entry has fired -- a tick at any price should be a no-op.
    await strat.on_tick(_tick(_london(9, 0), 2500.0), ctx)
    assert ctx.placed == []
    assert ctx.notifications == []


@pytest.mark.asyncio
async def test_paper_mode_blocks_new_entry_while_position_open():
    strat = GoldSweepReversal()
    params = dict(DEFAULT_PARAMS)
    params["cooldown_minutes"] = 0
    ctx = FakeContext(params, _base_history(), mode="paper")
    ctx.next_fill_price = Decimal("2629.0")
    await strat.on_start(ctx)
    await strat.on_bar(_bar(_london(9, 0), 2629, 2632, 2628, 2631.5), ctx)
    await strat.on_bar(_bar(_london(9, 5), 2630.5, 2629.5, 2628.5, 2629.0), ctx)
    assert len(ctx.placed) == 1

    # A second, independent sweep (Asian Low) while the first position is
    # still open -- must be suppressed even though max_trades_per_day (2)
    # and cooldown (0) would otherwise allow it.
    await strat.on_bar(_bar(_london(9, 10), 2611, 2612, 2607.0, 2608.5), ctx)
    await strat.on_bar(_bar(_london(9, 15), 2608.5, 2609.5, 2608, 2611.0), ctx)
    assert len(ctx.placed) == 1


@pytest.mark.asyncio
async def test_alert_mode_never_sets_open_position():
    strat = GoldSweepReversal()
    ctx = FakeContext(DEFAULT_PARAMS, _base_history(), mode="alert")
    await strat.on_start(ctx)
    await strat.on_bar(_bar(_london(9, 0), 2629, 2632, 2628, 2631.5), ctx)
    await strat.on_bar(_bar(_london(9, 5), 2630.5, 2629.5, 2628.5, 2629.0), ctx)

    assert len(ctx.placed) == 1
    assert ctx.state["open_position"] is None  # alert mode tracks no real position
    assert ctx.notifications == []  # alert mode uses alert_entry, not notify
