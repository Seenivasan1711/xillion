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

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


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

    async def send(self, text: str, parse_mode: str = "Markdown") -> None:
        if not self._enabled:
            logger.debug("Telegram not configured; skipping notification")
            return
        url = TELEGRAM_API.format(token=self._token)
        async with AsyncClient() as client:
            try:
                resp = await client.post(
                    url,
                    json={"chat_id": self._chat_id, "text": text, "parse_mode": parse_mode},
                    timeout=10,
                )
                if not resp.is_success:
                    logger.warning("Telegram send failed", status=resp.status_code, body=resp.text)
            except Exception as exc:
                logger.error("Telegram send exception", error=str(exc))

    async def alert(self, title: str, body: str, severity: str = "info") -> None:
        emoji = {"info": "ℹ️", "warn": "⚠️", "error": "❌", "critical": "🚨"}.get(severity, "📢")
        await self.send(f"{emoji} *{title}*\n{body}")

    async def send_test(self) -> tuple[bool, str]:
        """Like send(), but reports whether it actually worked -- send()
        deliberately swallows every failure (so a broken Telegram config
        never crashes real alerting/trading code), which is exactly the
        wrong contract for a "Send test message" button that needs to tell
        the user whether their bot token/chat ID actually work."""
        if not self._enabled:
            return False, "Bot token and chat ID must both be set first"
        url = TELEGRAM_API.format(token=self._token)
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
