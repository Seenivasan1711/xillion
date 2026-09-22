"""
Telegram inbound command/callback handling -- the control-surface half of
the bot, separate from telegram.py's outbound-only TelegramNotifier.

Long-polls Telegram's getUpdates (no public webhook needed -- works
identically in local dev and on Render, same "poll out, not in" shape as
mt5_bridge.py's own channel). Registered as a supervised background task
from xillion/main.py, only when TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID are
both configured.

Security: every update is checked against the configured chat id before
anything happens. Anything from a different chat is logged and dropped,
never trusted just because it reached this bot -- this is a single-user
system and the chat id is the only identity check that exists for it. The
kill switch specifically still demands a fresh TOTP code even from an
already-authorized chat -- this is a second front door to the same guarded
action (see xillion/api/risk.py's verify_totp_or_raise), never a new
unguarded one.
"""

from __future__ import annotations

import asyncio

import structlog
from fastapi import FastAPI, HTTPException
from sqlalchemy import select

from xillion.db.models import AppUser, StrategyInstance
from xillion.db.session import get_session_factory

logger = structlog.get_logger(__name__)

_HELP_TEXT = (
    "Commands:\n"
    "/status — list strategy instances and their running state\n"
    "/pause <name> — stop a running instance\n"
    "/resume <name> — start a stopped instance\n"
    "/killswitch <totp-code> — stop everything, cancel all open orders\n"
)


async def poll_telegram_updates(app: FastAPI) -> None:
    notifier = getattr(app.state, "telegram", None)
    if notifier is None or not getattr(notifier, "_enabled", False):
        logger.info("telegram_commands: not configured, poller idling")
        # main.py only registers this task when Telegram is configured --
        # this branch only exists as defense in depth. Sleep forever rather
        # than returning immediately: supervise() treats a fast return as a
        # crash and restarts it, and config can't change without a process
        # restart in this codebase anyway (see _load_telegram_credentials).
        await asyncio.Event().wait()
        return

    offset: int | None = None
    while True:
        try:
            updates = await notifier.get_updates(offset, timeout=25)
            for update in updates:
                offset = update["update_id"] + 1
                await _handle_update(app, notifier, update)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("telegram_commands: poll loop error", error=str(exc))
            await asyncio.sleep(5)


async def _handle_update(app: FastAPI, notifier, update: dict) -> None:
    if "callback_query" in update:
        await _handle_callback_query(app, notifier, update["callback_query"])
    elif "message" in update and "text" in update["message"]:
        await _handle_command(app, notifier, update["message"])


def _is_authorized(notifier, chat_id) -> bool:
    return chat_id is not None and str(chat_id) == str(getattr(notifier, "_chat_id", ""))


async def _handle_callback_query(app: FastAPI, notifier, cq: dict) -> None:
    chat_id = cq.get("message", {}).get("chat", {}).get("id")
    callback_id = cq.get("id")
    if not _is_authorized(notifier, chat_id):
        logger.warning("telegram_commands: callback from unauthorized chat", chat_id=chat_id)
        if callback_id:
            await notifier.answer_callback_query(callback_id, "Not authorized")
        return

    data = cq.get("data", "")
    message_id = cq.get("message", {}).get("message_id")
    action, _, arg = data.partition(":")

    if action in ("taken", "skipped") and arg:
        await _handle_signal_action_callback(notifier, callback_id, message_id, cq, action, arg)
    elif action in ("approve_change", "reject_change") and arg:
        await _handle_proposed_change_callback(
            app, notifier, callback_id, message_id, cq, action, arg
        )
    else:
        await notifier.answer_callback_query(callback_id, "Unrecognized action")


async def _handle_signal_action_callback(
    notifier, callback_id: str | None, message_id, cq: dict, action: str, signal_id: str
) -> None:
    from xillion.api.journal import set_signal_action_core

    factory = get_session_factory()
    try:
        async with factory() as db:
            await set_signal_action_core(
                db, signal_id, "TAKEN" if action == "taken" else "SKIPPED", source="telegram"
            )
        label = "✅ Taken" if action == "taken" else "⏭ Skipped"
        await notifier.answer_callback_query(callback_id, label)
        if message_id is not None:
            original = cq.get("message", {}).get("text", "")
            await notifier.edit_message_text(message_id, f"{original}\n\n{label} (via Telegram)")
    except HTTPException as exc:
        await notifier.answer_callback_query(callback_id, f"Failed: {exc.detail}")
    except Exception as exc:
        logger.error("telegram_commands: callback handling failed", error=str(exc))
        await notifier.answer_callback_query(callback_id, "Failed — see server logs")


