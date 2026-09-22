"""
JEV / LLM-assisted decision-making (2026-09-22, SESSION SPRINT item 17):
propose -> notify -> approve/reject. Approval must write through the exact
same update_instance_core a manual PATCH uses (verified by checking the
instance's real params_json changed, not just that the proposal row's
status flipped). Drives the route functions directly against a real
in-memory DB, same pattern as tests/integration/test_market_scheduler.py
and tests/integration/test_telegram_commands.py.
"""

import json
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI, HTTPException

from xillion.api.proposed_changes import (
    ProposeChangeRequest,
    approve_proposed_change,
    list_proposed_changes,
    propose_change,
    reject_proposed_change,
)
from xillion.core.plugin_loader import PluginRegistry
from xillion.core.risk import RiskManager
from xillion.core.strategy_base import ParamSpec, Strategy
from xillion.data.bus import MarketDataBus
from xillion.db.models import (
    BrokerClass,
    BrokerConnection,
    ProposedStrategyChange,
    StrategyClass,
    StrategyInstance,
)
from xillion.db.session import get_session_factory, init_db
from xillion.engine.strategy_engine import StrategyEngine
from xillion.notifications.telegram_commands import _handle_proposed_change_callback


class _FakeUser:
    username = "rakesh"


class _FakeNotifier:
    _chat_id = "123"
    _enabled = True

    def __init__(self) -> None:
        self.alerts: list[tuple[str, str, str]] = []
        self.buttoned: list[tuple[int, list]] = []
        self.edited: list[tuple[int, str]] = []
        self.answered: list[tuple[str, str]] = []
        self._next_message_id = 1

    async def alert(self, title: str, body: str, severity: str = "info") -> int:
        self.alerts.append((title, body, severity))
        mid = self._next_message_id
        self._next_message_id += 1
        return mid

    async def add_inline_buttons(self, message_id: int, buttons: list) -> None:
        self.buttoned.append((message_id, buttons))

    async def edit_message_text(self, message_id: int, text: str) -> None:
        self.edited.append((message_id, text))

    async def answer_callback_query(self, callback_id: str, text: str = "") -> None:
        self.answered.append((callback_id, text))


class _FakeRequest:
    def __init__(self, app: FastAPI) -> None:
        self.app = app


class _EchoStrategy(Strategy):
    timeframe = "5m"
    instruments = ["XAUUSD"]
    params_schema = [ParamSpec("tp_pts", "float", default=7.5)]


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def _make_app() -> FastAPI:
    app = FastAPI()
    registry = PluginRegistry()

    class _FakeLoader:
        def __init__(self, reg):
            self.registry = reg

    app.state.plugin_loader = _FakeLoader(registry)
    bus = MarketDataBus()
    app.state.bus = bus
    engine = StrategyEngine(bus=bus, risk_manager=RiskManager())
    engine.set_registry(registry)
    app.state.strategy_engine = engine
    app.state.broker_instances = {}
    app.state.telegram = _FakeNotifier()
    return app


async def _seed_instance(app: FastAPI, instance_id: str, name: str = "Gold Sweep-Reversal") -> str:
    await init_db()
    strategy_name = f"Proposed-Changes Test Strategy {instance_id}"
    app.state.plugin_loader.registry.strategies[strategy_name] = _EchoStrategy
    factory = get_session_factory()
    async with factory() as db:
        bc = BrokerClass(
            name=f"Dummy Broker {instance_id}",
            module_path="x",
            class_name="X",
            version="1.0.0",
            capabilities_json="{}",
            discovered_at=_now(),
            last_seen_at=_now(),
        )
        db.add(bc)
        await db.flush()
        conn = BrokerConnection(
            broker_class_id=bc.id,
            name=f"conn-{instance_id}",
            credentials_ref="PAPER",
            is_active=True,
            created_at=_now(),
            updated_at=_now(),
        )
        db.add(conn)
        sc = StrategyClass(
            name=strategy_name,
            module_path="x",
            class_name="X",
            version="1.0.0",
            params_schema_json="{}",
            code_hash="abc",
            discovered_at=_now(),
            last_seen_at=_now(),
        )
        db.add(sc)
        await db.flush()
        db.add(
            StrategyInstance(
                id=instance_id,
                strategy_class_id=sc.id,
                strategy_class_version="1.0.0",
                name=name,
                mode="alert",
                status="idle",
                broker_connection_id=conn.id,
                instruments_json='["XAUUSD"]',
                timeframe="5m",
                params_json=json.dumps({"tp_pts": 7.5}),
                capital_allocation=5000,
                risk_limits_json="{}",
                auto_start=False,
                created_at=_now(),
                updated_at=_now(),
            )
        )
        await db.commit()
    return instance_id


