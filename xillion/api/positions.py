"""
Live positions API (CP7) -- aggregates open positions across every running
strategy instance. Pulled forward from CP9's "Logs DB persistence +
GET /api/positions" bullet because the MCP server's get_positions tool
needs it now; CP9's DB-persistence half of that bullet is unrelated and
still pending.
"""

from typing import Any

from fastapi import APIRouter, Depends, Request

from xillion.api.deps import get_current_user
from xillion.db.models import AppUser

router = APIRouter(prefix="/positions", tags=["positions"])


def collect_open_positions(runners: list) -> list[dict]:
    """Pure aggregation logic, split out so it's testable without a FastAPI
    Request/app.state -- just needs objects shaped like StrategyRunner."""
    positions = []
    for runner in runners:
        try:
            for pos in runner._ctx.positions():
                if pos.quantity == 0:
                    continue
                positions.append(
                    {
                        "instance_id": runner._instance_id,
                        "instance_name": runner._ctx._instance_name,
                        "mode": runner._ctx.mode,
                        "symbol": pos.symbol,
                        "quantity": pos.quantity,
                        "avg_price": float(pos.avg_price),
                        "last_price": float(pos.last_price),
                        "realised_pnl": float(pos.realised_pnl),
                        "unrealised_pnl": float(pos.unrealised_pnl),
                    }
                )
        except Exception:
            continue  # a runner mid-crash shouldn't take the whole endpoint down
    return positions


@router.get("")
async def get_positions(
    request: Request, user: AppUser = Depends(get_current_user)
) -> dict[str, Any]:
    engine = getattr(request.app.state, "strategy_engine", None)
    if engine is None:
        return {"positions": []}
    return {"positions": collect_open_positions(engine.list_runners())}
