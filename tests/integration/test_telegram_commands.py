"""
Telegram control-surface dispatcher (2026-09-22): Take/Skip callback
handling, /status, /pause, /resume, /killswitch. Drives the module's
functions directly against a real (in-memory) DB, same pattern as
tests/integration/test_market_scheduler.py, with a fake notifier recording
what would have been sent to Telegram instead of making real HTTP calls.
"""

from datetime import UTC, datetime

import pyotp
import pytest
from fastapi import FastAPI
from sqlalchemy import delete

from xillion.auth.totp import encrypt_secret, generate_secret
from xillion.core.plugin_loader import PluginRegistry
from xillion.core.risk import RiskManager
from xillion.core.strategy_base import Strategy
from xillion.data.bus import MarketDataBus
from xillion.db.models import (
    AppUser,
    BrokerClass,
    BrokerConnection,
    SignalLog,
    StrategyClass,
    StrategyInstance,
)
from xillion.db.session import get_session_factory, init_db
from xillion.engine.strategy_engine import StrategyEngine
from xillion.notifications.telegram_commands import (
    _cmd_killswitch,
    _cmd_pause_resume,
    _cmd_status,
    _find_instance_by_name,
    _handle_callback_query,
    _handle_command,
    _is_authorized,
)

AUTHORIZED_CHAT_ID = "12345"


class _FakeNotifier:
    _chat_id = AUTHORIZED_CHAT_ID
    _enabled = True

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.answered: list[tuple[str, str]] = []
        self.edited: list[tuple[int, str]] = []

    async def send(self, text: str) -> int | None:
        self.sent.append(text)
        return None

    async def answer_callback_query(self, callback_id: str, text: str = "") -> None:
        self.answered.append((callback_id, text))

    async def edit_message_text(self, message_id: int, text: str) -> None:
        self.edited.append((message_id, text))


class _NoopStrategy(Strategy):
    timeframe = "5m"
    instruments = ["XAUUSD"]


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
    app.state.telegram = None
    return app


async def _seed_instance(app: FastAPI, instance_id: str, name: str, status: str = "idle") -> str:
    await init_db()
    strategy_name = f"Telegram Test Strategy {instance_id}"
    app.state.plugin_loader.registry.strategies[strategy_name] = _NoopStrategy
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
                status=status,
                broker_connection_id=conn.id,
                instruments_json='["XAUUSD"]',
                timeframe="5m",
                params_json="{}",
                capital_allocation=5000,
                risk_limits_json="{}",
                auto_start=False,
                created_at=_now(),
                updated_at=_now(),
            )
        )
        await db.commit()
    return instance_id


async def _seed_enter_signal(instance_id: str) -> int:
    factory = get_session_factory()
    async with factory() as db:
        row = SignalLog(
            strategy_instance_id=instance_id,
            ts=_now(),
            underlying_symbol="XAUUSD",
            signal_type="ENTER",
            tag="Asian High",
            side="SELL",
            price=2629.0,
            message="test entry",
            mode="alert",
            notified=True,
            notified_at=_now(),
        )
        db.add(row)
        await db.commit()
        return row.id


def test_is_authorized_matches_configured_chat_id():
    notifier = _FakeNotifier()
    assert _is_authorized(notifier, AUTHORIZED_CHAT_ID) is True
    assert _is_authorized(notifier, "99999") is False
    assert _is_authorized(notifier, None) is False


@pytest.mark.asyncio
async def test_find_instance_by_name_requires_unambiguous_match():
    app = await _make_app()
    await _seed_instance(app, "inst-a", "Gold Sweep-Reversal")
    await _seed_instance(app, "inst-b", "Gold Sweep-Reversal Backup")

    factory = get_session_factory()
    async with factory() as db:
        assert (await _find_instance_by_name(db, "Backup")).id == "inst-b"
        assert await _find_instance_by_name(db, "Gold") is None  # matches both -- ambiguous
        assert await _find_instance_by_name(db, "Nonexistent") is None


@pytest.mark.asyncio
async def test_handle_callback_query_marks_taken_and_edits_message():
    app = await _make_app()
    instance_id = await _seed_instance(app, "inst-c", "Gold Sweep-Reversal")
    signal_id = await _seed_enter_signal(instance_id)
    notifier = _FakeNotifier()

    cq = {
        "id": "cb1",
        "data": f"taken:{signal_id}",
        "message": {
            "chat": {"id": int(AUTHORIZED_CHAT_ID)},
            "message_id": 555,
            "text": "SELL ENTER: XAUUSD",
        },
    }
    await _handle_callback_query(app, notifier, cq)

    assert notifier.answered == [("cb1", "✅ Taken")]
    assert notifier.edited == [(555, "SELL ENTER: XAUUSD\n\n✅ Taken (via Telegram)")]

    factory = get_session_factory()
    async with factory() as db:
        row = await db.get(SignalLog, signal_id)
        assert row.user_action == "TAKEN"
        assert row.user_action_source == "telegram"


