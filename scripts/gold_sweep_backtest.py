#!/usr/bin/env python3
"""
XAUUSD Sweep-Reversal Backtester  v2

Strategy under test
-------------------
  Mark 4 lines per day: Asian session high/low, previous-day high/low.
  Price sweeps beyond a line, then an M5 candle closes back inside.
  Enter at that close, against the sweep.
  SL = SL_BUFFER beyond the sweep extreme, minimum MIN_SL_PTS.
  TP = fixed points.  Max 2 trades/day, one open at a time.

External reference tool, not part of the live xillion pipeline. Requires
the Windows-only MetaTrader5 package (or a CSV export on Mac/Linux) --
see docs/strategies/gold-xauusd-sweep-reversal.md for full context, usage,
and the SQLite schema this writes to.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

# ===================== CONFIG =====================

SYMBOL = "XAUUSD"
MONTHS_BACK = 6
SERVER_UTC_OFFSET = 3  # EET: 3 in summer, 2 in winter

ASIAN_START_UTC, ASIAN_END_UTC = 0.0, 7.0  # 05:30 - 12:30 IST

WINDOWS = [
    ("London", 7.0, 13.0),  # 12:30 - 18:30 IST
    ("Overlap", 13.0, 14.5),  # 18:30 - 20:00 IST
    ("Both", 7.0, 14.5),  # 12:30 - 20:00 IST
]

MIN_SL_PTS = 3.0
SL_BUFFER_PTS = 0.5
TP_PTS = 7.5
SWEEP_LOOKBACK_BARS = 3
MAX_TRADES_PER_DAY = 2
MAX_HOLD_MIN = 240

SPREAD_PTS = 0.20  # against you on entry and on exit
COMMISSION_USD = 0.50  # round turn at 0.08 lot

LOT = 0.08
USD_PER_PT_PER_LOT = 100.0  # XAUUSD: 1.00 lot = $100 per $1.00 move
START_EQUITY = 5000.0

# FundingPips 1 Step Flex $5K
MAX_LOSS_FLOOR = 4400.0  # 12% static
DAILY_LOSS_LIMIT = 150.0  # 3%
STRIKE_FLOATING_USD = 50.0  # 1% - permanent Striking System warning

TP_SWEEP = [4.0, 5.0, 6.0, 7.5, 9.0, 10.0, 12.0, 15.0, 20.0]

USD_PER_PT = LOT * USD_PER_PT_PER_LOT

# ===================== DATA =====================


def load_mt5(symbol, months, offset):
    try:
        import MetaTrader5 as mt5
    except ImportError:
        sys.exit(
            "MetaTrader5 not installed.  pip install MetaTrader5\n"
            "(Windows only - on Mac/Linux pass a CSV path instead.)"
        )

    if not mt5.initialize():
        sys.exit(
            f"MT5 initialize() failed: {mt5.last_error()}\n"
            "Is the terminal running and logged in?"
        )

    if mt5.symbol_info(symbol) is None:
        avail = [
            s.name for s in mt5.symbols_get() if "XAU" in s.name.upper() or "GOLD" in s.name.upper()
        ]
        mt5.shutdown()
        sys.exit(
            f"Symbol '{symbol}' not found.\n"
            f"Gold symbols on your broker: {avail or 'none found'}\n"
            f"Re-run with --symbol <name>"
        )
    mt5.symbol_select(symbol, True)

    frames, end = [], datetime.now()
    for _ in range(months + 1):
        start = end - timedelta(days=31)
        r = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, start, end)
        if r is not None and len(r):
            frames.append(pd.DataFrame(r))
        end = start
    mt5.shutdown()

    if not frames:
        sys.exit(
            f"No M1 history for {symbol}.  Open an M1 chart in MT5 and "
            f"scroll back to force the download, then retry."
        )

    df = pd.concat(frames, ignore_index=True).drop_duplicates("time")
    df["time"] = pd.to_datetime(df["time"], unit="s") - pd.Timedelta(hours=offset)
    return df.set_index("time")[["open", "high", "low", "close"]].sort_index()


def load_csv(path, offset=0):
    df = pd.read_csv(path)
    df.columns = [c.lower() for c in df.columns]
    tcol = next((c for c in df.columns if c in ("time", "date", "datetime", "timestamp")), None)
    if tcol is None:
        sys.exit(f"No time column in {path}.  Need: time,open,high,low,close")
    df = df.rename(columns={tcol: "time"})
    df["time"] = pd.to_datetime(df["time"])
    if offset:
        df["time"] = df["time"] - pd.Timedelta(hours=offset)
    missing = {"open", "high", "low", "close"} - set(df.columns)
    if missing:
        sys.exit(f"CSV missing columns: {sorted(missing)}")
    return df.set_index("time")[["open", "high", "low", "close"]].sort_index()


def check_timezone(m1, offset):
    rng = (m1["high"] - m1["low"]).groupby(m1.index.hour).mean()
    quiet = int(rng.idxmin())
    if 20 <= quiet <= 23 or quiet == 0:
        print(f"  timezone check ok (quietest hour {quiet:02d}:00 UTC)")
    else:
        print(f"  !! Quietest hour is {quiet:02d}:00 UTC, expected ~21:00-23:00.")
        print(f"     Server offset may be wrong. Try --offset " f"{(offset + quiet - 22) % 24}")


def resample_m5(m1):
    return (
        m1.resample("5min")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
        .dropna()
    )


def daily_levels(m1):
    hours = m1.index.hour + m1.index.minute / 60.0
    dates = m1.index.normalize()

    am = (hours >= ASIAN_START_UTC) & (hours < ASIAN_END_UTC)
    asian = m1[am].groupby(dates[am]).agg({"high": "max", "low": "min"})
    prev = m1.groupby(dates).agg({"high": "max", "low": "min"}).shift(1)

    out = {}
    for d in asian.index:
        if d not in prev.index or pd.isna(prev.loc[d, "high"]):
            continue
        out[d] = {
            "Asian High": (asian.loc[d, "high"], "res"),
            "Asian Low": (asian.loc[d, "low"], "sup"),
            "PD High": (prev.loc[d, "high"], "res"),
            "PD Low": (prev.loc[d, "low"], "sup"),
        }
    return out


# ===================== SIMULATION =====================


@dataclass
class Trade:
    date: str
    weekday: str
    month: str
    session: str
    line: str
    direction: str
    entry_time: pd.Timestamp
    entry: float
    sl: float
    sl_pts: float
    sl_hit: bool
    sl_time: object
    mfe_pts: float
    mae_pts: float
    timeout_price: float
    timeout_time: object
    tp_time: dict = field(default_factory=dict)
    tp_mae: dict = field(default_factory=dict)


def resolve(eidx, entry, sl, direction, m1, tps):
    """Walk M1 forward. Record when each candidate TP was first reached and
    the heat up to then, plus where the stop hit. One pass serves every TP."""
    mfe = mae = 0.0
    tp_time, tp_mae = {}, {}
    k = 0
    end = min(eidx + MAX_HOLD_MIN, len(m1))
    hi_a, lo_a, cl_a = m1["high"].values, m1["low"].values, m1["close"].values
    idx = m1.index

    for i in range(eidx, end):
        hi, lo = hi_a[i], lo_a[i]
        if direction == "long":
            fav, adv, stopped = hi - entry, entry - lo, lo <= sl
        else:
            fav, adv, stopped = entry - lo, hi - entry, hi >= sl

        mae = max(mae, adv)
        if stopped:
            # conservative: if both touched this minute, the stop went first
            return dict(
                mfe=mfe,
                mae=mae,
                sl_hit=True,
                sl_time=idx[i],
                timeout_price=np.nan,
                timeout_time=pd.NaT,
                tp_time=tp_time,
                tp_mae=tp_mae,
            )

        mfe = max(mfe, fav)
        while k < len(tps) and mfe >= tps[k]:
            tp_time[tps[k]] = idx[i]
            tp_mae[tps[k]] = mae
            k += 1

    j = max(end - 1, eidx)
    return dict(
        mfe=mfe,
        mae=mae,
        sl_hit=False,
        sl_time=pd.NaT,
        timeout_price=cl_a[j],
        timeout_time=idx[j],
        tp_time=tp_time,
        tp_mae=tp_mae,
    )


def find_trades(m1, m5, levels, session, w0, w1, tps):
    trades = []
    m5h = m5.index.hour + m5.index.minute / 60.0
    m5w = m5[(m5h >= w0) & (m5h < w1)]

    for date, day in m5w.groupby(m5w.index.normalize()):
        if date not in levels:
            continue
        lines = levels[date]
        taken, busy_until, pending = 0, None, {}
        bars = day.reset_index()

        for bi in range(len(bars)):
            if taken >= MAX_TRADES_PER_DAY:
                break
            row = bars.iloc[bi]
            t = row["time"]
            if busy_until is not None and t < busy_until:
                continue

            for name, (level, kind) in lines.items():
                if kind == "res":
                    poked, inside = row["high"] > level, row["close"] < level
                else:
                    poked, inside = row["low"] < level, row["close"] > level

                if poked:
                    ext = row["high"] if kind == "res" else row["low"]
                    if name in pending:
                        pbi, pext = pending[name]
                        pending[name] = (pbi, max(pext, ext) if kind == "res" else min(pext, ext))
                    else:
                        pending[name] = (bi, ext)

                if name not in pending:
                    continue
                pbi, extreme = pending[name]
                if bi - pbi > SWEEP_LOOKBACK_BARS:
                    del pending[name]
                    continue
                if not inside:
                    continue

                direction = "short" if kind == "res" else "long"
                entry = (
                    row["close"] - SPREAD_PTS if direction == "long" else row["close"] + SPREAD_PTS
                )

                if direction == "short":
                    sl = max(extreme + SL_BUFFER_PTS, entry + MIN_SL_PTS)
                    sl_pts = sl - entry
                else:
                    sl = min(extreme - SL_BUFFER_PTS, entry - MIN_SL_PTS)
                    sl_pts = entry - sl

                # fill at the M5 close = 5 minutes after the bar opened
                eidx = int(m1.index.searchsorted(t + pd.Timedelta(minutes=5)))
                if eidx >= len(m1):
                    del pending[name]
                    continue

                r = resolve(eidx, entry, sl, direction, m1, tps)
                trades.append(
                    Trade(
                        date=str(date.date()),
                        weekday=date.strftime("%a"),
                        month=date.strftime("%Y-%m"),
                        session=session,
                        line=name,
                        direction=direction,
                        entry_time=t + pd.Timedelta(minutes=5),
                        entry=round(entry, 2),
                        sl=round(sl, 2),
                        sl_pts=round(sl_pts, 2),
                        sl_hit=r["sl_hit"],
                        sl_time=r["sl_time"],
                        mfe_pts=round(r["mfe"], 2),
                        mae_pts=round(r["mae"], 2),
                        timeout_price=r["timeout_price"],
                        timeout_time=r["timeout_time"],
                        tp_time=r["tp_time"],
                        tp_mae=r["tp_mae"],
                    )
                )
                taken += 1
                done = r["sl_time"] if r["sl_hit"] else r["timeout_time"]
                busy_until = done if pd.notna(done) else t + pd.Timedelta(hours=4)
                del pending[name]
                break
    return trades


# ===================== EVALUATION =====================


def evaluate(trades, tp):
    """Score every trade at a given TP. No re-simulation needed."""
    rows = []
    for tr in trades:
        if tp in tr.tp_time:
            gross, outcome = tp, "win"
            xt = tr.tp_time[tp]
            xp = tr.entry + tp if tr.direction == "long" else tr.entry - tp
            heat = tr.tp_mae.get(tp, tr.mae_pts)
        elif tr.sl_hit:
            gross, outcome = -tr.sl_pts, "loss"
            xt, xp, heat = tr.sl_time, tr.sl, tr.mae_pts
        else:
            move = (
                (tr.timeout_price - tr.entry)
                if tr.direction == "long"
                else (tr.entry - tr.timeout_price)
            )
            gross, outcome = move, "timeout"
            xt, xp, heat = tr.timeout_time, tr.timeout_price, tr.mae_pts

        net = gross - SPREAD_PTS
        d = asdict(tr)
        d.pop("tp_time")
        d.pop("tp_mae")
        d.update(
            tp_pts=tp,
            outcome=outcome,
            exit_time=xt,
            exit_price=round(float(xp), 2),
            net_pts=round(net, 2),
            pnl=round(net * USD_PER_PT - COMMISSION_USD, 2),
            heat_pts=round(heat, 2),
            heat_usd=round(heat * USD_PER_PT, 2),
            hold_min=(int((xt - tr.entry_time).total_seconds() // 60) if pd.notna(xt) else np.nan),
        )
        rows.append(d)

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("entry_time").reset_index(drop=True)
        df["equity"] = (START_EQUITY + df["pnl"].cumsum()).round(2)
    return df


def save_sqlite(trades_df, runs_row, path):
    """Append this run to SQLite. Tables: runs (params + headline stats),
    trades (every trade, linked by run_id). Nothing SQLite-specific."""
    import sqlite3

    con = sqlite3.connect(path)
    try:
        pd.DataFrame([runs_row]).to_sql("runs", con, if_exists="append", index=False)
        t = trades_df.copy()
        t.insert(0, "run_id", runs_row["run_id"])
        for c in ("entry_time", "exit_time"):
            t[c] = t[c].astype(str)
        t.to_sql("trades", con, if_exists="append", index=False)
        con.execute("CREATE INDEX IF NOT EXISTS ix_trades_run ON trades(run_id)")
        con.execute("CREATE INDEX IF NOT EXISTS ix_trades_session " "ON trades(session, month)")
        con.commit()
        n_runs = con.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        n_trades = con.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    finally:
        con.close()
    return n_runs, n_trades


def summarise(df, months):
    n = len(df)
    if n == 0:
        return {}
    eq = df["equity"]
    streak = worst = 0
    for p in df["pnl"]:
        streak = streak + 1 if p <= 0 else 0
        worst = max(worst, streak)
    daily = df.groupby("date")["pnl"].sum()
    return dict(
        trades=n,
        win_rate=round(100 * (df["pnl"] > 0).mean(), 1),
        expectancy=round(df["pnl"].mean(), 2),
        total=round(df["pnl"].sum(), 2),
        per_month=round(df["pnl"].sum() / months, 2),
        max_dd=round((eq.cummax() - eq).max(), 2),
        final=round(eq.iloc[-1], 2),
        breached=bool((eq <= MAX_LOSS_FLOOR).any()),
        worst_streak=worst,
        avg_heat=round(df["heat_pts"].mean(), 2),
        avg_hold=round(df["hold_min"].mean(), 1),
        strikes=int((df["heat_usd"] >= STRIKE_FLOATING_USD).sum()),
        cap_days=int((daily <= -DAILY_LOSS_LIMIT).sum()),
        trading_days=int(daily.size),
    )


def report(trades, session, months):
    if not trades:
        print(f"\n{session}: no trades.")
        return None

    base = evaluate(trades, TP_PTS)
    s = summarise(base, months)

    print(f"\n{'=' * 72}")
    print(f"  {session}   (TP {TP_PTS} pts, SL min {MIN_SL_PTS} pts, {LOT} lot)")
    print("=" * 72)
    print(
        f"  {s['trades']} trades over {s['trading_days']} days   |   "
        f"win {s['win_rate']}%   |   expectancy ${s['expectancy']}"
    )
    print(
        f"  Total ${s['total']}  ->  ${s['per_month']}/month   |   "
        f"final equity ${s['final']}"
        f"{'   ** BREACHED **' if s['breached'] else ''}"
    )
    print(
        f"  Max DD ${s['max_dd']}   |   worst losing streak {s['worst_streak']}"
        f"   |   avg hold {s['avg_hold']} min   |   avg heat {s['avg_heat']} pts"
    )

    print("\n  Prop rule check")
    warn = "   <-- 4 of these closes the account" if s["strikes"] >= 4 else ""
    print(
        f"    Trades with heat >= ${STRIKE_FLOATING_USD:.0f} "
        f"(Striking System): {s['strikes']}{warn}"
    )
    print(f"    Days past the ${DAILY_LOSS_LIMIT:.0f} daily cap: {s['cap_days']}")
    print(
        f"    ${MAX_LOSS_FLOOR:.0f} equity floor: " f"{'HIT' if s['breached'] else 'never touched'}"
    )

    print("\n  Month by month")
    print(f"    {'Month':<9}{'N':>5}{'Win%':>8}{'P&L $':>11}" f"{'Equity $':>12}{'MaxDD $':>10}")
    print("    " + "-" * 55)
    for m, g in base.groupby("month"):
        e = g["equity"]
        print(
            f"    {m:<9}{len(g):>5}{100 * (g['pnl'] > 0).mean():>8.1f}"
            f"{g['pnl'].sum():>11.2f}{e.iloc[-1]:>12.2f}"
            f"{(e.cummax() - e).max():>10.2f}"
        )

    print("\n  TP sweep")
    print(
        f"    {'TP':>5}{'Win%':>8}{'Exp $':>9}{'/month $':>11}"
        f"{'MaxDD $':>10}{'Streak':>8}{'Strikes':>9}"
    )
    print("    " + "-" * 60)
    best = (None, -1e9)
    for tp in TP_SWEEP:
        ss = summarise(evaluate(trades, tp), months)
        if ss["expectancy"] > best[1]:
            best = (tp, ss["expectancy"])
        print(
            f"    {tp:>5.1f}{ss['win_rate']:>8.1f}{ss['expectancy']:>9.2f}"
            f"{ss['per_month']:>11.2f}{ss['max_dd']:>10.2f}"
            f"{ss['worst_streak']:>8}{ss['strikes']:>9}"
        )
    print(f"\n    Best expectancy: TP {best[0]} pts (${best[1]}/trade)")
    print(
        f"    Only move the TP there if max DD stays under "
        f"${START_EQUITY - MAX_LOSS_FLOOR:.0f} and you can sit the streak."
    )

    print("\n  By level                          By weekday")
    lv = [
        (k, len(g), 100 * (g["pnl"] > 0).mean(), g["pnl"].mean()) for k, g in base.groupby("line")
    ]
    wd = [
        (k, len(g), 100 * (g["pnl"] > 0).mean(), g["pnl"].mean())
        for k, g in base.groupby("weekday")
    ]
    order = {d: i for i, d in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri"])}
    wd.sort(key=lambda r: order.get(r[0], 9))
    for i in range(max(len(lv), len(wd))):
        a = (
            f"    {lv[i][0]:<11}n={lv[i][1]:<4}{lv[i][2]:>5.1f}% ${lv[i][3]:>6.2f}"
            if i < len(lv)
            else ""
        )
        b = (
            f"   {wd[i][0]:<4}n={wd[i][1]:<4}{wd[i][2]:>5.1f}% ${wd[i][3]:>6.2f}"
            if i < len(wd)
            else ""
        )
        print(f"{a:<38}{b}")

    return base


# ===================== MAIN =====================


def main():
    global SYMBOL, MONTHS_BACK, TP_PTS, MIN_SL_PTS, LOT, USD_PER_PT

    p = argparse.ArgumentParser()
    p.add_argument("csv", nargs="?", help="CSV of M1 bars (else pull from MT5)")
    p.add_argument("--symbol", default=SYMBOL)
    p.add_argument("--months", type=float, default=MONTHS_BACK)
    p.add_argument(
        "--offset", type=int, default=SERVER_UTC_OFFSET, help="broker server-time offset from UTC"
    )
    p.add_argument("--tp", type=float, default=TP_PTS)
    p.add_argument("--sl", type=float, default=MIN_SL_PTS)
    p.add_argument("--lot", type=float, default=LOT)
    p.add_argument("--out", default="sweep_trades.csv")
    p.add_argument("--db", default="sweep.db", help="SQLite file to append this run to; '' to skip")
    a = p.parse_args()

    SYMBOL, MONTHS_BACK = a.symbol, a.months
    TP_PTS, MIN_SL_PTS, LOT = a.tp, a.sl, a.lot
    USD_PER_PT = LOT * USD_PER_PT_PER_LOT

    print(f"XAUUSD sweep-reversal backtest - {SYMBOL}, {MONTHS_BACK} months")
    m1 = load_csv(a.csv, 0) if a.csv else load_mt5(SYMBOL, int(MONTHS_BACK), a.offset)
    m1 = m1[m1.index >= m1.index.max() - pd.Timedelta(days=MONTHS_BACK * 30.44)]
    if len(m1) < 5000:
        sys.exit(
            f"Only {len(m1)} M1 bars - not enough. Scroll back an M1 "
            f"chart in MT5 to force the download, then retry."
        )

    span = max((m1.index.max() - m1.index.min()).days / 30.44, 0.1)
    print(
        f"  {len(m1):,} M1 bars   {m1.index.min():%Y-%m-%d} -> "
        f"{m1.index.max():%Y-%m-%d} UTC   ({span:.1f} months)"
    )
    check_timezone(m1, a.offset)

    m5 = resample_m5(m1)
    levels = daily_levels(m1)
    print(f"  {len(m5):,} M5 bars, {len(levels)} tradeable days")

    tps = sorted(set(TP_SWEEP + [TP_PTS]))
    frames = []
    for name, w0, w1 in WINDOWS:
        df = report(find_trades(m1, m5, levels, name, w0, w1, tps), name, span)
        if df is not None:
            frames.append(df)

    if not frames:
        print("\nNo trades in any window. Check --offset, or loosen " "SWEEP_LOOKBACK_BARS.")
        return

    print(f"\n{'=' * 72}\n  SESSION COMPARISON (TP {TP_PTS})\n{'=' * 72}")
    print(
        f"  {'Session':<10}{'N':>6}{'Win%':>8}{'Exp $':>9}"
        f"{'/month $':>11}{'MaxDD $':>10}{'Strikes':>9}"
    )
    print("  " + "-" * 63)
    for df in frames:
        s = summarise(df, span)
        print(
            f"  {df['session'].iat[0]:<10}{s['trades']:>6}{s['win_rate']:>8.1f}"
            f"{s['expectancy']:>9.2f}{s['per_month']:>11.2f}"
            f"{s['max_dd']:>10.2f}{s['strikes']:>9}"
        )

    out = pd.concat(frames, ignore_index=True)
    cols = [
        "session",
        "date",
        "weekday",
        "month",
        "line",
        "direction",
        "entry_time",
        "entry",
        "sl",
        "sl_pts",
        "exit_time",
        "exit_price",
        "outcome",
        "hold_min",
        "net_pts",
        "pnl",
        "equity",
        "mfe_pts",
        "heat_pts",
        "heat_usd",
    ]
    out[cols].to_csv(a.out, index=False)
    print(f"\n  {len(out)} rows -> {a.out}")

    if a.db:
        overall = summarise(
            pd.concat(
                [f for f in frames if f["session"].iat[0] == "Both"] or frames[:1],
                ignore_index=True,
            ),
            span,
        )
        run = dict(
            run_id=datetime.now().strftime("%Y%m%d-%H%M%S"),
            run_at=datetime.now().isoformat(timespec="seconds"),
            symbol=SYMBOL,
            months=round(span, 2),
            data_from=str(m1.index.min()),
            data_to=str(m1.index.max()),
            bars=len(m1),
            days=len(levels),
            tp_pts=TP_PTS,
            min_sl_pts=MIN_SL_PTS,
            sl_buffer_pts=SL_BUFFER_PTS,
            lookback_bars=SWEEP_LOOKBACK_BARS,
            max_trades_day=MAX_TRADES_PER_DAY,
            max_hold_min=MAX_HOLD_MIN,
            lot=LOT,
            spread_pts=SPREAD_PTS,
            commission=COMMISSION_USD,
            start_equity=START_EQUITY,
            server_offset=a.offset,
            trades=overall.get("trades"),
            win_rate=overall.get("win_rate"),
            expectancy=overall.get("expectancy"),
            per_month=overall.get("per_month"),
            max_dd=overall.get("max_dd"),
            worst_streak=overall.get("worst_streak"),
            strikes=overall.get("strikes"),
            breached=overall.get("breached"),
        )
        nr, nt = save_sqlite(out[cols], run, a.db)
        print(f"  appended to {a.db}  (run {run['run_id']}; " f"{nr} runs, {nt} trades stored)")

    print("  mfe_pts is what tells you later whether a bigger TP is justified.")


if __name__ == "__main__":
    main()