@pytest.mark.asyncio
async def test_propose_change_creates_pending_row_and_notifies():
    app = await _make_app()
    instance_id = await _seed_instance(app, "inst-p1")
    factory = get_session_factory()

    async with factory() as db:
        result = await propose_change(
            ProposeChangeRequest(
                instance_id=instance_id,
                params={"tp_pts": 10.0},
                reasoning="Backtest showed better Sharpe at tp_pts=10",
                proposed_by="JEV",
            ),
            _FakeRequest(app),
            db,
            _FakeUser(),
        )

    assert result["status"] == "pending"
    notifier: _FakeNotifier = app.state.telegram
    assert len(notifier.alerts) == 1
    assert "Backtest showed better Sharpe" in notifier.alerts[0][1]
    assert len(notifier.buttoned) == 1  # Approve/Reject buttons attached

    async with factory() as db:
        row = await db.get(ProposedStrategyChange, result["proposal_id"])
        assert row.status == "pending"
        assert json.loads(row.proposed_params_json) == {"tp_pts": 10.0}


@pytest.mark.asyncio
async def test_list_proposed_changes_filters_by_status():
    app = await _make_app()
    instance_id = await _seed_instance(app, "inst-p2")
    factory = get_session_factory()

    async with factory() as db:
        r1 = await propose_change(
            ProposeChangeRequest(instance_id=instance_id, params={"tp_pts": 8.0}, reasoning="a"),
            _FakeRequest(app),
            db,
            _FakeUser(),
        )
    async with factory() as db:
        await reject_proposed_change(r1["proposal_id"], db, _FakeUser())

    async with factory() as db:
        all_result = await list_proposed_changes(None, db, _FakeUser())
        pending_result = await list_proposed_changes("pending", db, _FakeUser())

    # Filter to this test's own instance -- the shared in-memory test DB
    # can carry rows over from other tests in this file.
    mine = [p for p in all_result["proposals"] if p["strategy_instance_id"] == instance_id]
    mine_pending = [
        p for p in pending_result["proposals"] if p["strategy_instance_id"] == instance_id
    ]
    assert len(mine) == 1
    assert mine[0]["status"] == "rejected"
    assert len(mine_pending) == 0


@pytest.mark.asyncio
async def test_approve_applies_params_through_the_same_update_path():
    app = await _make_app()
    instance_id = await _seed_instance(app, "inst-p3")
    factory = get_session_factory()

    async with factory() as db:
        proposed = await propose_change(
            ProposeChangeRequest(
                instance_id=instance_id, params={"tp_pts": 12.5}, reasoning="test"
            ),
            _FakeRequest(app),
            db,
            _FakeUser(),
        )

    async with factory() as db:
        result = await approve_proposed_change(
            proposed["proposal_id"], _FakeRequest(app), db, _FakeUser()
        )
    assert result["approved"] is True

    async with factory() as db:
        inst = await db.get(StrategyInstance, instance_id)
        assert json.loads(inst.params_json)["tp_pts"] == 12.5  # actually applied, not just marked

        row = await db.get(ProposedStrategyChange, proposed["proposal_id"])
        assert row.status == "approved"
        assert row.decided_by == "rakesh"


