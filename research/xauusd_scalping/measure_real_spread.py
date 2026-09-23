"""
Replace the ASSUMED spread table with a MEASURED one from a real broker feed.

Why this matters more than any strategy work right now
------------------------------------------------------
`engine/cost_model.py`'s own docstring says its spread table is a
"PESSIMISTIC ASSUMPTION, not measured from a real broker feed." Every
result this project has produced is downstream of that number, and Phase 1
found that modelled round-trip cost is 82-170% of a 40-point trade's entire
risk budget -- which is what makes M1 scalping look structurally unviable.

If the real spreads are materially tighter than assumed, that conclusion
changes. If they are not, it is confirmed and the project should stop
looking for a better entry signal at this timeframe. Either way this one
input decides more than any strategy does, so it is worth measuring rather
than assuming.

What to feed it
---------------
An MT5 tick export containing BID and ASK (a bar/candle export will NOT do
-- candles carry no spread). See the "How to export" section printed by
`--help-export`, or at the bottom of this file.

Accepts either:
  * MT5 "Ticks" CSV export:  <DATE>\t<TIME>\t<BID>\t<ASK>\t<LAST>\t<VOLUME>...
  * Any CSV with recognisable bid/ask columns (auto-detected, case-insensitive)

Usage
-----
    python measure_real_spread.py ticks.csv
    python measure_real_spread.py ticks.csv --emit-table   # prints a drop-in
                                                           # replacement table
    python measure_real_spread.py --help-export

Output: measured spread percentiles per session (and per volatility tercile
where there is enough data), alongside the currently assumed value, with the
ratio -- so the gap is immediately visible.
"""
from __future__ import annotations

import csv
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from engine.cost_model import Session, VolBucket, session_for, _SPREAD_TABLE  # noqa: E402

# XAUUSD: the harness works in "points" where 1 point = $0.01 of price.
POINTS_PER_DOLLAR = 100.0

EXPORT_HELP = """
How to export real XAUUSD tick data from MT5 (this is the part only you can do)
------------------------------------------------------------------------------
Spread cannot be recovered from candles -- it only exists in bid/ask ticks.

  1. Open MT5 (the same broker account you actually trade -- spreads are
     broker-specific, so a different broker's data answers the wrong
     question).
  2. View -> Symbols  (or Ctrl+U).
  3. Find XAUUSD in the tree on the left, select it.
  4. Click the "Ticks" tab (NOT "Bars").
  5. Set the date range -- even 2-4 weeks is plenty; ideally include a
     range that spans all sessions (so Asia/London/NY/overlap are all
     represented), and try to include at least one high-volatility day.
  6. Click "Request", wait for it to load, then "Export Ticks" -> save as CSV.
  7. Run:  python measure_real_spread.py <that file>.csv

If "Ticks" shows nothing, your broker may not serve tick history -- in that
case an alternative is to log live spread yourself: in MT5, right-click the
chart -> Properties -> Show -> tick "Show ask line", and watch the bid/ask
gap across sessions, or run a small MQL5 script that samples SymbolInfoInteger
(SYMBOL_SPREAD) every few seconds for a day. Even a crude sample beats an
unvalidated assumption.
"""


