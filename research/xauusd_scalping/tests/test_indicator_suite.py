"""Indicator suite: every precomputed feature must be causal (2026-09-25)."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

from research.xauusd_scalping.engine.backtest_engine import Bar, StrategyContext
from research.xauusd_scalping.strategies.indicator_suite import (
    INDICATOR_RULES, IndicatorRuleStrategy, compute_features,
)


def _walk(n: int, seed: int = 7) -> list[Bar]:
    rng = np.random.default_rng(seed)
    px = 2000 + np.cumsum(rng.normal(0, 1.0, n))
    t0 = datetime(2026, 1, 5, 0, 0, tzinfo=UTC)
    out = []
    for i, c in enumerate(px):
        o = px[i - 1] if i else c
        out.append(Bar(ts=t0 + timedelta(minutes=15 * i), open=o, high=max(o, c) + abs(rng.normal(0, .4)),
                       low=min(o, c) - abs(rng.normal(0, .4)), close=c, volume=float(rng.integers(50, 500))))
    return out


def test_features_are_causal():
    bars = _walk(1500)
    full = compute_features(bars)
    for cut in (300, 777, 1200):
        part = compute_features(bars[:cut])
        pd.testing.assert_frame_equal(part, full.iloc[:cut], check_freq=False)


def test_rule_strategy_uses_series_previous_bar_not_last_call():
    bars = _walk(600)
    feats = compute_features(bars)
    s = IndicatorRuleStrategy(INDICATOR_RULES[0], feats)
    # previous-bar lookup is the immediately preceding bar in the series
    assert s._prev[bars[400].ts] == s._rows[bars[399].ts]
    sig = s.on_bar(bars[400], StrategyContext(history=bars[:401], has_open_position=False))
    assert sig is None or sig.stop_price != sig.target_price
