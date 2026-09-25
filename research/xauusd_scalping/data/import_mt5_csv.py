"""
Import Rakesh's MT5 exports (View -> Symbols -> Ticks / Bars -> Export) into
the harness's M1 parquet format, under data/<symbol>_mt5/ -- selected at
backtest time with RESEARCH_DATA_SOURCE=mt5 (see engine/instruments.py).

Two export shapes, auto-detected from the header:

  ticks: <DATE> <TIME> <BID> <ASK> <LAST> <VOLUME> <FLAGS>
         Sparse -- a row carries only the side that changed (FLAGS 2=bid,
         4=ask, 6=both), so bid/ask are forward-filled. M1 bars are built
         from the MID, same as download_dukascopy.py, so the two feeds are
         directly comparable. volume = tick count (only ever used as a
         relative VWAP weight -- see signals/indicators.py).
  bars:  <DATE> <TIME> <OPEN> <HIGH> <LOW> <CLOSE> <TICKVOL> <VOL> <SPREAD>
         BID-based OHLC ("Chart mode: By bid price" in the symbol spec);
         shifted to mid by + SPREAD/2 points. Coarser than ticks -- the
         bar's SPREAD column is one reading per minute -- so prefer ticks
         wherever both exist.

Both write an extra `spread_pts` column (median broker spread in the
minute, in MT5 points) -- the loader ignores it, but it's the broker's own
measured cost, which Dukascopy can only proxy.

TIMEZONE. Export timestamps are broker SERVER time, not UTC. Measured
2026-09-25 against Dukascopy's UTC bars (2026-06..09 overlap, 82k bars):
offset +3h gives median |close diff| $0.085; +2h gives $6.58, +4h $6.70.
So summer = UTC+3, winter UTC+2. Which DST calendar (US vs EU) was then
measured per DAY over March 2026, the only month where they differ: under
"ny+7" (US calendar) 2026-03-08..27 matched Dukascopy only at a further +1h
shift, every other day at 0; under "eet" (EU calendar) every day matches.
FundingPips' server clock is EET/EEST -> default "eet". `--verify`
re-measures the offset per month against data/<symbol>/ so a wrong choice
shows up as a flagged month rather than silently shifting session tags.

Usage (from research/xauusd_scalping/):
  python data/import_mt5_csv.py ~/Desktop/XAUUSD_2025...csv --symbol XAUUSD --verify
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.instruments import get_instrument  # noqa: E402

DATA_ROOT = Path(__file__).resolve().parent
CHUNK_ROWS = 5_000_000

# Server clock = a real-world tz + fixed hours. "ny+7": 17:00 New York =
# 00:00 server all year (UTC+2 winter, +3 from the US DST switch).
# "eet": Europe/Helsinki (UTC+2/+3 on the EU calendar).
SERVER_TZ = {"ny+7": ("America/New_York", 7), "eet": ("Europe/Helsinki", 0)}


def server_to_utc(naive: pd.Series, server_tz: str) -> pd.Series:
    tz, shift_h = SERVER_TZ[server_tz]
    local = naive - pd.Timedelta(hours=shift_h)
    # DST-transition hours fall on a weekend (market shut); shift_forward /
    # NaT keeps a stray weekend tick from crashing a 100M-row import.
    return local.dt.tz_localize(tz, ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert("UTC")


def detect_kind(path: Path) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        header = f.readline()
    if "<BID>" in header:
        return "ticks"
    if "<OPEN>" in header:
        return "bars"
    raise ValueError(f"{path.name}: unrecognised MT5 export header {header!r}")


def _ticks_to_m1(df: pd.DataFrame, point: float) -> pd.DataFrame:
    df = df.set_index("ts")
    mid = (df["bid"] + df["ask"]) / 2
    g = mid.resample("1min")
    bars = g.ohlc()
    bars["volume"] = g.count().astype(float)
    bars["spread_pts"] = ((df["ask"] - df["bid"]) / point).resample("1min").median()
    return bars.dropna(subset=["open"]).reset_index()


def import_ticks(path: Path, point: float, server_tz: str) -> pd.DataFrame:
    out: list[pd.DataFrame] = []
    last_bid = last_ask = None
    carry = None  # the trailing (possibly incomplete) minute of the previous chunk
    total = 0
    reader = pd.read_csv(
        path, sep="\t", usecols=[0, 1, 2, 3], names=["date", "time", "bid", "ask"],
        header=0, dtype={"date": str, "time": str, "bid": float, "ask": float},
        chunksize=CHUNK_ROWS,
    )
    for chunk in reader:
        total += len(chunk)
        # Forward-fill across the chunk boundary: seed the first row with the
        # previous chunk's last known quote.
        if last_bid is not None:
            chunk.iloc[0, chunk.columns.get_loc("bid")] = (
                chunk["bid"].iloc[0] if pd.notna(chunk["bid"].iloc[0]) else last_bid)
            chunk.iloc[0, chunk.columns.get_loc("ask")] = (
                chunk["ask"].iloc[0] if pd.notna(chunk["ask"].iloc[0]) else last_ask)
        chunk[["bid", "ask"]] = chunk[["bid", "ask"]].ffill()
        last_bid, last_ask = chunk["bid"].iloc[-1], chunk["ask"].iloc[-1]
        chunk["ts"] = server_to_utc(
            pd.to_datetime(chunk["date"] + " " + chunk["time"], format="%Y.%m.%d %H:%M:%S.%f"), server_tz)
        chunk = chunk.dropna(subset=["ts", "bid", "ask"])[["ts", "bid", "ask"]]
        if carry is not None:
            chunk = pd.concat([carry, chunk], ignore_index=True)
        cut = chunk["ts"].iloc[-1].floor("1min")
        carry = chunk[chunk["ts"] >= cut]
        out.append(_ticks_to_m1(chunk[chunk["ts"] < cut], point))
        print(f"  {total:>12,} ticks read, up to {cut}", flush=True)
    if carry is not None and len(carry):
        out.append(_ticks_to_m1(carry, point))
    return pd.concat(out, ignore_index=True)


def import_bars(path: Path, point: float, server_tz: str) -> pd.DataFrame:
    df = pd.read_csv(path, sep="\t")
    df.columns = [c.strip("<>").lower() for c in df.columns]
    naive = pd.to_datetime(df["date"] + " " + df["time"], format="%Y.%m.%d %H:%M:%S")
    half = df["spread"] * point / 2
    bars = pd.DataFrame({
        "ts": server_to_utc(naive, server_tz),
        "open": df["open"] + half, "high": df["high"] + half,
        "low": df["low"] + half, "close": df["close"] + half,
        "volume": df["tickvol"].astype(float), "spread_pts": df["spread"].astype(float),
    })
    return bars.dropna(subset=["ts"])


def write_monthly(bars: pd.DataFrame, symbol: str, out_dir: Path, overwrite_ticks: bool) -> None:
    """One parquet per month, merged with what's there. Tick-built bars win
    over bar-export bars for the same minute (they're strictly finer)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    bars = bars.copy()
    bars["ts"] = bars["ts"].astype("datetime64[us, UTC]")
    bars["_rank"] = 1 if overwrite_ticks else 0  # 1 = from ticks
    for month, part in bars.groupby(bars["ts"].dt.strftime("%Y-%m")):
        path = out_dir / f"{symbol}_{month}.parquet"
        if path.exists():
            old = pd.read_parquet(path)
            old["_rank"] = old.pop("_from_ticks") if "_from_ticks" in old else 0
            part = pd.concat([old, part], ignore_index=True)
        part = (part.sort_values(["ts", "_rank"]).drop_duplicates("ts", keep="last")
                .rename(columns={"_rank": "_from_ticks"}).reset_index(drop=True))
        part.to_parquet(path, index=False)
        print(f"  {path.name}: {len(part):,} bars", flush=True)


def verify(symbol: str, out_dir: Path) -> None:
    """Per month: best hour offset vs Dukascopy (should be 0 everywhere
    once converted) and median |close diff| at that offset."""
    duka_dir = DATA_ROOT / symbol.lower()
    print(f"\nverify vs {duka_dir.name}/ (Dukascopy UTC):  month  best_shift_h  median|diff|  n")
    for path in sorted(out_dir.glob(f"{symbol}_*.parquet")):
        duka = duka_dir / path.name
        if not duka.exists():
            print(f"  {path.stem[-7:]}  (no Dukascopy month to compare)")
            continue
        m, d = pd.read_parquet(path, columns=["ts", "close"]), pd.read_parquet(duka, columns=["ts", "close"])
        best = None
        for shift in (-1, 0, 1):
            x = m.assign(ts=m["ts"] + pd.Timedelta(hours=shift)).merge(d, on="ts")
            if len(x) < 500:
                continue
            err = (x["close_x"] - x["close_y"]).abs().median()
            if best is None or err < best[1]:
                best = (shift, err, len(x))
        if best is None:
            print(f"  {path.stem[-7:]}  (too little overlap)")
        else:
            flag = "" if best[0] == 0 else "   <-- WRONG OFFSET for this month"
            print(f"  {path.stem[-7:]}  {best[0]:+d}  ${best[1]:.3f}  {best[2]:,}{flag}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--server-tz", choices=sorted(SERVER_TZ), default="eet")
    ap.add_argument("--verify", action="store_true", help="compare each month against data/<symbol>/")
    args = ap.parse_args()

    symbol = args.symbol.upper()
    point = get_instrument(symbol).point_size
    out_dir = DATA_ROOT / f"{symbol.lower()}_mt5"
    # Bars first, ticks second, so tick-built minutes overwrite bar-export ones.
    files = sorted(args.files, key=lambda p: detect_kind(p) == "ticks")
    for path in files:
        kind = detect_kind(path.expanduser())
        print(f"{path.name}: {kind} export, server tz {args.server_tz}", flush=True)
        importer = import_ticks if kind == "ticks" else import_bars
        bars = importer(path.expanduser(), point, args.server_tz)
        print(f"  -> {len(bars):,} M1 bars, {bars['ts'].min()} .. {bars['ts'].max()}", flush=True)
        write_monthly(bars, symbol, out_dir, overwrite_ticks=(kind == "ticks"))
    if args.verify:
        verify(symbol, out_dir)


if __name__ == "__main__":
    main()
