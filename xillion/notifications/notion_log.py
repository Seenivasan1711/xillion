"""
Notion action log (2026-09-22, task-tracker.md's SESSION SPRINT item 16).

Logs operator actions taken on live/fine-tuned strategies -- parameter
edits, start/stop, Take/Skip decisions on alerts, kill-switch activations
-- as pages in a Notion database, for later LLM context feeding (a
human-readable decision log, distinct from mongo_context_store.py's raw
trade/backtest data).

Best-effort, always: never raises, same principle as TelegramNotifier.send()
and mongo_context_store.py. Empty NOTION_API_TOKEN/NOTION_DATABASE_ID (the
default until Rakesh sets up the integration -- see manual-tasks.md) means
log_action() is a real no-op with a debug log line, not a silent
pretend-success.

Design note: every Notion database has exactly one "title" property, but
its NAME is whatever the user called it when creating the database (not
necessarily "Name") -- so this queries the database's schema once (cached
per configured database id) to find the actual title property, rather than
assuming a specific name and silently failing against a real database that
doesn't happen to use it.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import structlog
from httpx import AsyncClient

from xillion.config import get_settings

logger = structlog.get_logger(__name__)

_NOTION_VERSION = "2022-06-28"
_BASE_URL = "https://api.notion.com/v1"

_title_prop_cache: dict[str, str] = {}  # database_id -> title property name


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": _NOTION_VERSION,
        "Content-Type": "application/json",
    }


async def _title_property_name(client: AsyncClient, token: str, database_id: str) -> str | None:
    if database_id in _title_prop_cache:
        return _title_prop_cache[database_id]

    resp = await client.get(
        f"{_BASE_URL}/databases/{database_id}", headers=_headers(token), timeout=10
    )
    if not resp.is_success:
        logger.warning(
            "notion_log: could not read database schema",
            status=resp.status_code,
            body=resp.text[:300],
        )
        return None

    properties = resp.json().get("properties", {})
    for name, spec in properties.items():
        if spec.get("type") == "title":
            _title_prop_cache[database_id] = name
            return name
    return None


async def log_action(title: str, details: dict[str, Any]) -> None:
    """Writes one page to the configured Notion database. `title` becomes
    the page's title; `details` is rendered as formatted text in the page
    body (not custom properties, since this doesn't assume the target
    database has any specific property beyond the title every database
    already has)."""
    settings = get_settings()
    token = settings.notion_api_token
    database_id = settings.notion_database_id
    if not token or not database_id:
        logger.debug("notion_log: not configured, skipping action log", title=title)
        return

    try:
        async with AsyncClient() as client:
            title_prop = await _title_property_name(client, token, database_id)
            if title_prop is None:
                logger.warning("notion_log: database has no title property, skipping")
                return

            body_text = json.dumps(details, default=str, indent=2)[
                :2000
            ]  # Notion's rich_text length cap
            resp = await client.post(
                f"{_BASE_URL}/pages",
                headers=_headers(token),
                json={
                    "parent": {"database_id": database_id},
                    "properties": {
                        title_prop: {
                            "title": [
                                {"text": {"content": f"{title} — {datetime.now(UTC).isoformat()}"}}
                            ]
                        }
                    },
                    "children": [
                        {
                            "object": "block",
                            "type": "code",
                            "code": {
                                "language": "json",
                                "rich_text": [{"text": {"content": body_text}}],
                            },
                        }
                    ],
                },
                timeout=10,
            )
            if not resp.is_success:
                logger.warning(
                    "notion_log: write failed", status=resp.status_code, body=resp.text[:300]
                )
    except Exception as exc:
        logger.error("notion_log: exception", error=str(exc))
