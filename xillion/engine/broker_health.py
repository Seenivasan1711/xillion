"""
Broker health monitoring + automatic failover trigger. Polls
Broker.healthcheck() the same way market_scheduler.py polls
is_market_open() -- react to a state TRANSITION (healthy -> sustained
unhealthy), not every individual tick.

Nothing here fires unless a BrokerConnection has failover_connection_id
explicitly set (migration 017) -- by default, a broker going down just
logs/alerts, same as before this existed. See xillion/engine/
broker_failover.py for the exit-only action itself once triggered.
"""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from fastapi import FastAPI
from sqlalchemy import select

from xillion.db.models import BrokerConnection
from xillion.db.session import get_session_factory
from xillion.engine.broker_failover import run_failover_exit

logger = structlog.get_logger(__name__)

DEFAULT_POLL_INTERVAL_SECONDS = 30
# ~90s of sustained failure before acting -- long enough that one slow
# response or a transient network blip doesn't fire a real cross-broker
# exit, short enough to matter for a same-day outage.
CONSECUTIVE_FAILURE_THRESHOLD = 3


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class ConnectionHealth:
    consecutive_failures: int = 0
    last_checked_at: str | None = None
    last_healthy_at: str | None = None
    down_alerted: bool = False
    failover_triggered: bool = False


async def run_broker_health_scheduler(
    app: FastAPI, poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS
) -> None:
    """Runs forever as a background task (see xillion/main.py's lifespan)."""
    if not hasattr(app.state, "broker_health"):
        # No type annotation here -- mypy rejects one on a non-self
        # attribute assignment (see xillion/main.py's own comment on the
        # same pattern for app.state.broker_instances).
        app.state.broker_health = {}
    while True:
        await asyncio.sleep(poll_interval_seconds)
        try:
            await _health_tick(app)
        except Exception as exc:
            logger.error("broker health scheduler tick failed", error=str(exc))


async def _health_tick(app: FastAPI) -> None:
    broker_instances = getattr(app.state, "broker_instances", {})
    health: dict[str, ConnectionHealth] = app.state.broker_health
    notifier = getattr(app.state, "telegram", None)
    notify = notifier.alert if notifier else None

    for name, info in broker_instances.items():
        broker = info.get("instance") if isinstance(info, dict) else None
        if broker is None or info.get("status") != "connected":
            continue

        state = health.setdefault(name, ConnectionHealth())
        try:
            healthy = await broker.healthcheck()
        except Exception as exc:
            logger.warning("broker healthcheck raised", connection=name, error=str(exc))
            healthy = False

        state.last_checked_at = _now_iso()

        if healthy:
            if state.consecutive_failures >= CONSECUTIVE_FAILURE_THRESHOLD:
                logger.info("broker health recovered", connection=name)
                if notify:
                    await notify("Broker recovered", f"{name} is healthy again.", "warning")
            state.consecutive_failures = 0
            state.last_healthy_at = state.last_checked_at
            state.down_alerted = False
            state.failover_triggered = False
            continue

        state.consecutive_failures += 1
        if state.consecutive_failures < CONSECUTIVE_FAILURE_THRESHOLD:
            continue

        if not state.down_alerted:
            logger.critical(
                "broker unhealthy for consecutive checks",
                connection=name,
                failures=state.consecutive_failures,
            )
            if notify:
                await notify(
                    "Broker unhealthy",
                    f"{name} has failed {state.consecutive_failures} consecutive health "
                    "checks. Checking for a configured failover target.",
                    "critical",
                )
            state.down_alerted = True

        if state.failover_triggered:
            continue  # already acted on this outage -- don't re-trigger every tick

        await _maybe_failover(app, name, health, notify)


async def _maybe_failover(app: FastAPI, down_name: str, health: dict, notify) -> None:
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(BrokerConnection).where(BrokerConnection.name == down_name)
        )
        down_conn = result.scalars().first()
        if down_conn is None or down_conn.failover_connection_id is None:
            return  # not configured -- alert-only, matches "if failover configured"

        target_result = await session.execute(
            select(BrokerConnection).where(BrokerConnection.id == down_conn.failover_connection_id)
        )
        target_conn = target_result.scalars().first()

    if target_conn is None:
        logger.error(
            "failover target connection row missing",
            down=down_name,
            target_id=down_conn.failover_connection_id,
        )
        return

    broker_instances = getattr(app.state, "broker_instances", {})
    target_info = broker_instances.get(target_conn.name)
    target_health = health.get(target_conn.name)
    target_broker = target_info.get("instance") if isinstance(target_info, dict) else None
    target_status = target_info.get("status") if isinstance(target_info, dict) else None

    if (
        target_broker is None
        or target_status != "connected"
        or (target_health is not None and target_health.consecutive_failures > 0)
    ):
        logger.critical(
            "failover target is not healthy -- cannot fail over",
            down=down_name,
            target=target_conn.name,
        )
        if notify:
            await notify(
                "Broker failover unavailable",
                f"{down_name} is down and its configured failover target "
                f"{target_conn.name} isn't healthy either. Manual intervention required.",
                "critical",
            )
        return

    health[down_name].failover_triggered = True
    await run_failover_exit(
        down_connection_id=down_conn.id,
        down_connection_name=down_name,
        failover_broker=target_broker,
        failover_broker_name=target_conn.name,
        db_factory=get_session_factory,
        notify=notify,
    )
