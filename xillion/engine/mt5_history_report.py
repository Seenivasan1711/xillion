"""
Parse an MT5 "Trade History Report" (History tab -> right-click -> Report ->
HTML) into closed positions, for My Trades import (2026-09-26).

The report is an HTML page of <tr>/<td> rows split into sections by a
single-cell heading row ("Positions", "Orders", "Deals", ...). Only the
Positions section is read: one row per closed position, with open and close
on the same row --

  Time | Position | Symbol | Type | Volume | Price | S / L | T / P |
  Time | Price | Commission | Swap | Profit

Robust to what real reports do: UTF-16 encoding (the MT5 default) or
UTF-8, numbers with space thousands separators ("4 637.49"), and header
cells repeated (two "Time"/"Price" columns -- read by position, not name).

Times are broker SERVER time; FundingPips' server is EET/EEST (measured
2026-09-25 against a UTC feed -- research/xauusd_scalping/data/
import_mt5_csv.py), converted here to UTC ISO strings.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

SERVER_TZ = ZoneInfo("Europe/Helsinki")
UTC = ZoneInfo("UTC")

POSITION_COLUMNS = [
    "open_time",
    "position",
    "symbol",
    "type",
    "volume",
    "open_price",
    "sl",
    "tp",
    "close_time",
    "close_price",
    "commission",
    "swap",
    "profit",
]


@dataclass(frozen=True)
class ReportPosition:
    ticket: str
    symbol: str
    side: str  # BUY | SELL
    volume_lots: float
    open_time: str  # UTC ISO
    open_price: float
    close_time: str | None
    close_price: float | None
    stop_loss: float | None
    take_profit: float | None
    commission: float
    swap: float
    profit: float


class _Rows(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
            span = dict(attrs).get("colspan")
            self._span = int(span) if span and span.isdigit() else 1

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._row is not None and self._cell is not None:
            text = " ".join("".join(self._cell).split())
            self._row.append(text)
            self._row.extend([""] * (self._span - 1))  # keep column positions aligned
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(c for c in self._row):
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def decode_report(raw: bytes) -> str:
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    if len(raw) > 1 and raw[1:2] == b"\x00":  # UTF-16 LE without BOM
        return raw.decode("utf-16-le")
    return raw.decode("utf-8", errors="replace")


def _num(s: str) -> float | None:
    s = s.replace("\xa0", "").replace(" ", "").replace(",", "")
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _utc(server_time: str) -> str | None:
    s = server_time.strip()
    for fmt in ("%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M"):
        try:
            local = datetime.strptime(s, fmt).replace(tzinfo=SERVER_TZ)
            return local.astimezone(UTC).isoformat()
        except ValueError:
            continue
    return None


@dataclass(frozen=True)
class ReportAccount:
    login: str | None  # e.g. "112555079"
    server: str | None  # e.g. "MetaQuotes-Demo"
    is_demo: bool


def parse_account(raw: bytes) -> ReportAccount:
    """The header row 'Account: 112555079 (USD, MetaQuotes-Demo, demo, Hedge)'
    (verified against a real report, 2026-09-26)."""
    p = _Rows()
    p.feed(decode_report(raw))
    for r in p.rows[:12]:
        cells = [c for c in r if c]
        if len(cells) >= 2 and cells[0].rstrip(":").lower() == "account":
            text = cells[1]
            login = text.split(" ", 1)[0] or None
            inner = text[text.find("(") + 1 : text.rfind(")")] if "(" in text else ""
            parts = [x.strip() for x in inner.split(",")]
            server = parts[1] if len(parts) > 1 else None
            return ReportAccount(
                login=login, server=server, is_demo="demo" in [x.lower() for x in parts]
            )
    return ReportAccount(login=None, server=None, is_demo=False)


def parse_positions(raw: bytes) -> tuple[list[ReportPosition], list[str]]:
    """Returns (closed positions, warnings). Raises ValueError if the file has
    no Positions section at all (i.e. isn't an MT5 history report)."""
    p = _Rows()
    p.feed(decode_report(raw))
    rows = p.rows
    start = next((i for i, r in enumerate(rows) if [c for c in r if c] == ["Positions"]), None)
    if start is None:
        raise ValueError("no 'Positions' section found -- expected an MT5 History report (HTML)")
    out: list[ReportPosition] = []
    warnings: list[str] = []
    for r in rows[start + 1 :]:
        cells = [c for c in r]
        nonempty = [c for c in cells if c]
        if len(nonempty) == 1 and not nonempty[0][:1].isdigit():
            break  # next section heading ("Orders", "Deals", ...)
        if cells and cells[0] == "Time":
            continue  # header row
        # MT5 pads rows with empty spacer cells in some builds; drop empties
        # only at the end so positional columns stay aligned.
        vals = cells[:]
        while vals and vals[-1] == "":
            vals.pop()
        if len(vals) < len(POSITION_COLUMNS):
            continue
        row = dict(zip(POSITION_COLUMNS, vals[: len(POSITION_COLUMNS)], strict=True))
        side = row["type"].strip().upper()
        if side not in ("BUY", "SELL"):
            continue  # balance/credit lines etc.
        open_time = _utc(row["open_time"])
        open_price = _num(row["open_price"])
        volume = _num(row["volume"])
        if open_time is None or open_price is None or volume is None:
            warnings.append(f"skipped unreadable row: {' | '.join(nonempty)[:120]}")
            continue
        out.append(
            ReportPosition(
                ticket=row["position"].strip(),
                symbol=row["symbol"].strip(),
                side=side,
                volume_lots=volume,
                open_time=open_time,
                open_price=open_price,
                close_time=_utc(row["close_time"]),
                close_price=_num(row["close_price"]),
                stop_loss=_num(row["sl"]) or None,
                take_profit=_num(row["tp"]) or None,
                commission=_num(row["commission"]) or 0.0,
                swap=_num(row["swap"]) or 0.0,
                profit=_num(row["profit"]) or 0.0,
            )
        )
    return out, warnings
