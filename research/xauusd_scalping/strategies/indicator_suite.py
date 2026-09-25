"""
Classic indicator strategies (step (c), 2026-09-25) -- baselines to set
beside the price-action shortlist S01-S11, and building blocks for the
custom strategy.

Speed: indicators are computed ONCE for the whole series with pandas
(`compute_features`), then looked up per bar by timestamp -- O(1) per bar
instead of re-deriving an EMA(200) from a slice on every call. That is only
honest if every feature at bar i uses bars <= i. `compute_features` is built
from causal operations only (ewm, trailing rolling windows, shift(+k)), and
tests/test_indicator_suite.py proves it: features computed on a truncated
series equal the full-series features on every shared row.

Exits are fixed ATR multiples at entry (the engine resolves stop/target
intrabar); every rule is stated before it is run and none is tuned here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from engine.backtest_engine import Bar, Side, Signal
from engine.cost_model import trading_date


def _wilder(x: pd.Series, n: int) -> pd.Series:
    return x.ewm(alpha=1 / n, adjust=False).mean()


def _rsi(close: pd.Series, n: int) -> pd.Series:
    d = close.diff()
    up, dn = _wilder(d.clip(lower=0), n), _wilder((-d).clip(lower=0), n)
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def compute_features(bars: list[Bar]) -> pd.DataFrame:
    df = pd.DataFrame(
        {"open": [b.open for b in bars], "high": [b.high for b in bars],
         "low": [b.low for b in bars], "close": [b.close for b in bars],
         "volume": [max(b.volume, 1e-9) for b in bars]},
        index=pd.DatetimeIndex([b.ts for b in bars], name="ts"),
    )
    c, h, lo = df["close"], df["high"], df["low"]
    f = pd.DataFrame(index=df.index)
    f["close"], f["high"], f["low"] = c, h, lo
    for n in (20, 50, 200):
        f[f"ema{n}"] = c.ewm(span=n, adjust=False).mean()
    tr = pd.concat([h - lo, (h - c.shift()).abs(), (lo - c.shift()).abs()], axis=1).max(axis=1)
    f["atr"] = _wilder(tr, 14)
    f["rsi2"], f["rsi14"] = _rsi(c, 2), _rsi(c, 14)
    mid, sd = c.rolling(20).mean(), c.rolling(20).std(ddof=0)
    f["bb_mid"], f["bb_up"], f["bb_lo"] = mid, mid + 2 * sd, mid - 2 * sd
    up_move, dn_move = h.diff(), -lo.diff()
    plus_dm = up_move.where((up_move > dn_move) & (up_move > 0), 0.0)
    minus_dm = dn_move.where((dn_move > up_move) & (dn_move > 0), 0.0)
    atr_w = _wilder(tr, 14)
    pdi, mdi = 100 * _wilder(plus_dm, 14) / atr_w, 100 * _wilder(minus_dm, 14) / atr_w
    f["adx"] = _wilder(100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan), 14)
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    f["macd"], f["macd_sig"] = macd, macd.ewm(span=9, adjust=False).mean()
    # Donchian of the PREVIOUS 20 bars (shift 1: a breakout is judged
    # against a channel that excludes the bar doing the breaking).
    f["dc_hi"], f["dc_lo"] = h.rolling(20).max().shift(1), lo.rolling(20).min().shift(1)
    f["supertrend_up"] = _supertrend(h, lo, c, f["atr"])
    # Session VWAP +- sigma, reset each trading day (17:00 New York).
    tday = pd.Series([trading_date(t) for t in df.index], index=df.index)
    tp = (h + lo + c) / 3
    pv, v = (tp * df["volume"]).groupby(tday).cumsum(), df["volume"].groupby(tday).cumsum()
    vwap = pv / v
    var = ((tp - vwap) ** 2 * df["volume"]).groupby(tday).cumsum() / v
    f["vwap"], f["vwap_sd"] = vwap, np.sqrt(var)
    # London opening range: 07:00-08:00 UTC high/low of the current trading
    # day, only known (non-NaN) from 08:00 UTC on.
    in_or = (df.index.hour == 7)
    or_hi = h.where(in_or).groupby(tday).cummax()
    or_lo = lo.where(in_or).groupby(tday).cummin()
    after = df.index.hour >= 8
    f["or_hi"] = or_hi.groupby(tday).ffill().where(after)
    f["or_lo"] = or_lo.groupby(tday).ffill().where(after)
    f["tday"] = tday
    f["hour"] = df.index.hour
    return f


def _supertrend(h: pd.Series, lo: pd.Series, c: pd.Series, atr: pd.Series, mult: float = 3.0) -> pd.Series:
    """Standard Supertrend(ATR14, 3) direction (True = up). Iterative but
    single-pass and causal: each bar uses only its own and prior values."""
    hl2 = ((h + lo) / 2).to_numpy()
    a, cl = atr.to_numpy(), c.to_numpy()
    n = len(cl)
    up_trend = np.ones(n, dtype=bool)
    fub, flb = np.full(n, np.nan), np.full(n, np.nan)
    for i in range(n):
        bu, bl = hl2[i] + mult * a[i], hl2[i] - mult * a[i]
        if i == 0 or np.isnan(fub[i - 1]):
            fub[i], flb[i] = bu, bl
            continue
        fub[i] = bu if (bu < fub[i - 1] or cl[i - 1] > fub[i - 1]) else fub[i - 1]
        flb[i] = bl if (bl > flb[i - 1] or cl[i - 1] < flb[i - 1]) else flb[i - 1]
        if up_trend[i - 1]:
            up_trend[i] = cl[i] >= flb[i]
        else:
            up_trend[i] = cl[i] > fub[i]
    return pd.Series(up_trend, index=c.index)


# rule(row, prev) -> Side | None. `row`/`prev` are this bar's and the
# previous bar's feature records (dicts).
Rule = Callable[[dict, dict], "Side | None"]


def _cross_up(r, p, a, b):
    return p[a] <= p[b] and r[a] > r[b]


def _cross_dn(r, p, a, b):
    return p[a] >= p[b] and r[a] < r[b]


def i01_ema_cross(r, p):
    if _cross_up(r, p, "ema20", "ema50") and r["close"] > r["ema200"]:
        return Side.LONG
    if _cross_dn(r, p, "ema20", "ema50") and r["close"] < r["ema200"]:
        return Side.SHORT
    return None


def i02_donchian_breakout(r, p):
    if r["close"] > r["dc_hi"]:
        return Side.LONG
    if r["close"] < r["dc_lo"]:
        return Side.SHORT
    return None


def i03_rsi2_pullback(r, p):  # Connors-style: buy dips in an uptrend
    if r["close"] > r["ema200"] and r["rsi2"] < 10:
        return Side.LONG
    if r["close"] < r["ema200"] and r["rsi2"] > 90:
        return Side.SHORT
    return None


def i04_bollinger_reversion(r, p):  # only in a non-trending market
    if r["adx"] < 20 and r["close"] < r["bb_lo"]:
        return Side.LONG
    if r["adx"] < 20 and r["close"] > r["bb_up"]:
        return Side.SHORT
    return None


def i05_macd_cross(r, p):
    if _cross_up(r, p, "macd", "macd_sig") and r["close"] > r["ema200"]:
        return Side.LONG
    if _cross_dn(r, p, "macd", "macd_sig") and r["close"] < r["ema200"]:
        return Side.SHORT
    return None


def i06_supertrend_flip(r, p):
    if r["supertrend_up"] and not p["supertrend_up"]:
        return Side.LONG
    if not r["supertrend_up"] and p["supertrend_up"]:
        return Side.SHORT
    return None


def i07_london_orb(r, p):  # first close outside the 07-08 UTC range, London hours only
    if not (8 <= r["hour"] < 12) or r["or_hi"] != r["or_hi"]:
        return None
    if r["close"] > r["or_hi"] and p["close"] <= p["or_hi"]:
        return Side.LONG
    if r["close"] < r["or_lo"] and p["close"] >= p["or_lo"]:
        return Side.SHORT
    return None


def i08_vwap_reversion(r, p):
    if r["vwap_sd"] != r["vwap_sd"] or r["vwap_sd"] <= 0:
        return None
    if r["close"] < r["vwap"] - 2 * r["vwap_sd"]:
        return Side.LONG
    if r["close"] > r["vwap"] + 2 * r["vwap_sd"]:
        return Side.SHORT
    return None


@dataclass(frozen=True)
class RuleSpec:
    key: str
    name: str
    rule: Rule
    stop_atr: float
    target_atr: float


INDICATOR_RULES = [
    RuleSpec("I01", "EMA20/50 cross + EMA200 filter", i01_ema_cross, 2.0, 3.0),
    RuleSpec("I02", "Donchian-20 breakout", i02_donchian_breakout, 2.0, 4.0),
    RuleSpec("I03", "RSI(2) pullback in EMA200 trend", i03_rsi2_pullback, 2.0, 1.5),
    RuleSpec("I04", "Bollinger reversion when ADX<20", i04_bollinger_reversion, 1.5, 1.5),
    RuleSpec("I05", "MACD cross + EMA200 filter", i05_macd_cross, 2.0, 3.0),
    RuleSpec("I06", "Supertrend(14,3) flip", i06_supertrend_flip, 3.0, 4.5),
    RuleSpec("I07", "London opening-range breakout", i07_london_orb, 1.5, 3.0),
    RuleSpec("I08", "Session VWAP 2-sigma reversion", i08_vwap_reversion, 1.5, 1.5),
]


class IndicatorRuleStrategy:
    """Engine-compatible strategy: looks up this bar's precomputed features
    and applies one rule. `feats` must come from compute_features() on the
    SAME bars the engine runs over."""

    def __init__(self, spec: RuleSpec, feats: pd.DataFrame, allow: Callable[[dict], bool] | None = None):
        self.spec = spec
        self.name = f"{spec.key} {spec.name}"
        self.allow = allow  # optional regime/session filter, for the custom build
        cols = [c for c in feats.columns if c != "tday"]
        recs = feats[cols].to_dict("records")
        self._rows = dict(zip(feats.index, recs, strict=True))
        # "Previous bar" from the SERIES, not the previous on_bar call: the
        # engine skips on_bar while a position is open or the day is halted,
        # so the last-seen row can be many bars stale and fake a crossover.
        self._prev = dict(zip(feats.index[1:], recs[:-1], strict=True))

    def on_bar(self, bar: Bar, ctx) -> Signal | None:
        row, prev = self._rows.get(bar.ts), self._prev.get(bar.ts)
        if row is None or prev is None or ctx.has_open_position:
            return None
        atr = row["atr"]
        if not atr or atr != atr:
            return None
        try:
            side = self.spec.rule(row, prev)
        except (TypeError, ValueError):
            return None
        if side is None or (self.allow is not None and not self.allow(row)):
            return None
        e = bar.close
        s, t = self.spec.stop_atr * atr, self.spec.target_atr * atr
        if side == Side.LONG:
            return Signal(side=side, stop_price=e - s, target_price=e + t, reason=self.name)
        return Signal(side=side, stop_price=e + s, target_price=e - t, reason=self.name)
