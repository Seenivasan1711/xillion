"""
Condition evaluator (CP5): metric/operator/threshold and metric/operator/
metric comparisons, crosses_above/below, and the AND-of-all-conditions /
None-means-not-enough-data-yet contract that ConditionStrategy relies on.
"""
from datetime import datetime, timedelta
from decimal import Decimal

from xillion.core.events import Bar
from xillion.engine.condition import evaluate, evaluate_all


def _bars(closes: list[float]) -> list[Bar]:
    ts = datetime(2026, 1, 1)
    return [
        Bar(symbol="X", timeframe="1d", ts=ts + timedelta(days=i),
            open=Decimal(str(c)), high=Decimal(str(c)), low=Decimal(str(c)),
            close=Decimal(str(c)), volume=100)
        for i, c in enumerate(closes)
    ]


def test_literal_threshold_comparison():
    bars = _bars([1, 2, 3, 4, 5])
    assert evaluate({"metric": {"name": "close"}, "operator": ">", "threshold": 4}, bars) is True
    assert evaluate({"metric": {"name": "close"}, "operator": ">", "threshold": 5}, bars) is False
    assert evaluate({"metric": {"name": "close"}, "operator": "<=", "threshold": 5}, bars) is True


def test_indicator_metric_threshold():
    bars = _bars([10, 12, 11, 13, 12, 14])
    # rsi(period=5) on this series is 75.0, hand-checked in test_indicators.py
    assert evaluate({"metric": {"name": "rsi", "period": 5}, "operator": ">", "threshold": 70}, bars) is True
    assert evaluate({"metric": {"name": "rsi", "period": 5}, "operator": ">", "threshold": 80}, bars) is False


def test_metric_vs_metric_comparison():
    # close currently above sma(3) since the series is rising
    bars = _bars([1, 2, 3, 4, 10])
    cond = {"metric": {"name": "close"}, "operator": ">", "other_metric": {"name": "sma", "period": 3}}
    assert evaluate(cond, bars) is True


def test_crosses_above_literal_threshold():
    # rising through 3: prev close=2 (<=3), current close=4 (>3)
    bars = _bars([1, 2, 4])
    cond = {"metric": {"name": "close"}, "operator": "crosses_above", "threshold": 3}
    assert evaluate(cond, bars) is True

    # already above on the previous bar too -- not a fresh cross
    bars2 = _bars([5, 6, 7])
    assert evaluate(cond, bars2) is False


def test_crosses_below_literal_threshold():
    bars = _bars([6, 5, 2])
    cond = {"metric": {"name": "close"}, "operator": "crosses_below", "threshold": 3}
    assert evaluate(cond, bars) is True


def test_crosses_above_metric_vs_metric():
    # close crosses above its own sma(3): construct a dip-then-spike
    bars = _bars([10, 9, 8, 7, 20])
    cond = {"metric": {"name": "close"}, "operator": "crosses_above", "other_metric": {"name": "sma", "period": 3}}
    result = evaluate(cond, bars)
    assert result is True


def test_none_when_not_enough_history():
    bars = _bars([1, 2])
    cond = {"metric": {"name": "rsi", "period": 14}, "operator": ">", "threshold": 50}
    assert evaluate(cond, bars) is None


def test_crosses_needs_at_least_two_bars():
    bars = _bars([5])
    cond = {"metric": {"name": "close"}, "operator": "crosses_above", "threshold": 3}
    assert evaluate(cond, bars) is None


def test_evaluate_all_is_and_of_every_condition():
    bars = _bars([10, 12, 11, 13, 12, 14])
    conditions = [
        {"metric": {"name": "rsi", "period": 5}, "operator": ">", "threshold": 70},  # True (75.0)
        {"metric": {"name": "close"}, "operator": ">", "threshold": 13},              # True (14 > 13)
    ]
    assert evaluate_all(conditions, bars) is True

    conditions_with_one_false = conditions + [{"metric": {"name": "close"}, "operator": ">", "threshold": 100}]
    assert evaluate_all(conditions_with_one_false, bars) is False


def test_evaluate_all_empty_list_is_false_not_true():
    """An empty condition list must never silently mean 'always enter' --
    that would be a strategy that fires on every single bar."""
    bars = _bars([1, 2, 3])
    assert evaluate_all([], bars) is False


def test_evaluate_all_none_when_any_condition_lacks_data():
    bars = _bars([1, 2])
    conditions = [
        {"metric": {"name": "close"}, "operator": ">", "threshold": 1},          # True
        {"metric": {"name": "rsi", "period": 14}, "operator": ">", "threshold": 50},  # None
    ]
    assert evaluate_all(conditions, bars) is None
