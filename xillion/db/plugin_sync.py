"""
Persists discovered plugins (xillion.core.plugin_loader.PluginRegistry) into
the strategy_class / broker_class tables. Plugin discovery itself is DB-free
(plugin_loader.py just scans/imports files); this is the one place that
bridges the in-memory registry to Postgres, so `GET /strategies/classes`
(in-memory) and `POST /instances` (DB-backed FK lookup) stay in sync.
"""
import dataclasses
import json
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xillion.core.plugin_loader import PluginRegistry
from xillion.db.models import BrokerClass, DataProviderClass, StrategyClass, StrategyVersionHistory

logger = structlog.get_logger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def sync_registry_to_db(registry: PluginRegistry, db: AsyncSession) -> None:
    """Upsert every discovered strategy/broker class into the DB by name."""
    now = _now()

    for name, cls in registry.strategies.items():
        result = await db.execute(select(StrategyClass).where(StrategyClass.name == name))
        row = result.scalar_one_or_none()
        params_schema_json = json.dumps([dataclasses.asdict(p) for p in cls.params_schema])
        code_hash = registry.strategy_file_hashes.get(name, "")
        module_path = registry.strategy_file_paths.get(name, "")
        if row is None:
            row = StrategyClass(
                name=name,
                module_path=module_path,
                class_name=cls.__name__,
                version=cls.version,
                description=cls.description,
                author=cls.author,
                default_timeframe=cls.timeframe,
                params_schema_json=params_schema_json,
                code_hash=code_hash,
                discovered_at=now,
                last_seen_at=now,
            )
            db.add(row)
            await db.flush()  # need row.id for the version-history FK below
            db.add(StrategyVersionHistory(
                strategy_class_id=row.id, version=cls.version, code_hash=code_hash, recorded_at=now,
            ))
        else:
            code_changed = row.code_hash != code_hash or row.version != cls.version
            row.module_path = module_path
            row.class_name = cls.__name__
            row.version = cls.version
            row.description = cls.description
            row.author = cls.author
            row.default_timeframe = cls.timeframe
            row.params_schema_json = params_schema_json
            row.code_hash = code_hash
            row.last_seen_at = now
            # strategy_class is upserted in place -- log the change here or
            # it's gone the moment the next sync overwrites it.
            if code_changed:
                db.add(StrategyVersionHistory(
                    strategy_class_id=row.id, version=cls.version, code_hash=code_hash, recorded_at=now,
                ))

    for name, cls in registry.brokers.items():
        result = await db.execute(select(BrokerClass).where(BrokerClass.name == name))
        row = result.scalar_one_or_none()
        capabilities_json = json.dumps(dataclasses.asdict(cls.capabilities))
        code_hash = registry.broker_file_hashes.get(name, "")
        module_path = registry.broker_file_paths.get(name, "")
        if row is None:
            db.add(
                BrokerClass(
                    name=name,
                    module_path=module_path,
                    class_name=cls.__name__,
                    version=cls.version,
                    capabilities_json=capabilities_json,
                    discovered_at=now,
                    last_seen_at=now,
                )
            )
        else:
            row.module_path = module_path
            row.class_name = cls.__name__
            row.version = cls.version
            row.capabilities_json = capabilities_json
            row.last_seen_at = now

    for name, cls in registry.data_providers.items():
        result = await db.execute(select(DataProviderClass).where(DataProviderClass.name == name))
        row = result.scalar_one_or_none()
        capabilities_json = json.dumps(dataclasses.asdict(cls.capabilities))
        module_path = registry.data_provider_file_paths.get(name, "")
        if row is None:
            db.add(
                DataProviderClass(
                    name=name,
                    module_path=module_path,
                    class_name=cls.__name__,
                    version=cls.version,
                    description=cls.description,
                    capabilities_json=capabilities_json,
                    discovered_at=now,
                    last_seen_at=now,
                )
            )
        else:
            row.module_path = module_path
            row.class_name = cls.__name__
            row.version = cls.version
            row.description = cls.description
            row.capabilities_json = capabilities_json
            row.last_seen_at = now

    await db.commit()
    logger.info(
        "plugin registry synced to db",
        strategy_count=len(registry.strategies),
        broker_count=len(registry.brokers),
        data_provider_count=len(registry.data_providers),
    )
