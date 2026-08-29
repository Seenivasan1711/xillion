"""
MT5 bridge historical data provider -- Gold Lane B1's primary backtest data
source (2026-08-29). Piggybacks on the already-connected MT5FundingPipsBroker
the same way data_providers/zerodha_kite.py piggybacks on ZerodhaBroker, but
the underlying fetch mechanism is necessarily different: Kite's Historical
Data API is a normal HTTPS call this backend can make directly, but MT5's
own history only exists inside the real terminal on Rakesh's own machine
(brokers/mt5_funding_pips.py's own module docstring explains why this
backend can never talk to that terminal directly).

So fetch_bars() here does the same thing brokers/mt5_funding_pips.py already
does for live orders: write a request row into the DB (MT5HistoricalRequest,
migration 019) and poll for mt5_bridge/bridge.py -- a separate local
process, already polling this backend every few seconds for order work --
to pick it up on its normal cycle, call MT5's own copy_rates_range()
against the real terminal, and report the bars back via
POST /mt5-bridge/historical-report. This is the "local agent" pattern
Rakesh asked for: the bridge already polls OUT to this backend (not the
other way around, so it works through NAT/firewalls without any inbound
port-forwarding on his Mac) -- this reuses that exact same channel for
historical data instead of inventing a second connection mechanism.

Honest limitation: this only returns data while the bridge is actually
running (Mac awake, MT5 terminal open and logged in, Wine bridge process
alive). If it isn't, fetch_bars() times out with a clear error rather than
hanging forever -- see data_providers/alpha_vantage_fx.py for the backup
source that works even when the bridge is offline.
"""

import asyncio
import json
from datetime import UTC, date, datetime
from decimal import Decimal

import structlog

from xillion.core.data_provider_base import DataProviderCapabilities, HistoricalDataProvider
from xillion.core.events import Bar

logger = structlog.get_logger(__name__)

# How long to wait for the bridge to notice and fulfil a request before
# giving up -- the bridge's own default poll interval is 2s
# (XILLION_MT5_POLL_INTERVAL_SECONDS), so this gives ~30 cycles of margin
# for a running bridge, while still failing within a reasonable HTTP
# request timeout if the bridge is offline rather than hanging forever.
_POLL_TIMEOUT_SECONDS = 60.0
_POLL_INTERVAL_SECONDS = 2.0


class MT5BridgeHistoryProvider(HistoricalDataProvider):
    name = "MT5 Bridge (Gold)"
    version = "1.0.0"
    description = (
        "Historical OHLC via your own MT5 terminal, fetched on demand through the local "
        "bridge (mt5_bridge/bridge.py) -- free, but only works while the bridge is running. "
        "Connect MT5 Funding Pips under Settings -> Brokers first."
    )
    capabilities = DataProviderCapabilities(
        supports_equity=False,
        supports_futures=False,
        supports_options=False,
        supports_forex=True,  # MT5 quotes Gold (XAUUSD) as a forex-style CFD symbol
        requires_credentials=False,  # reuses the MT5 broker's own bridge connection
        requires_broker=True,
        required_broker_name="MT5 Funding Pips",
        max_lookback_days=None,  # bounded only by what MT5's own terminal history holds
    )

    async def fetch_bars(
        self,
        symbol: str,
        exchange: str,
        timeframe: str,
        from_date: date,
        to_date: date,
        *,
        instrument_type: str = "equity",
        credentials: dict | None = None,
        broker=None,
    ) -> list[Bar]:
        if broker is None:
            raise ValueError(
                "MT5 Bridge (Gold) provider needs a connected MT5 Funding Pips broker -- "
                "connect one under Settings -> Brokers first."
            )
        connection_name = getattr(broker, "_connection_name", "MT5 Funding Pips")

        from xillion.db.models import MT5HistoricalRequest
        from xillion.db.session import get_session_factory

        factory = get_session_factory()
        now = datetime.now(UTC).isoformat()
        async with factory() as db:
            row = MT5HistoricalRequest(
                broker_connection_name=connection_name,
                symbol=symbol,
                timeframe=timeframe,
                from_date=from_date.isoformat(),
                to_date=to_date.isoformat(),
                status="PENDING",
                requested_at=now,
            )
            db.add(row)
            await db.commit()
            await db.refresh(row)
            request_id = row.id

        logger.info(
            "mt5 bridge: historical request queued",
            request_id=request_id,
            symbol=symbol,
            timeframe=timeframe,
            from_date=str(from_date),
            to_date=str(to_date),
        )

        waited = 0.0
        while waited < _POLL_TIMEOUT_SECONDS:
            async with factory() as db:
                row = await db.get(MT5HistoricalRequest, request_id)
                if row is not None and row.status in ("DONE", "FAILED"):
                    break
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
            waited += _POLL_INTERVAL_SECONDS
        else:
            raise RuntimeError(
                f"MT5 bridge did not respond within {_POLL_TIMEOUT_SECONDS:.0f}s -- "
                "is your local bridge (mt5_bridge/bridge.py) running, and is the MT5 "
                "terminal open and logged in? Request stays queued -- it will still be "
                "picked up next time the bridge polls, even though this call gave up."
            )

        if row.status == "FAILED":
            raise RuntimeError(f"MT5 bridge reported a failure: {row.error_message}")

        bars_raw = json.loads(row.bars_json) if row.bars_json else []
        return [
            Bar(
                symbol=symbol,
                timeframe=timeframe,
                ts=datetime.fromisoformat(b["ts"]),
                open=Decimal(b["open"]),
                high=Decimal(b["high"]),
                low=Decimal(b["low"]),
                close=Decimal(b["close"]),
                volume=int(b.get("volume") or 0),
            )
            for b in bars_raw
        ]
