"""
Strategy version history (CP6): strategy_class is upserted in place on
every plugin sync, which would silently lose a strategy's prior versions
the moment its code changes -- sync_registry_to_db must log each real
change to strategy_version_history before overwriting.
"""
import pytest
from sqlalchemy import select

from xillion.core.plugin_loader import PluginRegistry
from xillion.core.strategy_base import Strategy
from xillion.db.models import StrategyVersionHistory
from xillion.db.plugin_sync import sync_registry_to_db
from xillion.db.session import get_session_factory, init_db


class _VersionTestStrategy(Strategy):
    name = "Version History Test Strategy"
    version = "1.0.0"


def _registry_with(cls) -> PluginRegistry:
    registry = PluginRegistry()
    registry.strategies[cls.name] = cls
    registry.strategy_file_hashes[cls.name] = "hash-v1"
    registry.strategy_file_paths[cls.name] = "strategies/x.py"
    return registry


@pytest.mark.asyncio
async def test_first_sync_records_one_version():
    await init_db()
    factory = get_session_factory()
    async with factory() as session:
        await sync_registry_to_db(_registry_with(_VersionTestStrategy), session)

    async with factory() as session:
        rows = (await session.execute(select(StrategyVersionHistory))).scalars().all()
    assert len(rows) == 1
    assert rows[0].code_hash == "hash-v1"


@pytest.mark.asyncio
async def test_resyncing_unchanged_code_does_not_duplicate_history():
    await init_db()
    factory = get_session_factory()
    registry = _registry_with(_VersionTestStrategy)
    async with factory() as session:
        await sync_registry_to_db(registry, session)
    async with factory() as session:
        await sync_registry_to_db(registry, session)  # identical hash, second sync

    async with factory() as session:
        rows = (await session.execute(select(StrategyVersionHistory))).scalars().all()
    assert len(rows) == 1  # not re-logged


@pytest.mark.asyncio
async def test_code_change_appends_a_new_version_row_not_overwrite():
    await init_db()
    factory = get_session_factory()
    registry = _registry_with(_VersionTestStrategy)
    async with factory() as session:
        await sync_registry_to_db(registry, session)

    registry.strategy_file_hashes[_VersionTestStrategy.name] = "hash-v2"
    async with factory() as session:
        await sync_registry_to_db(registry, session)

    async with factory() as session:
        rows = (await session.execute(
            select(StrategyVersionHistory).order_by(StrategyVersionHistory.id)
        )).scalars().all()
    assert len(rows) == 2
    assert [r.code_hash for r in rows] == ["hash-v1", "hash-v2"]
