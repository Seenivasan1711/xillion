"""
mongo_context_store (2026-09-22, SESSION SPRINT item 15): unconfigured is a
real no-op (no motor import, no connection attempt), configured writes go
through, and a write failure never raises -- same best-effort contract as
TelegramNotifier.send(). No real MongoDB here; the client is stubbed.
"""

import pytest

from xillion.data import mongo_context_store


class _FakeCollection:
    def __init__(self):
        self.inserted: list[dict] = []
        self.raise_on_insert = False

    async def insert_one(self, doc):
        if self.raise_on_insert:
            raise RuntimeError("simulated connection failure")
        self.inserted.append(doc)


class _FakeDB:
    def __init__(self):
        self.collections: dict[str, _FakeCollection] = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


@pytest.fixture(autouse=True)
def _reset_client_cache():
    # _get_db() caches the Motor client at module scope -- reset between
    # tests so one test's monkeypatched settings don't leak into the next.
    mongo_context_store._client = None
    mongo_context_store._client_uri = None
    yield
    mongo_context_store._client = None
    mongo_context_store._client_uri = None


@pytest.mark.asyncio
async def test_record_trade_no_op_when_unconfigured(monkeypatch):
    monkeypatch.setattr(mongo_context_store, "_get_db", lambda: None)
    # Should return cleanly with no exception and nothing to assert on --
    # the point is it doesn't try to import/connect motor at all.
    await mongo_context_store.record_trade({"symbol": "XAUUSD"})


@pytest.mark.asyncio
async def test_record_trade_writes_when_configured(monkeypatch):
    fake_db = _FakeDB()
    monkeypatch.setattr(mongo_context_store, "_get_db", lambda: fake_db)

    await mongo_context_store.record_trade({"symbol": "XAUUSD", "pnl": 12.5})

    assert fake_db.collections["trades"].inserted == [{"symbol": "XAUUSD", "pnl": 12.5}]


@pytest.mark.asyncio
async def test_record_backtest_run_writes_when_configured(monkeypatch):
    fake_db = _FakeDB()
    monkeypatch.setattr(mongo_context_store, "_get_db", lambda: fake_db)

    await mongo_context_store.record_backtest_run({"run_id": "abc123", "metrics": {}})

    assert fake_db.collections["backtest_runs"].inserted == [{"run_id": "abc123", "metrics": {}}]


@pytest.mark.asyncio
async def test_write_failure_is_swallowed_not_raised(monkeypatch):
    fake_db = _FakeDB()
    fake_db.collections["trades"] = _FakeCollection()
    fake_db.collections["trades"].raise_on_insert = True
    monkeypatch.setattr(mongo_context_store, "_get_db", lambda: fake_db)

    # Must not raise, even though the underlying insert does.
    await mongo_context_store.record_trade({"symbol": "XAUUSD"})


@pytest.mark.asyncio
async def test_get_db_returns_none_when_uri_empty(monkeypatch):
    class _FakeSettings:
        mongodb_uri = ""

    monkeypatch.setattr(mongo_context_store, "get_settings", lambda: _FakeSettings())
    assert mongo_context_store._get_db() is None