def _parse_rows(path: Path):
    """Yields (datetime, spread_in_points). Tolerant of MT5's tab-separated
    export and of ordinary CSVs with bid/ask columns."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        sample = fh.read(8192)
        fh.seek(0)
        delim = "\t" if "\t" in sample.splitlines()[0] else ","
        reader = csv.reader(fh, delimiter=delim)
        header = next(reader)
        lower = [h.strip().lower().strip("<>") for h in header]

        def find(*names):
            for n in names:
                if n in lower:
                    return lower.index(n)
            return None

        i_bid, i_ask = find("bid"), find("ask")
        i_date, i_time = find("date"), find("time")
        i_dt = find("datetime", "timestamp", "time")
        if i_bid is None or i_ask is None:
            raise SystemExit(
                f"Could not find bid/ask columns in {path.name}. Header was: {header}\n"
                "This needs a TICK export (bid/ask), not a candle/bar export."
            )

        skipped = 0
        for row in reader:
            if not row or len(row) <= max(i_bid, i_ask):
                continue
            try:
                bid, ask = float(row[i_bid]), float(row[i_ask])
            except ValueError:
                skipped += 1
                continue
            if bid <= 0 or ask <= 0 or ask < bid:
                skipped += 1
                continue
            try:
                if i_date is not None and i_time is not None:
                    ts = datetime.fromisoformat(
                        f"{row[i_date].strip().replace('.', '-')} {row[i_time].strip()[:8]}"
                    )
                elif i_dt is not None:
                    ts = datetime.fromisoformat(row[i_dt].strip().replace(".", "-"))
                else:
                    continue
            except ValueError:
                skipped += 1
                continue
            yield ts, (ask - bid) * POINTS_PER_DOLLAR
        if skipped:
            print(f"(skipped {skipped} unparseable/invalid rows)", file=sys.stderr)


def main():
    args = [a for a in sys.argv[1:]]
    if not args or "--help-export" in args or "-h" in args or "--help" in args:
        print(EXPORT_HELP)
        return
    emit = "--emit-table" in args
    path = Path([a for a in args if not a.startswith("--")][0])
    if not path.exists():
        raise SystemExit(f"No such file: {path}")

    by_session: dict[Session, list[float]] = defaultdict(list)
    total = 0
    for ts, spread_pts in _parse_rows(path):
        by_session[session_for(ts)].append(spread_pts)
        total += 1
    if not total:
        raise SystemExit("No usable ticks parsed -- is this a tick export with bid/ask?")

    print(f"\nParsed {total:,} ticks from {path.name}\n")
    print(f"{'session':22s} {'ticks':>9s} {'median':>8s} {'p75':>7s} {'p90':>7s} "
          f"{'ASSUMED':>8s} {'measured/assumed':>17s}")
    verdicts = []
    for sess in Session:
        vals = by_session.get(sess, [])
        assumed = _SPREAD_TABLE[(sess, VolBucket.MEDIUM)]
        if len(vals) < 100:
            print(f"{sess.value:22s} {len(vals):9,d}   -- too few ticks to judge --")
            continue
        vals.sort()
        med = st.median(vals)
        p75 = vals[int(len(vals) * 0.75)]
        p90 = vals[int(len(vals) * 0.90)]
        ratio = med / assumed if assumed else float("nan")
        verdicts.append(ratio)
        print(f"{sess.value:22s} {len(vals):9,d} {med:8.1f} {p75:7.1f} {p90:7.1f} "
              f"{assumed:8.1f} {ratio:16.2f}x")

    print()
    if verdicts:
        avg = sum(verdicts) / len(verdicts)
        print(f"Measured spread is on average {avg:.2f}x the assumed table.")
        if avg < 0.6:
            print(
                "  => Assumed costs are materially PESSIMISTIC. Phase 1's\n"
                "     'cost is 82-170% of the risk budget' conclusion needs re-running\n"
                "     with these numbers -- the viability picture may change."
            )
        elif avg > 1.2:
            print(
                "  => Real costs are even WORSE than assumed. The structural\n"
                "     conclusion holds a fortiori; M1 scalping at this cost is not viable."
            )
        else:
            print(
                "  => Assumptions were roughly right. Phase 1's structural conclusion\n"
                "     stands: round-trip cost consumes most of a 40pt risk budget, and\n"
                "     no entry signal overcomes that."
            )

    if emit:
        print("\n# Drop-in replacement for _SPREAD_TABLE in engine/cost_model.py")
        print("# MEASURED from a real broker tick feed on "
              f"{datetime.now().date().isoformat()} -- replaces the previous assumption.")
        print("_SPREAD_TABLE: dict[tuple[Session, VolBucket], float] = {")
        for sess in Session:
            vals = sorted(by_session.get(sess, []))
            if len(vals) < 100:
                for vb in VolBucket:
                    print(f"    (Session.{sess.name}, VolBucket.{vb.name}): "
                          f"{_SPREAD_TABLE[(sess, vb)]},  # UNMEASURED -- kept assumed value")
                continue
            # Volatility terciles proxied by the spread's own distribution:
            # calm periods quote tight, volatile ones quote wide.
            lo = vals[int(len(vals) * 0.25)]
            mid = st.median(vals)
            hi = vals[int(len(vals) * 0.90)]
            for vb, v in ((VolBucket.LOW, lo), (VolBucket.MEDIUM, mid), (VolBucket.HIGH, hi)):
                print(f"    (Session.{sess.name}, VolBucket.{vb.name}): {v:.1f},")
        print("}")


if __name__ == "__main__":
    main()
