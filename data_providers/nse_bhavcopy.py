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

**Legacy pre-2024 format, added 2026-08-25.** The URL above (NSE's "UDiFF"
format) genuinely does not exist before 2024-01-01 -- every request 404s;
confirmed by direct probing (2023-12-01 -> 404, 2024-01-01 -> 200), not
assumed. A real 2-5yr backfill needs NSE's older archive, verified against
an actual downloaded file (2021-06-15), not guessed from search results:
  https://archives.nseindia.com/content/historical/DERIVATIVES/{YYYY}/{MON}/fo{DD}{MON}{YYYY}bhav.csv.zip
Columns: INSTRUMENT (FUTIDX/OPTIDX/FUTSTK/OPTSTK), SYMBOL (underlying),
EXPIRY_DT ("17-Jun-2021"), STRIKE_PR, OPTION_TYP (CE/PE/XX for futures),
OPEN/HIGH/LOW/CLOSE, SETTLE_PR, CONTRACTS, VAL_INLAKH, OPEN_INT,
CHG_IN_OI, TIMESTAMP. No ready-made tradingsymbol field (unlike the new
format's FinInstrmNm) -- _legacy_tradingsymbol() builds one, but it's a
synthetic, internal-only convention (not NSE's or Zerodha's real symbol
format), safe here only because this data is backtest-internal and never
used to place a live order or reconciled against a live broker's own
naming. `_fetch_and_parse_day`/`fetch_option_chain_for_day` try the new
URL first and fall back to the legacy one on a 404, so no hardcoded
cutover date is needed -- correct regardless of exactly which day NSE
switched formats.
"""
import csv
import io
import zipfile
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional

import httpx
import structlog

from xillion.core.data_provider_base import DataProviderCapabilities, HistoricalDataProvider
from xillion.core.events import Bar
from xillion.data.option_chain import HistoricalOptionRow

logger = structlog.get_logger(__name__)

_URL_TEMPLATE = "https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{ymd}_F_0000.csv.zip"
_LEGACY_URL_TEMPLATE = (
    "https://archives.nseindia.com/content/historical/DERIVATIVES/{yyyy}/{mon}/fo{dd}{mon}{yyyy}bhav.csv.zip"
)
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
        underlying_filter: "set[str] | None" = None,
    ) -> list[Bar]:
        """The whole-file lever: one ZIP download covers every F&O
        instrument traded that day, not just the one symbol asked for.
        BarWarehouse persists all of them so later requests for any other
        symbol on this same day cost zero provider calls -- unless
        `underlying_filter` is given, in which case only that filter's
        underlyings (matched against the file's own TckrSymb column) are
        kept, e.g. to scope a real historical backfill down to just the
        underlyings a strategy actually trades instead of the whole
        exchange (85M+ rows for a multi-year NFO backfill otherwise)."""
        if timeframe != "1d":
            raise ValueError(
                f"NSE Bhavcopy (Free) only provides daily bars — got timeframe={timeframe!r}"
            )
        if day.weekday() >= 5:
            return []
        async with httpx.AsyncClient(timeout=30.0, headers={"User-Agent": _USER_AGENT}) as client:
            day_bars = await self._fetch_and_parse_day(client, day, underlying_filter=underlying_filter)
        return list(day_bars.values())

    async def _fetch_and_parse_day(
        self, client: httpx.AsyncClient, day: date, *, underlying_filter: "set[str] | None" = None,
    ) -> dict[str, Bar]:
        """Download and parse one day's whole-market ZIP once, returning
        every instrument's bar keyed by tradingsymbol (or only those whose
        underlying is in `underlying_filter`, if given). Tries the current
        (UDiFF) format first; an empty result -- whether a genuine holiday
        or simply pre-2024 (where that URL never existed) -- falls back to
        the legacy archive, which itself just returns {} for an actual
        holiday, so this never fabricates data either way."""
        result = await self._fetch_and_parse_day_new(client, day, underlying_filter=underlying_filter)
        if result:
            return result
        return await self._fetch_and_parse_day_legacy(client, day, underlying_filter=underlying_filter)

    async def _fetch_and_parse_day_new(
        self, client: httpx.AsyncClient, day: date, *, underlying_filter: "set[str] | None" = None,
    ) -> dict[str, Bar]:
        url = _URL_TEMPLATE.format(ymd=day.strftime("%Y%m%d"))
        try:
            resp = await client.get(url)
            if resp.status_code == 404:
                return {}  # holiday, or simply pre-2024 (see fallback above)
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
                        if underlying_filter is not None and row.get("TckrSymb") not in underlying_filter:
                            continue
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

    async def _fetch_and_parse_day_legacy(
        self, client: httpx.AsyncClient, day: date, *, underlying_filter: "set[str] | None" = None,
    ) -> dict[str, Bar]:
        url = _LEGACY_URL_TEMPLATE.format(
            yyyy=day.strftime("%Y"), mon=day.strftime("%b").upper(), dd=day.strftime("%d"),
        )
        try:
            resp = await client.get(url)
            if resp.status_code == 404:
                return {}  # a genuine holiday -- the legacy file doesn't exist for this day either
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("nse bhavcopy legacy fetch failed", date=str(day), error=str(exc))
            return {}

        result: dict[str, Bar] = {}
        try:
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                csv_name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
                with zf.open(csv_name) as f:
                    reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
                    for row in reader:
                        underlying = (row.get("SYMBOL") or "").strip()
                        if not underlying:
                            continue
                        if underlying_filter is not None and underlying not in underlying_filter:
                            continue
                        sym = self._legacy_tradingsymbol_from_row(row)
                        if sym is None or sym in result:
                            continue
                        bar = self._row_to_bar_legacy(row, sym, day)
                        if bar is not None:
                            result[sym] = bar
        except (zipfile.BadZipFile, StopIteration) as exc:
            logger.warning("nse bhavcopy legacy parse failed", date=str(day), error=str(exc))
            return {}
        return result

    async def fetch_option_chain_for_day(self, day: date) -> list[HistoricalOptionRow]:
        """Point-in-time option/future chain for EVERY underlying traded
        that day, sourced from the same bhavcopy row bar-building already
        parses -- but capturing StrkPric/XpryDt/OptnTp/UndrlygPric, which
        _fetch_and_parse_day discards. Real column names confirmed against
        a live file (2026-08-24), not assumed:
        TckrSymb=underlying, XpryDt=expiry, StrkPric=strike, OptnTp=CE/PE,
        FinInstrmNm=tradingsymbol, NewBrdLotQty=lot size, ClsPric=close,
        UndrlygPric=the exchange's own recorded underlying close -- used as
        the backtest spot proxy so no separate index-bhavcopy fetch is
        needed. NSE-listed derivatives only (exchange hardcoded "NFO") --
        Sensex is BSE-listed and isn't in this file at all.

        Same new-format-first, legacy-fallback shape as
        _fetch_and_parse_day -- see _fetch_option_chain_for_day_legacy for
        the two real, honestly-documented approximations pre-2024 dates
        carry that this new-format path doesn't need."""
        if day.weekday() >= 5:
            return []
        async with httpx.AsyncClient(timeout=30.0, headers={"User-Agent": _USER_AGENT}) as client:
            rows = await self._fetch_option_chain_for_day_new(client, day)
            if rows:
                return rows
            return await self._fetch_option_chain_for_day_legacy(client, day)

    async def _fetch_option_chain_for_day_new(
        self, client: httpx.AsyncClient, day: date,
    ) -> list[HistoricalOptionRow]:
        url = _URL_TEMPLATE.format(ymd=day.strftime("%Y%m%d"))
        try:
            resp = await client.get(url)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("nse bhavcopy option-chain fetch failed", date=str(day), error=str(exc))
            return []

        rows: list[HistoricalOptionRow] = []
        try:
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                csv_name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
                with zf.open(csv_name) as f:
                    reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
                    for raw in reader:
                        parsed = self._row_to_option_row(raw)
                        if parsed is not None:
                            rows.append(parsed)
        except (zipfile.BadZipFile, StopIteration) as exc:
            logger.warning("nse bhavcopy option-chain parse failed", date=str(day), error=str(exc))
            return []
        return rows

    async def _fetch_option_chain_for_day_legacy(
        self, client: httpx.AsyncClient, day: date,
    ) -> list[HistoricalOptionRow]:
        """Two real, honestly-documented approximations that the new-format
        path above doesn't need, both because the legacy file simply
        doesn't carry the real column:
        - `underlying_price`: no UndrlygPric equivalent exists pre-2024.
          Approximated from the SAME underlying's nearest-expiry
          FUTIDX/FUTSTK contract CLOSE on the same day -- index futures
          trade close to spot, but this is a proxy, not NSE's own recorded
          value. `get_underlying_price`/`get_spot` callers should treat a
          pre-2024 backtest's spot price as approximate, not exact.
        - `lot_size`: no NewBrdLotQty equivalent exists pre-2024 either,
          and NIFTY/BANKNIFTY's real lot size changed multiple times across
          2021-2023 -- there's no verified free source for the exact lot
          size on an arbitrary historical date. Rather than silently
          guessing a number that would misprice position sizing, this
          returns 0, which position sizing (size_defined_risk_position)
          already turns into a loud ValueError instead of a wrong trade --
          see xillion/core/multileg.py. A real historical lot-size table
          would need to replace this before pre-2024 backtests can size
          positions at all."""
        url = _LEGACY_URL_TEMPLATE.format(
            yyyy=day.strftime("%Y"), mon=day.strftime("%b").upper(), dd=day.strftime("%d"),
        )
        try:
            resp = await client.get(url)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("nse bhavcopy legacy option-chain fetch failed", date=str(day), error=str(exc))
            return []

        raw_rows: list[dict] = []
        try:
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                csv_name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
                with zf.open(csv_name) as f:
                    raw_rows = list(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8")))
        except (zipfile.BadZipFile, StopIteration) as exc:
            logger.warning("nse bhavcopy legacy option-chain parse failed", date=str(day), error=str(exc))
            return []

        # Nearest-expiry future close per underlying, for the spot proxy.
        future_closes: dict[str, list[tuple[date, Decimal]]] = {}
        for row in raw_rows:
            if (row.get("INSTRUMENT") or "").strip() not in ("FUTIDX", "FUTSTK"):
                continue
            underlying = (row.get("SYMBOL") or "").strip()
            expiry = self._parse_legacy_expiry(row.get("EXPIRY_DT"))
            if not underlying or expiry is None:
                continue
            try:
                close = Decimal(row["CLOSE"])
            except (KeyError, InvalidOperation):
                continue
            if close > 0:
                future_closes.setdefault(underlying, []).append((expiry, close))

        def _spot_proxy(underlying: str) -> Optional[Decimal]:
            candidates = future_closes.get(underlying)
            if not candidates:
                return None
            return min(candidates, key=lambda c: c[0])[1]

        rows: list[HistoricalOptionRow] = []
        for row in raw_rows:
            parsed = self._row_to_option_row_legacy(row, _spot_proxy)
            if parsed is not None:
                rows.append(parsed)
        return rows

    @staticmethod
    def _row_to_option_row(row: dict) -> "HistoricalOptionRow | None":
        try:
            tradingsymbol = row["FinInstrmNm"]
            underlying = row["TckrSymb"]
            if not tradingsymbol or not underlying:
                return None
            expiry_str = row.get("XpryDt") or ""
            expiry = date.fromisoformat(expiry_str) if expiry_str else None
            strike_str = (row.get("StrkPric") or "").strip()
            strike = Decimal(strike_str) if strike_str and strike_str != "-1" else None
            option_type = (row.get("OptnTp") or "").strip() or None
            if option_type not in ("CE", "PE"):
                option_type = None
            lot_size = int(float(row.get("NewBrdLotQty") or 0))
            close = Decimal(row["ClsPric"])
            underlying_price_str = (row.get("UndrlygPric") or "").strip()
            underlying_price = Decimal(underlying_price_str) if underlying_price_str else None
            return HistoricalOptionRow(
                tradingsymbol=tradingsymbol, exchange="NFO", underlying=underlying,
                expiry=expiry, strike=strike, option_type=option_type, lot_size=lot_size,
                close=close, underlying_price=underlying_price,
            )
        except (KeyError, InvalidOperation, ValueError):
            return None

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

    # ── Legacy (pre-2024) format helpers ────────────────────────────────────────

    @staticmethod
    def _parse_legacy_expiry(expiry_str: "str | None") -> Optional[date]:
        if not expiry_str:
            return None
        try:
            return datetime.strptime(expiry_str.strip(), "%d-%b-%Y").date()
        except ValueError:
            return None

    @classmethod
    def _legacy_tradingsymbol_from_row(cls, row: dict) -> Optional[str]:
        """Synthetic, internal-only convention -- see this module's
        docstring for why (no ready-made tradingsymbol column pre-2024,
        and this data never needs to match NSE's/Zerodha's real naming
        since it's backtest-internal only)."""
        instrument = (row.get("INSTRUMENT") or "").strip()
        if instrument not in ("FUTIDX", "OPTIDX", "FUTSTK", "OPTSTK"):
            return None
        underlying = (row.get("SYMBOL") or "").strip()
        expiry = cls._parse_legacy_expiry(row.get("EXPIRY_DT"))
        if not underlying or expiry is None:
            return None
        expiry_tag = expiry.strftime("%d%b%y").upper()
        if instrument in ("FUTIDX", "FUTSTK"):
            return f"{underlying}{expiry_tag}FUT"
        strike_str = (row.get("STRIKE_PR") or "").strip()
        option_typ = (row.get("OPTION_TYP") or "").strip()
        if not strike_str or option_typ not in ("CE", "PE"):
            return None
        try:
            strike_int = int(float(strike_str))
        except ValueError:
            return None
        return f"{underlying}{expiry_tag}{strike_int}{option_typ}"

    @classmethod
    def _row_to_bar_legacy(cls, row: dict, symbol: str, day: date) -> Bar | None:
        try:
            return Bar(
                symbol=symbol,
                timeframe="1d",
                ts=datetime.combine(day, datetime.min.time()),
                open=Decimal(row["OPEN"]),
                high=Decimal(row["HIGH"]),
                low=Decimal(row["LOW"]),
                close=Decimal(row["CLOSE"]),
                volume=int(float(row.get("CONTRACTS") or 0)),
            )
        except (KeyError, InvalidOperation, ValueError):
            return None

    @classmethod
    def _row_to_option_row_legacy(cls, row: dict, spot_proxy_fn) -> "HistoricalOptionRow | None":
        """`spot_proxy_fn(underlying) -> Optional[Decimal]` -- see
        _fetch_option_chain_for_day_legacy's docstring for what this
        approximates and why. `lot_size=0` is deliberate, not a bug: see
        the same docstring -- it turns into a loud ValueError in
        size_defined_risk_position rather than a silently wrong trade."""
        instrument = (row.get("INSTRUMENT") or "").strip()
        if instrument not in ("FUTIDX", "OPTIDX", "FUTSTK", "OPTSTK"):
            return None
        underlying = (row.get("SYMBOL") or "").strip()
        tradingsymbol = cls._legacy_tradingsymbol_from_row(row)
        if not underlying or tradingsymbol is None:
            return None
        expiry = cls._parse_legacy_expiry(row.get("EXPIRY_DT"))
        strike_str = (row.get("STRIKE_PR") or "").strip()
        option_type = (row.get("OPTION_TYP") or "").strip()
        strike = None
        if instrument in ("OPTIDX", "OPTSTK") and option_type in ("CE", "PE"):
            try:
                strike = Decimal(strike_str) if strike_str else None
            except InvalidOperation:
                strike = None
        else:
            option_type = None
        try:
            close = Decimal(row["CLOSE"])
        except (KeyError, InvalidOperation):
            return None
        return HistoricalOptionRow(
            tradingsymbol=tradingsymbol, exchange="NFO", underlying=underlying,
            expiry=expiry, strike=strike, option_type=option_type, lot_size=0,
            close=close, underlying_price=spot_proxy_fn(underlying),
        )
