"""
D1 swing rules (option 1, 2026-09-25). Classic, few-parameter systems,
stated before they were run and not tuned:

  D01 Turtle 20/10   close beyond the prior 20-day high/low; exit on the
                     opposite prior 10-day extreme; 2 ATR(20) stop
  D02 Turtle 55/20   same with 55/20
  D03 MA trend       close crosses SMA50 while SMA50 is on the same side of
                     SMA200; exit on a close back across SMA50; 3 ATR stop
  D04 RSI(2) daily   RSI(2) < 10 above SMA200 (long) / > 90 below it (short);
                     exit on a close back across SMA5; 3 ATR stop
  D05 Weekly mom.    on Monday's close, trade last week's direction
                     (Friday close vs the Friday before); exit Friday's
                     close; 2 ATR stop

Runs on RESEARCH_TIMEFRAME=D1 bars (run_backtests.daily_trading_bars). Uses
the engine's exit_signal hook for the trailing/rule exits; the resting
target is parked far away so it never binds. Features are causal: rolling
windows end at the current bar, and channels use shift(1) so a breakout
is judged against the days BEFORE it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from engine.backtest_engine import Bar, Side, Signal
from engine.cost_model import trading_date


def compute_daily_features(bars: list[Bar]) -> pd.DataFrame:
    idx = pd.DatetimeIndex([b.ts for b in bars], name="ts")
    c = pd.Series([b.close for b in bars], index=idx)
    h = pd.Series([b.high for b in bars], index=idx)
    lo = pd.Series([b.low for b in bars], index=idx)
    f = pd.DataFrame({"close": c, "high": h, "low": lo})
    tr = pd.concat([h - lo, (h - c.shift()).abs(), (lo - c.shift()).abs()], axis=1).max(axis=1)
    f["atr"] = tr.ewm(alpha=1 / 20, adjust=False).mean()
    for n in (5, 50, 200):
        f[f"sma{n}"] = c.rolling(n).mean()
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 2, adjust=False).mean()
    dn = (-d).clip(lower=0).ewm(alpha=1 / 2, adjust=False).mean()
    f["rsi2"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    for n in (10, 20, 55):
        f[f"hi{n}"] = h.rolling(n).max().shift(1)
        f[f"lo{n}"] = lo.rolling(n).min().shift(1)
    tdays = [trading_date(t) for t in idx]
    f["weekday"] = [d.weekday() for d in tdays]
    # Last completed week's direction, known from Monday on: Friday close vs
    # the Friday before. ISO week of the trading day groups Mon-Fri.
    week = pd.Series([d.isocalendar()[:2] for d in tdays], index=idx)
    week_close = c.groupby(week.values).last()
    wk_ret = week_close.diff()
    prev_week_ret = {k: wk_ret.shift(1).get(k) for k in week_close.index}
    f["prev_week_ret"] = [prev_week_ret[w] for w in week]
    return f


EntryFn = Callable[[dict, dict], "Side | None"]
ExitFn = Callable[[dict, Side], bool]


def _cross(r, p, col, up):
    return (p["close"] <= p[col] and r["close"] > r[col]) if up else (p["close"] >= p[col] and r["close"] < r[col])


@dataclass(frozen=True)
class SwingSpec:
    key: str
    name: str
    entry: EntryFn
    exit: ExitFn
    stop_atr: float


SWING_RULES = [
    SwingSpec("D01", "Turtle 20/10 breakout",
              lambda r, p: Side.LONG if r["close"] > r["hi20"] else Side.SHORT if r["close"] < r["lo20"] else None,
              lambda r, s: r["close"] < r["lo10"] if s == Side.LONG else r["close"] > r["hi10"], 2.0),
    SwingSpec("D02", "Turtle 55/20 breakout",
              lambda r, p: Side.LONG if r["close"] > r["hi55"] else Side.SHORT if r["close"] < r["lo55"] else None,
              lambda r, s: r["close"] < r["lo20"] if s == Side.LONG else r["close"] > r["hi20"], 2.0),
    SwingSpec("D03", "SMA50 cross with SMA200 trend",
              lambda r, p: Side.LONG if (_cross(r, p, "sma50", True) and r["sma50"] > r["sma200"])
              else Side.SHORT if (_cross(r, p, "sma50", False) and r["sma50"] < r["sma200"]) else None,
              lambda r, s: r["close"] < r["sma50"] if s == Side.LONG else r["close"] > r["sma50"], 3.0),
    SwingSpec("D04", "RSI(2) daily pullback in SMA200 trend",
              lambda r, p: Side.LONG if (r["close"] > r["sma200"] and r["rsi2"] < 10)
              else Side.SHORT if (r["close"] < r["sma200"] and r["rsi2"] > 90) else None,
              lambda r, s: r["close"] > r["sma5"] if s == Side.LONG else r["close"] < r["sma5"], 3.0),
    SwingSpec("D05", "Weekly momentum Mon->Fri",
              lambda r, p: None if r["weekday"] != 0 or r["prev_week_ret"] != r["prev_week_ret"]
              else Side.LONG if r["prev_week_ret"] > 0 else Side.SHORT,
              lambda r, s: r["weekday"] == 4, 2.0),
]


class SwingRuleStrategy:
    def __init__(self, spec: SwingSpec, feats: pd.DataFrame):
        self.spec = spec
        self.name = f"{spec.key} {spec.name}"
        recs = feats.to_dict("records")
        self._rows = dict(zip(feats.index, recs, strict=True))
        self._prev = dict(zip(feats.index[1:], recs[:-1], strict=True))

    def on_bar(self, bar: Bar, ctx) -> Signal | None:
        r, p = self._rows.get(bar.ts), self._prev.get(bar.ts)
        if r is None or p is None or not r["atr"] or r["atr"] != r["atr"]:
            return None
        try:
            side = self.spec.entry(r, p)
        except (TypeError, ValueError):
            return None
        if side is None:
            return None
        e, s = bar.close, self.spec.stop_atr * r["atr"]
        far = 100 * r["atr"]  # rule exits only; the resting target never binds
        if side == Side.LONG:
            return Signal(side=side, stop_price=e - s, target_price=e + far, reason=self.name)
        return Signal(side=side, stop_price=e + s, target_price=e - far, reason=self.name)

    def exit_signal(self, bar: Bar, ctx, position) -> bool:
        r = self._rows.get(bar.ts)
        if r is None:
            return False
        try:
            return bool(self.spec.exit(r, position.side))
        except (TypeError, ValueError):
            return False
