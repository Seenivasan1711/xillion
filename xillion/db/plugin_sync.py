"""
Persists discovered plugins (xillion.core.plugin_loader.PluginRegistry) into
the strategy_class / broker_class tables. Plugin discovery itself is DB-free
(plugin_loader.py just scans/imports files); this is the one place that
bridges the in-memory registry to Postgres, so `GET /strategies/classes`
(in-memory) and `POST /instances` (DB-backed FK lookup) stay in sync.
"""

import dataclasses
import json
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xillion.core.plugin_loader import PluginRegistry
from xillion.db.models import BrokerClass, DataProviderClass, StrategyClass, StrategyVersionHistory

logger = structlog.get_logger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat()


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
            db.add(
                StrategyVersionHistory(
                    strategy_class_id=row.id,
                    version=cls.version,
                    code_hash=code_hash,
                    recorded_at=now,
                )
            )
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
                db.add(
                    StrategyVersionHistory(
                        strategy_class_id=row.id,
                        version=cls.version,
                        code_hash=code_hash,
                        recorded_at=now,
                    )
                )

    # Distinct variable names per loop below (broker_*/provider_* rather
    # than reusing row/cls/result from the strategies loop above): Python
    # doesn't scope `for` loop variables, so reusing them across loops over
    # differently-typed registries made mypy pin each name's type to its
    # first-seen loop, misflagging every later reference to a Broker/
    # DataProviderClass-only attribute (e.g. .capabilities) as an error --
    # this runs correctly today, it's purely a static-typing false positive
    # from name reuse, but the rename is genuinely clearer either way.
    for name, broker_cls in registry.brokers.items():
        broker_result = await db.execute(select(BrokerClass).where(BrokerClass.name == name))
        broker_row = broker_result.scalar_one_or_none()
        capabilities_json = json.dumps(dataclasses.asdict(broker_cls.capabilities))
        module_path = registry.broker_file_paths.get(name, "")
        if broker_row is None:
            db.add(
                BrokerClass(
                    name=name,
                    module_path=module_path,
                    class_name=broker_cls.__name__,
                    version=broker_cls.version,
                    capabilities_json=capabilities_json,
                    discovered_at=now,
                    last_seen_at=now,
                )
            )
        else:
            broker_row.module_path = module_path
            broker_row.class_name = broker_cls.__name__
            broker_row.version = broker_cls.version
            broker_row.capabilities_json = capabilities_json
            broker_row.last_seen_at = now

    for name, provider_cls in registry.data_providers.items():
        provider_result = await db.execute(
            select(DataProviderClass).where(DataProviderClass.name == name)
        )
        provider_row = provider_result.scalar_one_or_none()
        capabilities_json = json.dumps(dataclasses.asdict(provider_cls.capabilities))
        module_path = registry.data_provider_file_paths.get(name, "")
        if provider_row is None:
            db.add(
                DataProviderClass(
                    name=name,
                    module_path=module_path,
                    class_name=provider_cls.__name__,
                    version=provider_cls.version,
                    description=provider_cls.description,
                    capabilities_json=capabilities_json,
                    discovered_at=now,
                    last_seen_at=now,
                )
            )
        else:
            provider_row.module_path = module_path
            provider_row.class_name = provider_cls.__name__
            provider_row.version = provider_cls.version
            provider_row.description = provider_cls.description
            provider_row.capabilities_json = capabilities_json
            provider_row.last_seen_at = now

    await db.commit()
    logger.info(
        "plugin registry synced to db",
        strategy_count=len(registry.strategies),
        broker_count=len(registry.brokers),
        data_provider_count=len(registry.data_providers),
    )
