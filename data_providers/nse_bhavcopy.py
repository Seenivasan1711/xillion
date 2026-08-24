"""
Free historical data provider: NSE's own official F&O bhavcopy archive.
No API key, no broker connection -- just NSE's public end-of-day dump.

URL format and columns verified directly against a live file on 2026-08-03:
  https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_YYYYMMDD_F_0000.csv.zip
Columns include TckrSymb (underlying), FinInstrmNm (full tradingsymbol),
FinInstrmTp (IDO=index option, IDF=index future, STO/STF=stock equivalents),
OpnPric/HghPric/LwPric/ClsPric, TtlTradgVol.

Daily granularity only -- bhavcopy is an end-of-day file, there's no
intraday data at this tier. That's the tradeoff for "free": see
docs/13-quantman-parity-roadmap.md's data-provider comparison table for
paid alternatives (TrueData, Global Datafeeds) once intraday/OI/IV history
is actually needed.
"""
import csv
import io
import zipfile
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

import httpx
import structlog

from xillion.core.data_provider_base import DataProviderCapabilities, HistoricalDataProvider
from xillion.core.events import Bar

logger = structlog.get_logger(__name__)

_URL_TEMPLATE = "https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{ymd}_F_0000.csv.zip"
_USER_AGENT = "Mozilla/5.0 (compatible; xillion-backtester/1.0)"


class NSEBhavcopyProvider(HistoricalDataProvider):
    name = "NSE Bhavcopy (Free)"
    version = "1.0.0"
    description = (
        "Official NSE F&O end-of-day archive. Free, no API key. Daily bars "
        "only (no intraday). Symbol must be the full tradingsymbol for "
        "options/futures (e.g. NIFTY2680426150CE), matching how resolved "
        "instruments are named elsewhere in xillion."
    )
    capabilities = DataProviderCapabilities(
        supports_equity=False,
        supports_futures=True,
        supports_options=True,
        supports_forex=False,
        requires_credentials=False,
        requires_broker=False,
        max_lookback_days=None,  # NSE archives go back to 1994
        supports_whole_file_bulk=True,
    )

    async def fetch_bars(
        self,
        symbol: str,
        exchange: str,
        timeframe: str,
        from_date: date,
        to_date: date,
        *,
        instrument_type: str = "option",
        credentials=None,
        broker=None,
    ) -> list[Bar]:
        if timeframe != "1d":
            raise ValueError(
                f"NSE Bhavcopy (Free) only provides daily bars — got timeframe={timeframe!r}"
            )

        bars: list[Bar] = []
        async with httpx.AsyncClient(timeout=30.0, headers={"User-Agent": _USER_AGENT}) as client:
            day = from_date
            while day <= to_date:
                if day.weekday() < 5:  # skip weekends outright, no point requesting
                    day_bars = await self._fetch_and_parse_day(client, day)
                    bar = day_bars.get(symbol)
                    if bar is not None:
                        bars.append(bar)
                day += timedelta(days=1)
        return bars

    async def fetch_all_bars_for_day(
        self,
        exchange: str,
        timeframe: str,
        day: date,
        *,
        credentials=None,
        broker=None,
    ) -> list[Bar]:
        """The whole-file lever: one ZIP download covers every F&O
        instrument traded that day, not just the one symbol asked for.
        BarWarehouse persists all of them so later requests for any other
        symbol on this same day cost zero provider calls."""
        if timeframe != "1d":
            raise ValueError(
                f"NSE Bhavcopy (Free) only provides daily bars — got timeframe={timeframe!r}"
            )
        if day.weekday() >= 5:
            return []
        async with httpx.AsyncClient(timeout=30.0, headers={"User-Agent": _USER_AGENT}) as client:
            day_bars = await self._fetch_and_parse_day(client, day)
        return list(day_bars.values())

    async def _fetch_and_parse_day(self, client: httpx.AsyncClient, day: date) -> dict[str, Bar]:
        """Download and parse one day's whole-market ZIP once, returning
        every instrument's bar keyed by tradingsymbol."""
        url = _URL_TEMPLATE.format(ymd=day.strftime("%Y%m%d"))
        try:
            resp = await client.get(url)
            if resp.status_code == 404:
                return {}  # holiday / no trading that day
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("nse bhavcopy fetch failed", date=str(day), error=str(exc))
            return {}

        result: dict[str, Bar] = {}
        try:
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                csv_name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
                with zf.open(csv_name) as f:
                    reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
                    for row in reader:
                        sym = row.get("FinInstrmNm") or row.get("TckrSymb")
                        if not sym or sym in result:
                            continue
                        bar = self._row_to_bar(row, sym, day)
                        if bar is not None:
                            result[sym] = bar
        except (zipfile.BadZipFile, StopIteration) as exc:
            logger.warning("nse bhavcopy parse failed", date=str(day), error=str(exc))
            return {}
        return result

    @staticmethod
    def _row_to_bar(row: dict, symbol: str, day: date) -> Bar | None:
        try:
            return Bar(
                symbol=symbol,
                timeframe="1d",
                ts=datetime.combine(day, datetime.min.time()),
                open=Decimal(row["OpnPric"]),
                high=Decimal(row["HghPric"]),
                low=Decimal(row["LwPric"]),
                close=Decimal(row["ClsPric"]),
                volume=int(float(row.get("TtlTradgVol") or 0)),
            )
        except (KeyError, InvalidOperation, ValueError):
            return None
