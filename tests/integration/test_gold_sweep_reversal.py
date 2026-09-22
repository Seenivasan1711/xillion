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

from strategies.gold_sweep_reversal import GoldSweepReversal, _confidence_score
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

    async def alert_exit(self, symbol, side, *, price=None, tag=None, reason=None) -> Order:
        return await self.place_order(
            OrderRequest(
                symbol=symbol,
                side=side,
                quantity=1,
                order_type=OrderType.MARKET,
                price=price,
                tag=tag,
                signal_type="EXIT",
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


@pytest.mark.asyncio
async def test_alert_mode_on_tick_fires_exit_alert_on_target_hit():
    strat = GoldSweepReversal()
    ctx = FakeContext(DEFAULT_PARAMS, _base_history(), mode="alert")
    await strat.on_start(ctx)
    await strat.on_bar(_bar(_london(9, 0), 2629, 2632, 2628, 2631.5), ctx)
    await strat.on_bar(_bar(_london(9, 5), 2630.5, 2629.5, 2628.5, 2629.0), ctx)  # SHORT, tp=2621.5
    assert len(ctx.placed) == 1
    assert len(ctx.state["alert_positions"]) == 1

    await strat.on_tick(_tick(_london(9, 30), 2621.5), ctx)

    assert len(ctx.placed) == 2  # entry + exit alert, no real orders either way
    exit_req = ctx.placed[1]
    assert exit_req.signal_type == "EXIT"
    assert exit_req.tag == "Asian High"  # same tag as the entry -- pairs in signal_log
    assert exit_req.side == Side.BUY  # closing a short = buy side
    assert float(exit_req.price) == 2621.5
    assert "WIN" in exit_req.reason
    assert "target hit" in exit_req.reason
    assert ctx.state["alert_positions"] == []  # resolved, no longer watched
    assert ctx.state["open_position"] is None  # unaffected -- alert mode never uses this slot


@pytest.mark.asyncio
async def test_alert_mode_on_tick_fires_exit_alert_on_stop_hit():
    strat = GoldSweepReversal()
    ctx = FakeContext(DEFAULT_PARAMS, _base_history(), mode="alert")
    await strat.on_start(ctx)
    await strat.on_bar(_bar(_london(9, 0), 2629, 2632, 2628, 2631.5), ctx)
    await strat.on_bar(_bar(_london(9, 5), 2630.5, 2629.5, 2628.5, 2629.0), ctx)  # SHORT, sl=2632.5

    await strat.on_tick(_tick(_london(9, 10), 2632.5), ctx)

    exit_req = ctx.placed[1]
    assert exit_req.signal_type == "EXIT"
    assert "LOSS" in exit_req.reason
    assert "stopped out" in exit_req.reason
    assert ctx.state["alert_positions"] == []


@pytest.mark.asyncio
async def test_alert_mode_on_tick_ignores_price_between_sl_and_tp():
    strat = GoldSweepReversal()
    ctx = FakeContext(DEFAULT_PARAMS, _base_history(), mode="alert")
    await strat.on_start(ctx)
    await strat.on_bar(_bar(_london(9, 0), 2629, 2632, 2628, 2631.5), ctx)
    await strat.on_bar(_bar(_london(9, 5), 2630.5, 2629.5, 2628.5, 2629.0), ctx)

    await strat.on_tick(_tick(_london(9, 10), 2627.0), ctx)  # between tp (2621.5) and sl (2632.5)

    assert len(ctx.placed) == 1  # entry only, no exit yet
    assert len(ctx.state["alert_positions"]) == 1


@pytest.mark.asyncio
async def test_max_sl_pts_caps_a_wide_wick_extreme():
    strat = GoldSweepReversal()
    params = dict(DEFAULT_PARAMS)
    params["max_sl_pts"] = 5.0  # tighter than this sweep's real wick extreme
    ctx = FakeContext(params, _base_history())
    await strat.on_start(ctx)

    # Sweep bar pokes above Asian High (2630) to 2645 -- kept below PD High
    # (2650, from _base_history()) so it doesn't *also* poke-and-instantly-
    # reclaim that unrelated level within this same bar and steal the test.
    await strat.on_bar(_bar(_london(9, 0), 2629, 2645, 2628, 2631.5), ctx)
    await strat.on_bar(_bar(_london(9, 5), 2630.5, 2629.5, 2628.5, 2629.0), ctx)

    assert len(ctx.placed) == 1
    req = ctx.placed[0]
    assert req.tag == "Asian High"
    # Uncapped, sl would be max(2645.5, 2632.0) = 2645.5 (16+ pts away).
    # Capped at max_sl_pts=5.0 from entry (2629.0): sl = 2634.0.
    assert float(req.stop_loss_price) == pytest.approx(2634.0)


@pytest.mark.asyncio
async def test_use_session_levels_adds_pd_london_and_ny_levels():
    strat = GoldSweepReversal()
    params = dict(DEFAULT_PARAMS)
    params["use_session_levels"] = True
    history = [
        _bar(
            datetime(2026, 1, 5, 9, tzinfo=UTC), 2656, 2660, 2655, 2658
        ),  # prev-day London (07-13 UTC)
        _bar(
            datetime(2026, 1, 5, 14, tzinfo=UTC), 2666, 2670, 2665, 2668
        ),  # prev-day NY-overlap (13-17 UTC)
        _bar(datetime(2026, 1, 6, 2, tzinfo=UTC), 2615, 2630, 2610, 2620),  # today's Asian
    ]
    ctx = FakeContext(params, history)
    await strat.on_start(ctx)

    # Trigger the day roll; this bar itself shouldn't sweep anything.
    await strat.on_bar(_bar(_london(9, 0), 2620, 2621, 2619, 2620), ctx)
    assert ctx.placed == []

    levels = ctx.state["levels"]
    assert levels["PD London High"]["price"] == 2660.0
    assert levels["PD London Low"]["price"] == 2655.0
    assert levels["PD NY-overlap High"]["price"] == 2670.0
    assert levels["PD NY-overlap Low"]["price"] == 2665.0
    # Whole-day PD High/Low still spans both sessions, unchanged.
    assert levels["PD High"]["price"] == 2670.0
    assert levels["PD Low"]["price"] == 2655.0
    assert levels["Asian High"]["price"] == 2630.0
    assert levels["Asian Low"]["price"] == 2610.0


@pytest.mark.asyncio
async def test_use_session_levels_off_by_default_no_new_levels():
    strat = GoldSweepReversal()
    history = [
        _bar(datetime(2026, 1, 5, 9, tzinfo=UTC), 2656, 2660, 2655, 2658),
        _bar(datetime(2026, 1, 5, 14, tzinfo=UTC), 2666, 2670, 2665, 2668),
        _bar(datetime(2026, 1, 6, 2, tzinfo=UTC), 2615, 2630, 2610, 2620),
    ]
    ctx = FakeContext(DEFAULT_PARAMS, history)  # use_session_levels defaults False
    await strat.on_start(ctx)
    await strat.on_bar(_bar(_london(9, 0), 2620, 2621, 2619, 2620), ctx)

    assert set(ctx.state["levels"].keys()) == {"Asian High", "Asian Low", "PD High", "PD Low"}


@pytest.mark.asyncio
async def test_prev_day_lookback_days_widens_pd_range():
    strat = GoldSweepReversal()
    params = dict(DEFAULT_PARAMS)
    params["prev_day_lookback_days"] = 3
    history = [
        _bar(datetime(2026, 1, 3, 10, tzinfo=UTC), 2600, 2640, 2590, 2620),  # 3 days back
        _bar(
            datetime(2026, 1, 4, 10, tzinfo=UTC), 2610, 2625, 2560, 2600
        ),  # 2 days back -- widest low
        _bar(
            datetime(2026, 1, 5, 10, tzinfo=UTC), 2600, 2650, 2595, 2620
        ),  # 1 day back -- widest high
        _bar(datetime(2026, 1, 6, 2, tzinfo=UTC), 2615, 2630, 2612, 2620),  # today's Asian
    ]
    ctx = FakeContext(params, history)
    await strat.on_start(ctx)
    await strat.on_bar(_bar(_london(9, 0), 2620, 2621, 2619, 2620), ctx)

    levels = ctx.state["levels"]
    assert levels["PD High"]["price"] == 2650.0  # from 01-05
    assert levels["PD Low"]["price"] == 2560.0  # from 01-04


@pytest.mark.asyncio
async def test_prev_day_lookback_days_default_matches_original_single_day():
    strat = GoldSweepReversal()
    history = [
        _bar(
            datetime(2026, 1, 3, 10, tzinfo=UTC), 2600, 2640, 2590, 2620
        ),  # should be ignored, 2+ days back
        _bar(
            datetime(2026, 1, 5, 10, tzinfo=UTC), 2600, 2650, 2595, 2620
        ),  # only this counts, default lookback=1
        _bar(datetime(2026, 1, 6, 2, tzinfo=UTC), 2615, 2630, 2612, 2620),
    ]
    ctx = FakeContext(DEFAULT_PARAMS, history)  # prev_day_lookback_days defaults to 1
    await strat.on_start(ctx)
    await strat.on_bar(_bar(_london(9, 0), 2620, 2621, 2619, 2620), ctx)

    levels = ctx.state["levels"]
    assert levels["PD High"]["price"] == 2650.0
    assert levels["PD Low"]["price"] == 2595.0


def test_confidence_score_penalizes_wide_stop():
    tight_score, _ = _confidence_score(
        sl_pts=3.0,
        min_sl_pts=3.0,
        max_sl_pts=100.0,
        reclaim_bars=0,  # isolate the SL component -- no reclaim-speed penalty either
        sweep_lookback_bars=3,
        recent_losses_in_a_row=0,
    )
    wide_score, _ = _confidence_score(
        sl_pts=95.0,
        min_sl_pts=3.0,
        max_sl_pts=100.0,
        reclaim_bars=0,
        sweep_lookback_bars=3,
        recent_losses_in_a_row=0,
    )
    assert tight_score > wide_score
    assert tight_score == 100  # sl at the floor -- no SL penalty at all


def test_confidence_score_penalizes_loss_streak():
    no_streak, _ = _confidence_score(
        sl_pts=3.0,
        min_sl_pts=3.0,
        max_sl_pts=100.0,
        reclaim_bars=1,
        sweep_lookback_bars=3,
        recent_losses_in_a_row=0,
    )
    with_streak, reasons = _confidence_score(
        sl_pts=3.0,
        min_sl_pts=3.0,
        max_sl_pts=100.0,
        reclaim_bars=1,
        sweep_lookback_bars=3,
        recent_losses_in_a_row=3,
    )
    assert with_streak < no_streak
    assert any("loss(es) in a row" in r for r in reasons)


def test_confidence_score_clamped_to_0_100_range():
    score, _ = _confidence_score(
        sl_pts=500.0,
        min_sl_pts=3.0,
        max_sl_pts=100.0,
        reclaim_bars=99,
        sweep_lookback_bars=3,
        recent_losses_in_a_row=99,
    )
    assert 0 <= score <= 100


@pytest.mark.asyncio
async def test_confidence_score_off_by_default_not_in_reason():
    strat = GoldSweepReversal()
    ctx = FakeContext(DEFAULT_PARAMS, _base_history())  # enable_confidence_score defaults False
    await strat.on_start(ctx)
    await strat.on_bar(_bar(_london(9, 0), 2629, 2632, 2628, 2631.5), ctx)
    await strat.on_bar(_bar(_london(9, 5), 2630.5, 2629.5, 2628.5, 2629.0), ctx)

    assert "Setup confidence" not in ctx.placed[0].reason


@pytest.mark.asyncio
async def test_confidence_score_appended_to_reason_when_enabled():
    strat = GoldSweepReversal()
    params = dict(DEFAULT_PARAMS)
    params["enable_confidence_score"] = True
    ctx = FakeContext(params, _base_history())
    await strat.on_start(ctx)
    await strat.on_bar(_bar(_london(9, 0), 2629, 2632, 2628, 2631.5), ctx)
    await strat.on_bar(_bar(_london(9, 5), 2630.5, 2629.5, 2628.5, 2629.0), ctx)

    reason = ctx.placed[0].reason
    assert "Setup confidence:" in reason
    assert "/100" in reason
    assert "does not gate this entry" in reason
