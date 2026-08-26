"""
ExecutionRouter <-> RiskManager wiring (CP9): submit() previously called
risk.check(request) with NO strategy_config and NO current_positions at
all, silently disabling the per-strategy daily-loss and max-open-positions
gates for every real order regardless of what was configured -- RiskManager
itself was already correctly tested (test_risk_manager.py), the bug was
entirely in this wiring layer, which had no tests of its own before this.
"""

from decimal import Decimal

import pytest

from brokers._dummy import DummyBroker
from xillion.core.events import OrderRequest, OrderType, Side
from xillion.core.execution import ExecutionRouter
from xillion.core.risk import RiskManager, StrategyRiskConfig


def _order(qty: int = 1) -> OrderRequest:
    req = OrderRequest(symbol="NIFTY", side=Side.BUY, quantity=qty, order_type=OrderType.MARKET)
    req.strategy_instance_id = "test-instance"
    return req


@pytest.mark.asyncio
async def test_submit_without_risk_config_still_applies_account_level_gates():
    """No risk_config passed (the old, buggy default) must not crash --
    account-level gates (kill switch, OPS, quantity) still apply, only the
    per-strategy ones are unavailable without a config, same as before."""
    router = ExecutionRouter(DummyBroker(), RiskManager())
    order = await router.submit(_order())
    assert order.status.value != "REJECTED"


@pytest.mark.asyncio
async def test_submit_enforces_per_strategy_daily_loss_when_config_is_wired():
    # capital=50000: account gate (default 3%) trips at -1500; per-strategy
    # gate (2%) trips at -1000. A -1200 loss must trip the per-strategy gate
    # specifically, not just happen to also trip the (already-tested,
    # unrelated) account-level one.
    risk = RiskManager()
    risk.record_loss("test-instance", Decimal("-1200"))
    config = StrategyRiskConfig(capital_allocation=Decimal("50000"), daily_loss_pct=2.0)
    router = ExecutionRouter(DummyBroker(), risk, risk_config=config)

    order = await router.submit(_order())
    assert order.status.value == "REJECTED"
    assert "within_strategy_daily_loss" in order.rejection_reason


@pytest.mark.asyncio
async def test_submit_enforces_max_open_positions_when_current_positions_passed():
    risk = RiskManager()
    config = StrategyRiskConfig(capital_allocation=Decimal("100000"), max_open_positions=2)
    router = ExecutionRouter(DummyBroker(), risk, risk_config=config)

    order = await router.submit(_order(), current_positions=2)
    assert order.status.value == "REJECTED"
    assert "positions" in order.rejection_reason


@pytest.mark.asyncio
async def test_submit_approves_when_under_the_configured_limits():
    risk = RiskManager()
    config = StrategyRiskConfig(
        capital_allocation=Decimal("100000"), max_open_positions=5, daily_loss_pct=5.0
    )
    router = ExecutionRouter(DummyBroker(), risk, risk_config=config)

    order = await router.submit(_order(), current_positions=1)
    assert order.status.value != "REJECTED"


def test_set_risk_config_replaces_it_for_subsequent_checks():
    router = ExecutionRouter(DummyBroker(), RiskManager())
    assert router.risk_config is None
    new_config = StrategyRiskConfig(capital_allocation=Decimal("50000"), max_open_positions=1)
    router.set_risk_config(new_config)
    assert router.risk_config is new_config
