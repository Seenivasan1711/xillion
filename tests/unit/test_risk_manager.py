"""Unit tests for RiskManager: OPS limiter, kill switch, loss gates, position limit."""
import time
from decimal import Decimal

import pytest

from xillion.core.events import OrderRequest, OrderType, Side
from xillion.core.risk import RiskApproved, RiskManager, RiskRejected, StrategyRiskConfig


def _order(qty: int = 1, strategy_id: str = "test-strat") -> OrderRequest:
    req = OrderRequest(
        symbol="NIFTY",
        side=Side.BUY,
        quantity=qty,
        order_type=OrderType.MARKET,
    )
    req.strategy_instance_id = strategy_id
    return req


def _config(capital: float = 100_000.0) -> StrategyRiskConfig:
    return StrategyRiskConfig(capital_allocation=Decimal(str(capital)))


# ── Kill switch ────────────────────────────────────────────────────────────────

def test_kill_switch_blocks_all_orders():
    rm = RiskManager()
    rm.activate_kill_switch()
    result = rm.check(_order(), _config())
    assert isinstance(result, RiskRejected)
    assert "kill switch" in result.reason


def test_reset_kill_switch_allows_orders():
    rm = RiskManager()
    rm.activate_kill_switch()
    rm.reset_kill_switch()
    assert isinstance(rm.check(_order(), _config()), RiskApproved)


def test_kill_switch_status_reflects_state():
    rm = RiskManager()
    assert not rm.kill_switch_active
    rm.activate_kill_switch()
    assert rm.kill_switch_active
    rm.reset_kill_switch()
    assert not rm.kill_switch_active


# ── Invalid quantity ───────────────────────────────────────────────────────────

def test_zero_quantity_rejected():
    rm = RiskManager()
    result = rm.check(_order(qty=0), _config())
    assert isinstance(result, RiskRejected)
    assert "quantity" in result.reason


def test_negative_quantity_rejected():
    rm = RiskManager()
    result = rm.check(_order(qty=-5), _config())
    assert isinstance(result, RiskRejected)


# ── OPS limiter ────────────────────────────────────────────────────────────────

def test_ops_limit_throttles_burst(monkeypatch):
    """Submit OPS_LIMIT orders in one second — the (limit+1)th must be rejected."""
    from xillion.config import get_settings
    limit = get_settings().ops_limit_per_second  # typically 9

    rm = RiskManager()
    # Fill up to the limit
    for _ in range(limit):
        result = rm.check(_order(), _config())
        assert isinstance(result, RiskApproved), f"Expected Approved but got {result}"

    # One more should be throttled
    result = rm.check(_order(), _config())
    assert isinstance(result, RiskRejected)
    assert "OPS limit" in result.reason


def test_ops_window_resets_after_one_second(monkeypatch):
    """After the sliding window rolls off, orders should be approved again."""
    from xillion.config import get_settings
    from xillion.core import risk as risk_mod

    limit = get_settings().ops_limit_per_second
    rm = RiskManager()

    # Saturate the window
    for _ in range(limit):
        rm.check(_order(), _config())

    # Wind the clock forward by >1 second using monkeypatch
    original_monotonic = time.monotonic
    monkeypatch.setattr(time, "monotonic", lambda: original_monotonic() + 1.1)

    result = rm.check(_order(), _config())
    assert isinstance(result, RiskApproved)


# ── Daily loss gates ───────────────────────────────────────────────────────────

def test_account_daily_loss_gate():
    rm = RiskManager()
    cfg = _config(capital=10_000.0)
    # Record a loss large enough to trip the gate (account daily loss pct = 3% = ₹300)
    rm.record_loss("test-strat", Decimal("-500"))
    result = rm.check(_order(), cfg)
    assert isinstance(result, RiskRejected)
    assert "daily loss" in result.reason


def test_no_loss_recorded_allows_order():
    rm = RiskManager()
    assert isinstance(rm.check(_order(), _config()), RiskApproved)


def test_reset_daily_clears_loss():
    rm = RiskManager()
    cfg = _config(capital=10_000.0)
    rm.record_loss("test-strat", Decimal("-500"))
    rm.reset_daily()
    assert isinstance(rm.check(_order(), cfg), RiskApproved)


def test_per_strategy_loss_gate():
    rm = RiskManager()
    cfg = StrategyRiskConfig(
        capital_allocation=Decimal("10000"),
        daily_loss_pct=2.0,  # ₹200 limit
    )
    rm.record_loss("test-strat", Decimal("-300"))
    result = rm.check(_order(strategy_id="test-strat"), cfg)
    assert isinstance(result, RiskRejected)
    assert "strategy daily loss" in result.reason


# ── Max open positions ─────────────────────────────────────────────────────────

def test_max_positions_gate():
    rm = RiskManager()
    cfg = StrategyRiskConfig(capital_allocation=Decimal("100000"), max_open_positions=2)
    result = rm.check(_order(), cfg, current_positions=2)
    assert isinstance(result, RiskRejected)
    assert "positions" in result.reason


def test_below_max_positions_approved():
    rm = RiskManager()
    cfg = StrategyRiskConfig(capital_allocation=Decimal("100000"), max_open_positions=5)
    assert isinstance(rm.check(_order(), cfg, current_positions=4), RiskApproved)


# ── notify callback ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_notify_called_on_kill_switch():
    import asyncio
    calls = []

    async def fake_notify(title, body, severity):
        calls.append((title, severity))

    rm = RiskManager()
    rm.set_notify(fake_notify)

    loop = asyncio.get_event_loop()
    rm.activate_kill_switch()
    await asyncio.sleep(0)  # let the task run

    assert len(calls) == 1
    assert calls[0][1] == "critical"
