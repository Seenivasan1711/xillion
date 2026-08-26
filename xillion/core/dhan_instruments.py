"""
Dhan instrument (scrip master) resolution -- shared between
data_providers/dhanhq.py (historical data) and brokers/dhan.py (CP15, live
trading), since both need the exact same symbol -> securityId/
exchangeSegment lookup. Extracted here rather than duplicated so a fix to
one applies to both.

Verified 2026-08-03 against DhanHQ's official Python SDK source
(github.com/dhan-oss/DhanHQ-py) and docs (dhanhq.co/docs/v2/annexure/) for
the exchangeSegment enum values; the instrument master CSV URL and its
columns were verified against a real downloaded file. Dhan identifies
instruments by a numeric securityId, not a tradingsymbol -- `symbol` here
must match Dhan's own naming convention from their instrument master (e.g.
"NIFTY-Aug2026-FUT"), not Kite/NSE-style "NIFTY26AUGFUT" used elsewhere.
"""

import csv
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import structlog

logger = structlog.get_logger(__name__)

SCRIP_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"
SCRIP_MASTER_CACHE = Path("data/dhan_scrip_master.csv")
SCRIP_MASTER_TTL = timedelta(hours=24)

# String exchangeSegment (used by REST order/quote/historical endpoints) ->
# numeric segment code (used by the MarketFeed WebSocket's subscribe
# messages) -- two different enums for the same exchanges, both verified
# against the official SDK's marketfeed.py (get_exchange_segment) and
# dhanhq.py class constants.
EXCHANGE_SEGMENT_TO_FEED_CODE = {
    "IDX_I": 0,
    "NSE_EQ": 1,
    "NSE_FNO": 2,
    "NSE_CURRENCY": 3,
    "BSE_EQ": 4,
    "MCX_COMM": 5,
    "BSE_CURRENCY": 7,
    "BSE_FNO": 8,
}


def exchange_segment(exch_id: str, instrument: str) -> str:
    """Maps the scrip master's EXCH_ID + INSTRUMENT columns to the
    exchangeSegment enum the API actually expects -- related but not the
    same value (verified against dhanhq.co/docs/v2/annexure/)."""
    if instrument == "INDEX":
        return "IDX_I"
    if exch_id == "NSE":
        if instrument == "EQUITY":
            return "NSE_EQ"
        if instrument in ("FUTIDX", "OPTIDX", "FUTSTK", "OPTSTK"):
            return "NSE_FNO"
        if instrument in ("FUTCUR", "OPTCUR"):
            return "NSE_CURRENCY"
    if exch_id == "BSE":
        if instrument == "EQUITY":
            return "BSE_EQ"
        if instrument in ("FUTIDX", "OPTIDX", "FUTSTK", "OPTSTK"):
            return "BSE_FNO"
        if instrument in ("FUTCUR", "OPTCUR"):
            return "BSE_CURRENCY"
    if exch_id == "MCX":
        return "MCX_COMM"
    raise ValueError(f"No known exchangeSegment for EXCH_ID={exch_id!r} INSTRUMENT={instrument!r}")


@dataclass
class ResolvedSecurity:
    security_id: str
    exchange_segment: str
    instrument: str
    lot_size: int = 1
    tick_size: str = "0.05"


async def ensure_scrip_master(client: httpx.AsyncClient) -> Path:
    if SCRIP_MASTER_CACHE.exists():
        age = datetime.now(UTC) - datetime.fromtimestamp(SCRIP_MASTER_CACHE.stat().st_mtime, tz=UTC)
        if age < SCRIP_MASTER_TTL:
            return SCRIP_MASTER_CACHE

    resp = await client.get(SCRIP_MASTER_URL)
    resp.raise_for_status()
    SCRIP_MASTER_CACHE.parent.mkdir(parents=True, exist_ok=True)
    SCRIP_MASTER_CACHE.write_bytes(resp.content)
    logger.info("dhan scrip master refreshed", size=len(resp.content))
    return SCRIP_MASTER_CACHE


def resolve_security(master_path: Path, symbol: str) -> ResolvedSecurity | None:
    with master_path.open(encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("SYMBOL_NAME") == symbol or row.get("DISPLAY_NAME") == symbol:
                try:
                    seg = exchange_segment(row["EXCH_ID"], row["INSTRUMENT"])
                except ValueError:
                    continue
                return ResolvedSecurity(
                    security_id=row["SECURITY_ID"],
                    exchange_segment=seg,
                    instrument=row["INSTRUMENT"],
                    # LOT_SIZE is float-formatted in the real file ("1.0",
                    # not "1") -- int() on that string raises ValueError.
                    lot_size=int(float(row.get("LOT_SIZE") or 1)),
                    tick_size=row.get("TICK_SIZE") or "0.05",
                )
    return None