@pytest.mark.asyncio
async def test_handle_callback_query_rejects_unauthorized_chat():
    app = await _make_app()
    instance_id = await _seed_instance(app, "inst-d", "Gold Sweep-Reversal")
    signal_id = await _seed_enter_signal(instance_id)
    notifier = _FakeNotifier()

    cq = {
        "id": "cb2",
        "data": f"taken:{signal_id}",
        "message": {"chat": {"id": 99999}, "message_id": 1, "text": "x"},
    }
    await _handle_callback_query(app, notifier, cq)

    assert notifier.edited == []  # never touched the message
    factory = get_session_factory()
    async with factory() as db:
        row = await db.get(SignalLog, signal_id)
        assert row.user_action is None  # never marked


@pytest.mark.asyncio
async def test_cmd_status_lists_instances():
    app = await _make_app()
    await _seed_instance(app, "inst-e", "Gold Sweep-Reversal")
    notifier = _FakeNotifier()

    await _cmd_status(app, notifier)

    assert len(notifier.sent) == 1
    assert "Gold Sweep-Reversal" in notifier.sent[0]
    assert "⚪" in notifier.sent[0]  # idle, not running


@pytest.mark.asyncio
async def test_cmd_pause_resume_no_match_reports_ambiguity():
    app = await _make_app()
    notifier = _FakeNotifier()

    await _cmd_pause_resume(app, notifier, "Nonexistent Strategy", pause=True)

    assert "No unambiguous match" in notifier.sent[0]


@pytest.mark.asyncio
async def test_cmd_killswitch_rejects_missing_totp():
    app = await _make_app()
    factory = get_session_factory()
    async with factory() as db:
        await db.execute(delete(AppUser))  # single-user lookup -- keep exactly one row
        secret = generate_secret()
        db.add(
            AppUser(
                username="rakesh",
                password_hash="x",
                totp_secret=encrypt_secret(secret),
                is_active=True,
                created_at=_now(),
            )
        )
        await db.commit()

    notifier = _FakeNotifier()
    await _cmd_killswitch(app, notifier, "")

    assert "NOT activated" in notifier.sent[0]
    assert "TOTP code required" in notifier.sent[0]


@pytest.mark.asyncio
async def test_cmd_killswitch_rejects_wrong_totp():
    app = await _make_app()
    factory = get_session_factory()
    async with factory() as db:
        await db.execute(delete(AppUser))
        secret = generate_secret()
        db.add(
            AppUser(
                username="rakesh2",
                password_hash="x",
                totp_secret=encrypt_secret(secret),
                is_active=True,
                created_at=_now(),
            )
        )
        await db.commit()

    notifier = _FakeNotifier()
    await _cmd_killswitch(app, notifier, "000000")

    assert "NOT activated" in notifier.sent[0]
    assert "Invalid TOTP" in notifier.sent[0]


@pytest.mark.asyncio
async def test_cmd_killswitch_accepts_valid_totp_and_activates(monkeypatch):
    app = await _make_app()
    factory = get_session_factory()
    secret = generate_secret()
    async with factory() as db:
        await db.execute(delete(AppUser))
        db.add(
            AppUser(
                username="rakesh3",
                password_hash="x",
                totp_secret=encrypt_secret(secret),
                is_active=True,
                created_at=_now(),
            )
        )
        await db.commit()

    called = {}

    async def _fake_activate(app_arg, actor):
        called["actor"] = actor
        return {"activated": True, "strategies_stopped": 0, "orders_cancelled": 0}

    monkeypatch.setattr("xillion.api.risk.activate_kill_switch_core", _fake_activate, raising=True)

    notifier = _FakeNotifier()
    valid_code = pyotp.TOTP(secret).now()
    await _cmd_killswitch(app, notifier, valid_code)

    assert called.get("actor") == "telegram"
    assert notifier.sent == []  # success has no extra message -- core function notifies


@pytest.mark.asyncio
async def test_handle_command_ignores_unauthorized_chat():
    app = await _make_app()
    notifier = _FakeNotifier()
    message = {"chat": {"id": 99999}, "text": "/status"}

    await _handle_command(app, notifier, message)

    assert notifier.sent == []
