"""
Telegram notifier. Sends alerts via the Telegram Bot API.

Configured via Settings -> Notifications in the app (encrypted DB storage,
same xillion/auth/credstore.py pattern as broker credentials), with
TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID env vars as a fallback -- see
xillion/main.py's _load_telegram_credentials.
"""

import structlog
from httpx import AsyncClient

from xillion.config import settings

logger = structlog.get_logger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


class TelegramNotifier:
    def __init__(self, token: str = "", chat_id: str = "") -> None:
        self._token = token or settings.telegram_bot_token
        self._chat_id = chat_id or settings.telegram_chat_id
        self._enabled = bool(self._token and self._chat_id)

    def configure(self, token: str, chat_id: str) -> None:
        """Applied immediately, no process restart -- called from
        PUT /settings/notifications so a saved token takes effect right
        away, same as Zerodha/Dhan's save-then-reconnect flow."""
        self._token = token
        self._chat_id = chat_id
        self._enabled = bool(self._token and self._chat_id)

    async def send(self, text: str, parse_mode: str = "Markdown") -> int | None:
        """Returns the sent message's message_id (needed to later attach
        inline buttons via add_inline_buttons, see 2026-09-22's Telegram
        control-surface work) or None if sending failed/wasn't configured."""
        if not self._enabled:
            logger.debug("Telegram not configured; skipping notification")
            return None
        url = TELEGRAM_API.format(token=self._token, method="sendMessage")
        async with AsyncClient() as client:
            try:
                resp = await client.post(
                    url,
                    json={"chat_id": self._chat_id, "text": text, "parse_mode": parse_mode},
                    timeout=10,
                )
                if not resp.is_success:
                    logger.warning("Telegram send failed", status=resp.status_code, body=resp.text)
                    return None
                return resp.json().get("result", {}).get("message_id")
            except Exception as exc:
                logger.error("Telegram send exception", error=str(exc))
                return None

    async def alert(self, title: str, body: str, severity: str = "info") -> int | None:
        emoji = {"info": "ℹ️", "warn": "⚠️", "error": "❌", "critical": "🚨"}.get(severity, "📢")
        return await self.send(f"{emoji} *{title}*\n{body}")

    async def add_inline_buttons(self, message_id: int, buttons: list[list[dict]]) -> None:
        """Attach an inline keyboard to an already-sent message -- used to
        add Take/Skip buttons once a signal_log row (and its id, needed in
        callback_data) exists, without changing alert()'s existing
        send-then-persist ordering. `buttons` is Telegram's own
        inline_keyboard shape: a list of rows, each a list of
        {"text": ..., "callback_data": ...} dicts."""
        if not self._enabled:
            return
        url = TELEGRAM_API.format(token=self._token, method="editMessageReplyMarkup")
        async with AsyncClient() as client:
            try:
                resp = await client.post(
                    url,
                    json={
                        "chat_id": self._chat_id,
                        "message_id": message_id,
                        "reply_markup": {"inline_keyboard": buttons},
                    },
                    timeout=10,
                )
                if not resp.is_success:
                    logger.warning(
                        "Telegram add_inline_buttons failed",
                        status=resp.status_code,
                        body=resp.text,
                    )
            except Exception as exc:
                logger.error("Telegram add_inline_buttons exception", error=str(exc))

    async def edit_message_text(
        self, message_id: int, text: str, parse_mode: str = "Markdown"
    ) -> None:
        """Replace a message's text (and drop its inline keyboard, since
        Telegram clears reply_markup when omitted) -- used after a
        Take/Skip button is pressed, so the message reflects the decision
        instead of still showing clickable buttons."""
        if not self._enabled:
            return
        url = TELEGRAM_API.format(token=self._token, method="editMessageText")
        async with AsyncClient() as client:
            try:
                resp = await client.post(
                    url,
                    json={
                        "chat_id": self._chat_id,
                        "message_id": message_id,
                        "text": text,
                        "parse_mode": parse_mode,
                    },
                    timeout=10,
                )
                if not resp.is_success:
                    logger.warning(
                        "Telegram edit_message_text failed", status=resp.status_code, body=resp.text
                    )
            except Exception as exc:
                logger.error("Telegram edit_message_text exception", error=str(exc))

    async def answer_callback_query(self, callback_query_id: str, text: str = "") -> None:
        """Acknowledges a button press -- Telegram shows a small toast with
        `text` and stops the button's loading spinner. Must be called for
        every callback_query received, even if text is empty, or the
        client-side button stays in a spinning state until it times out."""
        if not self._enabled:
            return
        url = TELEGRAM_API.format(token=self._token, method="answerCallbackQuery")
        async with AsyncClient() as client:
            try:
                await client.post(
                    url, json={"callback_query_id": callback_query_id, "text": text}, timeout=10
                )
            except Exception as exc:
                logger.error("Telegram answer_callback_query exception", error=str(exc))

    async def get_updates(self, offset: int | None, timeout: int = 25) -> list[dict]:
        """Long-polls Telegram's getUpdates -- the inbound half of the bot
        (commands, button presses). Deliberately polling, not a webhook: no
        public HTTPS URL/port needs exposing, works identically in local
        dev and on Render, same "poll out, not in" shape as
        mt5_bridge.py's own channel. Returns [] on any failure rather than
        raising -- the poller loop (telegram_commands.py) treats an empty
        list as "nothing new," not as an error to crash on."""
        if not self._enabled:
            return []
        url = TELEGRAM_API.format(token=self._token, method="getUpdates")
        params: dict = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        async with AsyncClient() as client:
            try:
                # +10s beyond Telegram's own long-poll timeout, so the HTTP
                # client doesn't give up before Telegram itself responds.
                resp = await client.get(url, params=params, timeout=timeout + 10)
                if not resp.is_success:
                    logger.warning("Telegram get_updates failed", status=resp.status_code)
                    return []
                return resp.json().get("result", [])
            except Exception as exc:
                logger.error("Telegram get_updates exception", error=str(exc))
                return []

    async def send_test(self) -> tuple[bool, str]:
        """Like send(), but reports whether it actually worked -- send()
        deliberately swallows every failure (so a broken Telegram config
        never crashes real alerting/trading code), which is exactly the
        wrong contract for a "Send test message" button that needs to tell
        the user whether their bot token/chat ID actually work."""
        if not self._enabled:
            return False, "Bot token and chat ID must both be set first"
        url = TELEGRAM_API.format(token=self._token, method="sendMessage")
        async with AsyncClient() as client:
            try:
                resp = await client.post(
                    url,
                    json={
                        "chat_id": self._chat_id,
                        "text": "✅ Xillion test message — if you can see this, Telegram alerts are working.",
                        "parse_mode": "Markdown",
                    },
                    timeout=10,
                )
                if resp.is_success:
                    return True, "Sent"
                return False, resp.json().get("description", f"HTTP {resp.status_code}")
            except Exception as exc:
                return False, str(exc)
