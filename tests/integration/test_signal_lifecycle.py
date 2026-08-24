"""
Integration test: alert mode's entry -> target/stop-loss -> exit lifecycle
(CP4). Before this, signal_log had no ENTER/EXIT distinction or way to link
an exit back to the entry it closes -- every alert was a one-shot fire.
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from brokers._dummy import DummyBroker
from xillion.core.events import Side, Tick
from xillion.core.plugin_loader import PluginRegistry
from xillion.core.risk import RiskManager
from xillion.core.strategy_base import Strategy, StrategyContext
from xillion.data.bus import MarketDataBus
from xillion.db.models import SignalLog
from xillion.db.session import get_session_factory, init_db
from xillion.engine.strategy_engine import StrategyEngine


class _FakeNotifier:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    async def alert(self, title: str, body: str, severity: str = "info") -> None:
        self.messages.append((title, body))


def _tick(symbol: str, ltp: float) -> Tick:
    return Tick(symbol=symbol, ltp=Decimal(str(ltp)), ltt=datetime.now(timezone.utc))


class _EntryThenExitStrategy(Strategy):
    """Enters once on the first tick, exits on the second -- same tag both
    times, so the framework should auto-link the exit to the entry."""
    name = "Entry Then Exit Test Strategy"
    timeframe = "1m"
    instruments = ["NIFTY 50"]

    async def on_tick(self, tick: Tick, ctx: StrategyContext) -> None:
        if not ctx.state.get("entered"):
            ctx.state["entered"] = True
            await ctx.alert_entry(
                tick.symbol, Side.BUY, price=tick.ltp,
                target=tick.ltp + 100, stop_loss=tick.ltp - 50, tag="setup_1",
            )
        elif not ctx.state.get("exited"):
            ctx.state["exited"] = True
            await ctx.alert_exit(tick.symbol, Side.SELL, price=tick.ltp, tag="setup_1")


class _TwoFullCyclesStrategy(Strategy):
    """Enter/exit twice in a row, same tag both times, on one instance --
    the second exit must link to the second (still-open) entry, not the
    first one (already closed by the first exit)."""
    name = "Two Full Cycles Test Strategy"
    timeframe = "1m"
    instruments = ["NIFTY 50"]

    async def on_tick(self, tick: Tick, ctx: StrategyContext) -> None:
        step = ctx.state.get("step", 0)
        if step == 0:
            await ctx.alert_entry(tick.symbol, Side.BUY, price=tick.ltp, tag="repeated_tag")
        elif step == 1:
            await ctx.alert_exit(tick.symbol, Side.SELL, price=tick.ltp, tag="repeated_tag")
        elif step == 2:
            await ctx.alert_entry(tick.symbol, Side.BUY, price=tick.ltp, tag="repeated_tag")
        elif step == 3:
            await ctx.alert_exit(tick.symbol, Side.SELL, price=tick.ltp, tag="repeated_tag")
        ctx.state["step"] = step + 1


class _ExitWithNoEntryStrategy(Strategy):
    """Fires a bare EXIT with a tag that was never entered."""
    name = "Exit With No Entry Test Strategy"
    timeframe = "1m"
    instruments = ["NIFTY 50"]

    async def on_tick(self, tick: Tick, ctx: StrategyContext) -> None:
        if not ctx.state.get("fired"):
            ctx.state["fired"] = True
            await ctx.alert_exit(tick.symbol, Side.SELL, price=tick.ltp, tag="never_entered")


async def _spawn(monkeypatch, strategy_cls, instance_id: str, notifier=None):
    monkeypatch.setattr("xillion.engine.strategy_engine.is_market_open", lambda *a, **k: True)
    await init_db()

    registry = PluginRegistry()
    registry.strategies[strategy_cls.name] = strategy_cls

    bus = MarketDataBus()
    engine = StrategyEngine(bus=bus, risk_manager=RiskManager())
    engine.set_registry(registry)

    await engine.spawn(
        instance_id=instance_id,
        strategy_name=strategy_cls.name,
        broker=DummyBroker(),
        instruments=["NIFTY 50"],
        timeframe="1m",
        capital=Decimal("100000"),
        params={},
        mode="alert",
        notifier=notifier or _FakeNotifier(),
    )
    return bus


@pytest.mark.asyncio
async def test_exit_auto_links_to_its_entry_via_tag(monkeypatch):
    instance_id = "test-entry-exit-instance"
    bus = await _spawn(monkeypatch, _EntryThenExitStrategy, instance_id)

    await bus.publish_tick(_tick("NIFTY 50", 25000.0))  # -> ENTER
    await bus.publish_tick(_tick("NIFTY 50", 25080.0))  # -> EXIT

    async with get_session_factory()() as session:
        rows = (await session.execute(
            select(SignalLog).where(SignalLog.strategy_instance_id == instance_id).order_by(SignalLog.id)
        )).scalars().all()

    assert len(rows) == 2
    entry, exit_ = rows
    assert entry.signal_type == "ENTER"
    assert entry.tag == "setup_1"
    assert entry.target_price == 25100.0
    assert entry.stop_loss_price == 24950.0
    assert entry.parent_signal_id is None

    assert exit_.signal_type == "EXIT"
    assert exit_.tag == "setup_1"
    assert exit_.parent_signal_id == entry.id  # auto-linked by matching tag


@pytest.mark.asyncio
async def test_repeated_tag_links_exit_to_the_still_open_entry_not_an_older_closed_one(monkeypatch):
    """Same tag reused across two full entry/exit cycles on ONE instance:
    the second exit must link to the second entry, not accidentally re-link
    to the first (already-closed) one."""
    instance_id = "test-repeated-tag-instance"
    bus = await _spawn(monkeypatch, _TwoFullCyclesStrategy, instance_id)

    await bus.publish_tick(_tick("NIFTY 50", 25000.0))  # ENTER #1
    await bus.publish_tick(_tick("NIFTY 50", 25080.0))  # EXIT #1 (closes #1)
    await bus.publish_tick(_tick("NIFTY 50", 26000.0))  # ENTER #2
    await bus.publish_tick(_tick("NIFTY 50", 26080.0))  # EXIT #2 (must close #2, not #1)

    async with get_session_factory()() as session:
        rows = (await session.execute(
            select(SignalLog).where(SignalLog.strategy_instance_id == instance_id).order_by(SignalLog.id)
        )).scalars().all()

    assert len(rows) == 4
    entry1, exit1, entry2, exit2 = rows
    assert exit1.parent_signal_id == entry1.id
    assert exit2.parent_signal_id == entry2.id
    assert exit2.parent_signal_id != entry1.id


@pytest.mark.asyncio
async def test_exit_with_no_matching_entry_is_persisted_unlinked_not_dropped(monkeypatch):
    instance_id = "test-orphan-exit-instance"
    bus = await _spawn(monkeypatch, _ExitWithNoEntryStrategy, instance_id)

    await bus.publish_tick(_tick("NIFTY 50", 25000.0))

    async with get_session_factory()() as session:
        rows = (await session.execute(
            select(SignalLog).where(SignalLog.strategy_instance_id == instance_id)
        )).scalars().all()

    assert len(rows) == 1
    assert rows[0].signal_type == "EXIT"
    assert rows[0].parent_signal_id is None  # no matching open entry -- stored, not linked or dropped


@pytest.mark.asyncio
async def test_notifier_body_includes_target_and_stop_loss(monkeypatch):
    notifier = _FakeNotifier()
    instance_id = "test-notify-body-instance"
    bus = await _spawn(monkeypatch, _EntryThenExitStrategy, instance_id, notifier=notifier)

    await bus.publish_tick(_tick("NIFTY 50", 25000.0))

    assert len(notifier.messages) == 1
    _, body = notifier.messages[0]
    assert "target" in body.lower()
    assert "stop-loss" in body.lower()
