"""
Pre-trade AI confidence hook (CP8): asks a configured LLM backend (today,
prosper-engine's /confidence endpoint) how confident it is in an ENTER
signal before it goes out, so the score can be logged against what actually
happened later (see xillion/engine/journal.py, which surfaces this
alongside the real outcome instead of asking anyone to trust it on faith).

Disabled by default (AI_CONFIDENCE_URL unset) -- get_confidence() then
returns None immediately, no network call, alert mode behaves exactly as
it did before this existed. When configured, any failure (timeout, bad
response, backend down) also returns None rather than raising -- a review
service being unavailable must never block or break a real alert.
"""
from typing import Optional

import httpx
import structlog

from xillion.config import settings

logger = structlog.get_logger(__name__)


async def get_confidence(
    symbol: str,
    side: str,
    price: Optional[float],
    target_price: Optional[float],
    stop_loss_price: Optional[float],
    tag: Optional[str],
) -> Optional[float]:
    if not settings.ai_confidence_url:
        return None
    try:
        async with httpx.AsyncClient(timeout=settings.ai_confidence_timeout_seconds) as client:
            resp = await client.post(
                settings.ai_confidence_url,
                json={
                    "symbol": symbol, "side": side, "price": price,
                    "target_price": target_price, "stop_loss_price": stop_loss_price,
                    "tag": tag,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            confidence = data.get("confidence")
            if confidence is None:
                return None
            return max(0.0, min(100.0, float(confidence)))
    except Exception as exc:
        logger.warning("ai confidence lookup failed, continuing without it", error=str(exc), symbol=symbol)
        return None
