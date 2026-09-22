"""
JEV / LLM-assisted decision-making (2026-09-22, task-tracker.md's SESSION
SPRINT item 17): an LLM proposes a strategy parameter change with its
reasoning, via the MCP server's propose_parameter_change tool -- this
module is the queue + approve/reject flow, never the thing that applies a
change itself. Notifies Rakesh on Telegram with Approve/Reject inline
buttons (see telegram_commands.py's callback handling); approval writes
through the exact same update_instance_core the web UI's own edit form
(and the API's PATCH route) already uses, not a new write path -- an
approved proposal is indistinguishable, in what it does to the DB, from
Rakesh editing the instance himself.

Mirrors the project's existing "an LLM must never invent an order" boundary
(deferred-backlog.md's "Explicitly rejected" table), extended to parameter
changes: propose + explain, human approves, only then does code write
anything.
"""

import json
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from xillion.api.deps import db_dep, get_current_user
from xillion.api.instances import UpdateInstanceRequest, update_instance_core
from xillion.db.models import AppUser, ProposedStrategyChange, StrategyInstance

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/proposed-changes", tags=["proposed-changes"])


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _row_dict(r: ProposedStrategyChange) -> dict:
    return {
        "id": r.id,
        "strategy_instance_id": r.strategy_instance_id,
        "params": json.loads(r.proposed_params_json),
        "reasoning": r.reasoning,
        "proposed_by": r.proposed_by,
        "status": r.status,
        "created_at": r.created_at,
        "decided_at": r.decided_at,
        "decided_by": r.decided_by,
    }


class ProposeChangeRequest(BaseModel):
    instance_id: str
    params: dict
    reasoning: str
    proposed_by: str = "JEV"


@router.post("")
async def propose_change(
    body: ProposeChangeRequest,
    request: Request,
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    result = await db.execute(
        select(StrategyInstance).where(StrategyInstance.id == body.instance_id)
    )
    inst = result.scalar_one_or_none()
    if inst is None:
        raise HTTPException(404, "Instance not found")

    row = ProposedStrategyChange(
        strategy_instance_id=body.instance_id,
        proposed_params_json=json.dumps(body.params),
        reasoning=body.reasoning,
        proposed_by=body.proposed_by,
        status="pending",
        created_at=_now(),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    notifier = getattr(request.app.state, "telegram", None)
    if notifier is not None:
        params_text = json.dumps(body.params, indent=2)
        message_id = await notifier.alert(
            f"Proposed change: {inst.name}",
            f"By: {body.proposed_by}\n\n{body.reasoning}\n\nProposed params:\n{params_text}",
            "warn",
        )
        if message_id is not None and hasattr(notifier, "add_inline_buttons"):
            await notifier.add_inline_buttons(
                message_id,
                [
                    [
                        {"text": "✅ Approve", "callback_data": f"approve_change:{row.id}"},
                        {"text": "❌ Reject", "callback_data": f"reject_change:{row.id}"},
                    ]
                ],
            )
            row.telegram_message_id = message_id
            await db.commit()

    logger.info(
        "proposed strategy change created",
        proposal_id=row.id,
        instance_id=body.instance_id,
        proposed_by=body.proposed_by,
    )
    return {"proposal_id": row.id, "status": "pending"}


@router.get("")
async def list_proposed_changes(
    status: str | None = None,
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    query = select(ProposedStrategyChange).order_by(ProposedStrategyChange.id.desc())
    if status:
        query = query.where(ProposedStrategyChange.status == status)
    result = await db.execute(query)
    return {"proposals": [_row_dict(r) for r in result.scalars().all()]}


async def approve_proposed_change_core(
    app: FastAPI, db: AsyncSession, proposal_id: int, actor: str
) -> dict:
    """Core approve logic, shared by the API route below and the Telegram
    inline-button handler (telegram_commands.py). Writes through
    update_instance_core -- the exact same path a manual PATCH takes, same
    running-instance guard, same Notion action log."""
    row = await db.get(ProposedStrategyChange, proposal_id)
    if row is None:
        raise HTTPException(404, "Proposal not found")
    if row.status != "pending":
        raise HTTPException(400, f"Proposal already {row.status}")

    params = json.loads(row.proposed_params_json)
    update_result = await update_instance_core(
        app, db, row.strategy_instance_id, UpdateInstanceRequest(params=params), actor=actor
    )
    row.status = "approved"
    row.decided_at = _now()
    row.decided_by = actor
    await db.commit()
    logger.info("proposed strategy change approved", proposal_id=proposal_id, actor=actor)
    return {"approved": True, "update_result": update_result}


async def reject_proposed_change_core(db: AsyncSession, proposal_id: int, actor: str) -> dict:
    row = await db.get(ProposedStrategyChange, proposal_id)
    if row is None:
        raise HTTPException(404, "Proposal not found")
    if row.status != "pending":
        raise HTTPException(400, f"Proposal already {row.status}")

    row.status = "rejected"
    row.decided_at = _now()
    row.decided_by = actor
    await db.commit()
    logger.info("proposed strategy change rejected", proposal_id=proposal_id, actor=actor)
    return {"rejected": True}


@router.post("/{proposal_id}/approve")
async def approve_proposed_change(
    proposal_id: int,
    request: Request,
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    return await approve_proposed_change_core(request.app, db, proposal_id, actor=user.username)


@router.post("/{proposal_id}/reject")
async def reject_proposed_change(
    proposal_id: int,
    db: AsyncSession = Depends(db_dep),
    user: AppUser = Depends(get_current_user),
):
    return await reject_proposed_change_core(db, proposal_id, actor=user.username)
