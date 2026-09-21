"""
fill_param_defaults: found for real 2026-09-21 when a `{}` params payload
(sent via a direct API call, not the dashboard form -- which always seeds
every param from params_schema, so this gap was invisible there) crashed
a strategy's very first ctx.params["x"] access, both for a live instance
and a provider-backed backtest run. Every caller that reaches a strategy
with a params dict (instance creation, /run, /run-csv, /run-provider,
/optimize, /walk-forward) merges through this first.
"""

from xillion.core.strategy_base import ParamSpec, Strategy, fill_param_defaults


class _FakeStrategy(Strategy):
    name = "Fake"
    params_schema = [
        ParamSpec("a", "int", default=1),
        ParamSpec("b", "float", default=2.5),
        ParamSpec("c", "str", default="x"),
    ]


def test_empty_params_gets_every_default():
    assert fill_param_defaults(_FakeStrategy, {}) == {"a": 1, "b": 2.5, "c": "x"}


def test_explicit_values_override_defaults():
    result = fill_param_defaults(_FakeStrategy, {"a": 99})
    assert result == {"a": 99, "b": 2.5, "c": "x"}


def test_unknown_keys_in_input_are_dropped_not_carried_through():
    # Only params_schema's own keys should ever reach a strategy -- a typo
    # or stale key in the request shouldn't silently pass through.
    result = fill_param_defaults(_FakeStrategy, {"a": 5, "not_a_real_param": 123})
    assert result == {"a": 5, "b": 2.5, "c": "x"}
