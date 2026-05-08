"""
Telegram notifier. Sends alerts via the Telegram Bot API.
Configure TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env.
"""
import structlog
from httpx import AsyncClient

from xillion.config import settings

logger = structlog.get_logger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier:
    def __init__(self) -> None:
        self._token = settings.telegram_bot_token
        self._chat_id = settings.telegram_chat_id
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
