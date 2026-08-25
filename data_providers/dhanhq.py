"""
DhanHQ v2 historical data provider. Needs a Dhan API access token + client
ID -- configure under Settings → Data Providers.

Verified 2026-08-03 against DhanHQ's official Python SDK source
(github.com/dhan-oss/DhanHQ-py: _historical_data.py for exact request
payload fields, dhan_http.py for base URL/auth headers) and the official
docs (dhanhq.co/docs/v2/historical-data/, /docs/v2/annexure/) for the
response shape and exchangeSegment/instrument enum values. The instrument
master CSV URL and its columns were verified against a real downloaded
file. NOT live-tested against an authenticated API response -- no Dhan
account credentials available in this environment. Same caveat as
zerodha_kite.py: structurally correct, unverified end-to-end.

Symbol resolution: Dhan identifies instruments by a numeric securityId, not
a tradingsymbol, so `symbol` here must match DHAN'S OWN naming convention
from their instrument master (e.g. "NIFTY-Aug2026-FUT"), not Kite/NSE-style
"NIFTY26AUGFUT" used elsewhere in xillion. This is the same
provider-specific-symbol-format tradeoff as nse_bhavcopy.py.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

import httpx
import structlog

from xillion.core.data_provider_base import DataProviderCapabilities, HistoricalDataProvider
from xillion.core.dhan_instruments import ResolvedSecurity, ensure_scrip_master, resolve_security
from xillion.core.events import Bar

logger = structlog.get_logger(__name__)

_BASE_URL = "https://api.dhan.co/v2"

_INTRADAY_INTERVAL = {"1m": 1, "5m": 5, "15m": 15, "1h": 60}
_INTRADAY_MAX_DAYS_PER_REQUEST = 85  # Dhan's real limit is 90; leave margin


class DhanHQProvider(HistoricalDataProvider):
    name = "DhanHQ"
    version = "1.0.0"
    description = (
        "DhanHQ v2 Historical Data API. Auto-configured from the same "
        "access token + client ID you enter under Configuration → Brokers "
        "→ Dhan — no need to enter it twice, this only needs its own "
        "entry below if you want DhanHQ for data without connecting Dhan "
        "as a trading broker. Symbol must match Dhan's own naming "
        "convention (e.g. \"NIFTY-Aug2026-FUT\", not Kite/NSE-style "
        "\"NIFTY26AUGFUT\") — resolved via Dhan's own instrument master, "
        "cached locally for 24h. Intraday: last 90 days per request "
        "(auto-chunked here). Daily: since listing."
    )
    capabilities = DataProviderCapabilities(
        supports_equity=True,
        supports_futures=True,
        supports_options=True,
        supports_forex=False,
        requires_credentials=True,
        requires_broker=False,
        max_lookback_days=None,
    )
    credential_fields = [
        ("api_key", "Access token", "password"),
        ("api_secret", "Client ID", "text"),
    ]

    async def fetch_bars(
        self,
        symbol: str,
        exchange: str,
        timeframe: str,
        from_date: date,
        to_date: date,
        *,
        instrument_type: str = "equity",
        credentials: Optional[dict] = None,
        broker=None,
    ) -> list[Bar]:
        if not credentials or not credentials.get("api_key") or not credentials.get("api_secret"):
            raise ValueError(
                "DhanHQ needs an access token and client ID — configure it "
                "under Settings → Data Providers (API key = access token, "
                "API secret = client ID)"
            )
        access_token = credentials["api_key"]
        client_id = credentials["api_secret"]

        if timeframe != "1d" and timeframe not in _INTRADAY_INTERVAL:
            raise ValueError(
                f"DhanHQ doesn't support timeframe={timeframe!r} (supports: 1d, "
                f"{', '.join(_INTRADAY_INTERVAL)})"
            )

        headers = {
            "access-token": access_token,
            "client-id": client_id,
            "Content-type": "application/json",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            master_path = await ensure_scrip_master(client)
            resolved = resolve_security(master_path, symbol)
            if resolved is None:
                raise ValueError(
                    f"Couldn't find '{symbol}' in Dhan's instrument master — "
                    f"use Dhan's own naming (e.g. NIFTY-Aug2026-FUT), not "
                    f"another provider's symbol format"
                )

            if timeframe == "1d":
                return await self._fetch_daily(client, headers, resolved, symbol, from_date, to_date)
            return await self._fetch_intraday(client, headers, resolved, symbol, timeframe, from_date, to_date)

    async def _fetch_daily(
        self, client: httpx.AsyncClient, headers: dict, resolved: ResolvedSecurity,
        symbol: str, from_date: date, to_date: date,
    ) -> list[Bar]:
        payload = {
            "securityId": resolved.security_id,
            "exchangeSegment": resolved.exchange_segment,
            "instrument": resolved.instrument,
            "expiryCode": 0,
            "oi": False,
            "fromDate": from_date.isoformat(),
            "toDate": to_date.isoformat(),
        }
        resp = await client.post(f"{_BASE_URL}/charts/historical", json=payload, headers=headers)
        resp.raise_for_status()
        return self._parse_response(resp.json(), symbol, "1d")

    async def _fetch_intraday(
        self, client: httpx.AsyncClient, headers: dict, resolved: ResolvedSecurity,
        symbol: str, timeframe: str, from_date: date, to_date: date,
    ) -> list[Bar]:
        bars: list[Bar] = []
        chunk_start = from_date
        while chunk_start <= to_date:
            chunk_end = min(chunk_start + timedelta(days=_INTRADAY_MAX_DAYS_PER_REQUEST), to_date)
            payload = {
                "securityId": resolved.security_id,
                "exchangeSegment": resolved.exchange_segment,
                "instrument": resolved.instrument,
                "interval": _INTRADAY_INTERVAL[timeframe],
                "oi": False,
                "fromDate": f"{chunk_start.isoformat()} 09:00:00",
                "toDate": f"{chunk_end.isoformat()} 16:00:00",
            }
            resp = await client.post(f"{_BASE_URL}/charts/intraday", json=payload, headers=headers)
            resp.raise_for_status()
            bars.extend(self._parse_response(resp.json(), symbol, timeframe))
            chunk_start = chunk_end + timedelta(days=1)
        return bars

    @staticmethod
    def _parse_response(data: dict, symbol: str, timeframe: str) -> list[Bar]:
        opens = data.get("open", [])
        highs = data.get("high", [])
        lows = data.get("low", [])
        closes = data.get("close", [])
        volumes = data.get("volume", [])
        timestamps = data.get("timestamp", [])
        bars = []
        for i in range(len(timestamps)):
            bars.append(
                Bar(
                    symbol=symbol,
                    timeframe=timeframe,
                    ts=datetime.fromtimestamp(timestamps[i], tz=timezone.utc).replace(tzinfo=None),
                    open=Decimal(str(opens[i])),
                    high=Decimal(str(highs[i])),
                    low=Decimal(str(lows[i])),
                    close=Decimal(str(closes[i])),
                    volume=int(volumes[i]) if i < len(volumes) else 0,
                )
            )
        return bars