async def _handle_proposed_change_callback(
    app: FastAPI,
    notifier,
    callback_id: str | None,
    message_id,
    cq: dict,
    action: str,
    proposal_id_str: str,
) -> None:
    """JEV / LLM-assisted decision-making (2026-09-22): Approve routes
    through the exact same update_instance_core a manual PATCH uses --
    this handler is just the Telegram front door to that, same as
    /killswitch is a front door to activate_kill_switch_core."""
    from xillion.api.proposed_changes import (
        approve_proposed_change_core,
        reject_proposed_change_core,
    )

    try:
        proposal_id = int(proposal_id_str)
    except ValueError:
        await notifier.answer_callback_query(callback_id, "Invalid proposal id")
        return

    factory = get_session_factory()
    try:
        async with factory() as db:
            if action == "approve_change":
                await approve_proposed_change_core(app, db, proposal_id, actor="telegram")
                label = "✅ Approved and applied"
            else:
                await reject_proposed_change_core(db, proposal_id, actor="telegram")
                label = "❌ Rejected"
        await notifier.answer_callback_query(callback_id, label)
        if message_id is not None:
            original = cq.get("message", {}).get("text", "")
            await notifier.edit_message_text(message_id, f"{original}\n\n{label} (via Telegram)")
    except HTTPException as exc:
        await notifier.answer_callback_query(callback_id, f"Failed: {exc.detail}")
    except Exception as exc:
        logger.error("telegram_commands: proposed-change callback failed", error=str(exc))
        await notifier.answer_callback_query(callback_id, "Failed — see server logs")


async def _handle_command(app: FastAPI, notifier, message: dict) -> None:
    chat_id = message.get("chat", {}).get("id")
    if not _is_authorized(notifier, chat_id):
        logger.warning("telegram_commands: message from unauthorized chat", chat_id=chat_id)
        return

    text = (message.get("text") or "").strip()
    if not text.startswith("/"):
        return

    parts = text.split(maxsplit=1)
    command = parts[0].lower().split("@")[0]  # strip a possible /cmd@botname suffix
    arg = parts[1].strip() if len(parts) > 1 else ""

    if command == "/status":
        await _cmd_status(app, notifier)
    elif command == "/pause":
        await _cmd_pause_resume(app, notifier, arg, pause=True)
    elif command == "/resume":
        await _cmd_pause_resume(app, notifier, arg, pause=False)
    elif command == "/killswitch":
        await _cmd_killswitch(app, notifier, arg)
    else:
        await notifier.send(_HELP_TEXT)


async def _cmd_status(app: FastAPI, notifier) -> None:
    engine = getattr(app.state, "strategy_engine", None)
    factory = get_session_factory()
    async with factory() as db:
        result = await db.execute(select(StrategyInstance))
        instances = result.scalars().all()
    if not instances:
        await notifier.send("No strategy instances exist yet.")
        return
    running_ids = {r._instance_id for r in engine.list_runners()} if engine else set()
    lines = [
        f"{'🟢' if inst.id in running_ids else '⚪'} {inst.name} ({inst.mode})"
        for inst in instances
    ]
    await notifier.send("\n".join(lines))


async def _find_instance_by_name(db, name: str) -> StrategyInstance | None:
    """Case-insensitive substring match -- requires exactly one match, so a
    fuzzy name never risks pausing/resuming the wrong instance."""
    result = await db.execute(select(StrategyInstance))
    matches = [i for i in result.scalars().all() if name.lower() in i.name.lower()]
    return matches[0] if len(matches) == 1 else None


async def _cmd_pause_resume(app: FastAPI, notifier, arg: str, pause: bool) -> None:
    if not arg:
        await notifier.send(f"Usage: /{'pause' if pause else 'resume'} <instance name>")
        return

    from xillion.api.instances import start_instance_core, stop_instance_core

    factory = get_session_factory()
    async with factory() as db:
        inst = await _find_instance_by_name(db, arg)
        if inst is None:
            await notifier.send(f"No unambiguous match for '{arg}'. Try /status for exact names.")
            return
        try:
            if pause:
                await stop_instance_core(app, db, inst.id, reason="telegram_pause")
                await notifier.send(f"⏸ Paused: {inst.name}")
            else:
                await start_instance_core(app, db, inst.id)
                await notifier.send(f"▶️ Resumed: {inst.name}")
        except HTTPException as exc:
            await notifier.send(f"Failed: {exc.detail}")


async def _cmd_killswitch(app: FastAPI, notifier, totp_code: str) -> None:
    from xillion.api.risk import activate_kill_switch_core, verify_totp_or_raise

    factory = get_session_factory()
    async with factory() as db:
        result = await db.execute(select(AppUser))
        user = result.scalars().first()
        if user is None:
            await notifier.send("No user account found — cannot verify.")
            return
        try:
            verify_totp_or_raise(user, totp_code or None)
        except HTTPException as exc:
            await notifier.send(f"Kill switch NOT activated: {exc.detail}")
            return

    try:
        # activate_kill_switch_core sends its own "Kill Switch Fired" alert
        # on success -- nothing more to send from here.
        await activate_kill_switch_core(app, actor="telegram")
    except HTTPException as exc:
        await notifier.send(f"Kill switch failed: {exc.detail}")
