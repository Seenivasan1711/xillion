"""
Generic entry/exit condition evaluation for ConditionStrategy (CP5) -- the
metric/operator/threshold rows the Strategy Builder UI produces, so a new
setup needs a JSON blob of conditions, not a new Python file.

A condition is a plain dict (this is what travels over JSON as a strategy
param, so dataclasses would just add a conversion layer with nothing to
show for it):

    {"metric": {"name": "rsi", "period": 14}, "operator": ">", "threshold": 70}
    {"metric": {"name": "close"}, "operator": "crosses_above",
     "other_metric": {"name": "sma", "period": 20}}

Exactly one of "threshold" (a literal number) or "other_metric" (a second
metric spec) must be set.
"""

from xillion.core.events import Bar
from xillion.engine import indicators as ind

OPERATORS = (">", "<", ">=", "<=", "==", "crosses_above", "crosses_below")
METRICS = (
    "close",
    "open",
    "high",
    "low",
    "volume",
    "sma",
    "ema",
    "rsi",
    "atr",
    "vwap",
    "bb_upper",
    "bb_mid",
    "bb_lower",
    "macd_line",
    "macd_signal",
    "macd_hist",
    "supertrend",
)


def _compute_metric(bars: list[Bar], metric: dict) -> float | None:
    name = metric["name"]
    if name not in METRICS:
        raise ValueError(f"Unknown metric {name!r}")
    if not bars:
        return None

    if name == "close":
        return float(bars[-1].close)
    if name == "open":
        return float(bars[-1].open)
    if name == "high":
        return float(bars[-1].high)
    if name == "low":
        return float(bars[-1].low)
    if name == "volume":
        return float(bars[-1].volume)

    period = int(metric.get("period", 14))
    closes = [float(b.close) for b in bars]

    if name == "sma":
        return ind.sma(closes, period)
    if name == "ema":
        return ind.ema(closes, period)
    if name == "rsi":
        return ind.rsi(closes, period)
    if name == "atr":
        return ind.atr(bars, period)
    if name == "vwap":
        return ind.vwap(bars, period)
    if name in ("bb_upper", "bb_mid", "bb_lower"):
        bands = ind.bollinger(closes, period, float(metric.get("num_std", 2.0)))
        if bands is None:
            return None
        lower, mid, upper = bands
        return {"bb_lower": lower, "bb_mid": mid, "bb_upper": upper}[name]
    if name in ("macd_line", "macd_signal", "macd_hist"):
        m = ind.macd(
            closes,
            int(metric.get("fast", 12)),
            int(metric.get("slow", 26)),
            int(metric.get("signal", 9)),
        )
        if m is None:
            return None
        line, signal, hist = m
        return {"macd_line": line, "macd_signal": signal, "macd_hist": hist}[name]
    if name == "supertrend":
        st = ind.supertrend(bars, period, float(metric.get("multiplier", 3.0)))
        return st[0] if st else None

    raise ValueError(f"Unknown metric {name!r}")  # unreachable, satisfies type checkers


def evaluate(condition: dict, bars: list[Bar]) -> bool | None:
    """True/False, or None if there isn't enough history yet to compute."""
    operator = condition["operator"]
    if operator not in OPERATORS:
        raise ValueError(f"Unknown operator {operator!r}")

    metric = condition["metric"]
    other_metric = condition.get("other_metric")
    threshold = condition.get("threshold")

    current = _compute_metric(bars, metric)
    if current is None:
        return None

    if operator in ("crosses_above", "crosses_below"):
        if len(bars) < 2:
            return None
        prev_bars = bars[:-1]
        prev = _compute_metric(prev_bars, metric)
        if prev is None:
            return None
        if other_metric is not None:
            current_ref = _compute_metric(bars, other_metric)
            prev_ref = _compute_metric(prev_bars, other_metric)
        else:
            current_ref = prev_ref = threshold
        if current_ref is None or prev_ref is None:
            return None
        if operator == "crosses_above":
            return prev <= prev_ref and current > current_ref
        return prev >= prev_ref and current < current_ref

    ref = _compute_metric(bars, other_metric) if other_metric is not None else threshold
    if ref is None:
        return None
    if operator == ">":
        return current > ref
    if operator == "<":
        return current < ref
    if operator == ">=":
        return current >= ref
    if operator == "<=":
        return current <= ref
    return current == ref  # "=="


def evaluate_all(conditions: list[dict], bars: list[Bar]) -> bool | None:
    """AND of every condition. None (not enough data yet) if any one of
    them can't be evaluated -- an empty list is always False, never "no
    conditions means always enter", which would be a dangerous default."""
    if not conditions:
        return False
    results = [evaluate(c, bars) for c in conditions]
    if any(r is None for r in results):
        return None
    return all(results)