@pytest.mark.asyncio
async def test_reject_does_not_change_instance_params():
    app = await _make_app()
    instance_id = await _seed_instance(app, "inst-p4")
    factory = get_session_factory()

    async with factory() as db:
        proposed = await propose_change(
            ProposeChangeRequest(instance_id=instance_id, params={"tp_pts": 99.0}, reasoning="x"),
            _FakeRequest(app),
            db,
            _FakeUser(),
        )

    async with factory() as db:
        await reject_proposed_change(proposed["proposal_id"], db, _FakeUser())

    async with factory() as db:
        inst = await db.get(StrategyInstance, instance_id)
        assert json.loads(inst.params_json)["tp_pts"] == 7.5  # unchanged


@pytest.mark.asyncio
async def test_cannot_decide_an_already_decided_proposal_twice():
    app = await _make_app()
    instance_id = await _seed_instance(app, "inst-p5")
    factory = get_session_factory()

    async with factory() as db:
        proposed = await propose_change(
            ProposeChangeRequest(instance_id=instance_id, params={"tp_pts": 9.0}, reasoning="x"),
            _FakeRequest(app),
            db,
            _FakeUser(),
        )

    async with factory() as db:
        await approve_proposed_change(proposed["proposal_id"], _FakeRequest(app), db, _FakeUser())

    async with factory() as db:
        with pytest.raises(HTTPException) as exc_info:
            await reject_proposed_change(proposed["proposal_id"], db, _FakeUser())
        assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_approve_blocked_while_instance_running_same_as_manual_patch():
    app = await _make_app()
    instance_id = await _seed_instance(app, "inst-p6")
    factory = get_session_factory()

    async with factory() as db:
        proposed = await propose_change(
            ProposeChangeRequest(instance_id=instance_id, params={"tp_pts": 9.0}, reasoning="x"),
            _FakeRequest(app),
            db,
            _FakeUser(),
        )

    # Simulate a running instance by registering a fake runner the engine sees as running.
    class _FakeRunner:
        status = "running"

    app.state.strategy_engine._runners[instance_id] = _FakeRunner()  # type: ignore[attr-defined]

    async with factory() as db:
        with pytest.raises(HTTPException) as exc_info:
            await approve_proposed_change(
                proposed["proposal_id"], _FakeRequest(app), db, _FakeUser()
            )
        assert exc_info.value.status_code == 400
        assert "Stop the instance" in exc_info.value.detail

    async with factory() as db:
        row = await db.get(ProposedStrategyChange, proposed["proposal_id"])
        assert row.status == "pending"  # never got marked approved since the write itself failed


@pytest.mark.asyncio
async def test_telegram_approve_callback_applies_change_and_edits_message():
    app = await _make_app()
    instance_id = await _seed_instance(app, "inst-p7")
    factory = get_session_factory()
    notifier: _FakeNotifier = app.state.telegram

    async with factory() as db:
        proposed = await propose_change(
            ProposeChangeRequest(
                instance_id=instance_id, params={"tp_pts": 15.0}, reasoning="via telegram"
            ),
            _FakeRequest(app),
            db,
            _FakeUser(),
        )

    cq = {
        "id": "cb1",
        "data": f"approve_change:{proposed['proposal_id']}",
        "message": {"message_id": 42, "text": "Proposed change: Gold Sweep-Reversal"},
    }
    await _handle_proposed_change_callback(
        app, notifier, "cb1", 42, cq, "approve_change", str(proposed["proposal_id"])
    )

    assert notifier.answered == [("cb1", "✅ Approved and applied")]
    assert len(notifier.edited) == 1

    async with factory() as db:
        inst = await db.get(StrategyInstance, instance_id)
        assert json.loads(inst.params_json)["tp_pts"] == 15.0
