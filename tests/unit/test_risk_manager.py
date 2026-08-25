"""
Unit tests for RiskManager (CP13: expanded from 6 checks toward the ~20 in
automation-platform-spec/10-RISK-ENGINE.md §10.2). Each check has at least
one test proving it blocks when it alone fails, per that spec's own
testing-requirements section (10.8).
"""
import time
from decimal import Decimal

import pytest

from xillion.core.events import Order, OrderRequest, OrderStatus, OrderType, Side
from xillion.core.risk import MarketContext, RiskApproved, RiskManager, RiskRejected, StrategyRiskConfig


def _order(qty: int = 1, strategy_id: str = "test-strat", price=None, symbol="NIFTY", side=Side.BUY) -> OrderRequest:
    req = OrderRequest(
        symbol=symbol, side=side, quantity=qty,
        order_type=OrderType.LIMIT if price is not None else OrderType.MARKET,
        price=Decimal(str(price)) if price is not None else None,
    )
    req.strategy_instance_id = strategy_id
    return req


def _config(capital: float = 100_000.0, **kwargs) -> StrategyRiskConfig:
    return StrategyRiskConfig(capital_allocation=Decimal(str(capital)), **kwargs)


def _open_order(symbol="NIFTY", side=Side.SELL) -> Order:
    return Order(
        client_order_id="existing-1", symbol=symbol, side=side, quantity=1,
        order_type=OrderType.LIMIT, status=OrderStatus.ACCEPTED,
        submitted_at=None, updated_at=None,
    )


# ── Kill switch ────────────────────────────────────────────────────────────────

def test_kill_switch_blocks_all_orders():
    rm = RiskManager()
    rm.activate_kill_switch()
    result = rm.check(_order(), _config())
    assert isinstance(result, RiskRejected)
    assert "kill_switch_clear" in result.failed_checks


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


# ── Trading pause (CP13) — softer than the kill switch, manually reversible ────

def test_pause_trading_blocks_orders():
    rm = RiskManager()
    rm.pause_trading()
    result = rm.check(_order(), _config())
    assert isinstance(result, RiskRejected)
    assert "trading_enabled" in result.failed_checks


def test_resume_trading_allows_orders_again():
    rm = RiskManager()
    rm.pause_trading()
    rm.resume_trading()
    assert isinstance(rm.check(_order(), _config()), RiskApproved)


# ── Invalid / sane quantity ─────────────────────────────────────────────────────

def test_zero_quantity_rejected():
    rm = RiskManager()
    result = rm.check(_order(qty=0), _config())
    assert isinstance(result, RiskRejected)
    assert "qty_positive" in result.failed_checks


def test_negative_quantity_rejected():
    rm = RiskManager()
    result = rm.check(_order(qty=-5), _config())
    assert isinstance(result, RiskRejected)
    assert "qty_positive" in result.failed_checks


def test_qty_over_sane_ceiling_rejected():
    from xillion.config import get_settings
    rm = RiskManager()
    result = rm.check(_order(qty=get_settings().default_max_qty_per_order + 1), _config())
    assert isinstance(result, RiskRejected)
    assert "qty_sane" in result.failed_checks


# ── Lot-size / freeze-qty checks (CP13, only run when MarketContext supplies them) ─

def test_qty_not_a_lot_multiple_rejected():
    rm = RiskManager()
    ctx = MarketContext(lot_size=65)
    result = rm.check(_order(qty=100), _config(), market_context=ctx)  # not a multiple of 65
    assert isinstance(result, RiskRejected)
    assert "qty_lot_multiple" in result.failed_checks


def test_qty_lot_multiple_passes_when_divisible():
    rm = RiskManager()
    ctx = MarketContext(lot_size=65)
    result = rm.check(_order(qty=130), _config(), market_context=ctx)
    assert isinstance(result, RiskApproved)


def test_qty_lot_multiple_skipped_without_lot_size():
    """No lot_size supplied -- the check must be SKIPPED, not failed."""
    rm = RiskManager()
    result = rm.check(_order(qty=7), _config())  # not a multiple of anything sensible
    assert isinstance(result, RiskApproved)


def test_qty_beyond_freeze_limit_rejected():
    rm = RiskManager()
    ctx = MarketContext(freeze_qty=1800)
    result = rm.check(_order(qty=1801), _config(), market_context=ctx)
    assert isinstance(result, RiskRejected)
    assert "qty_within_freeze" in result.failed_checks


# ── Price checks (tick, collar, circuit) ────────────────────────────────────────

def test_price_not_tick_multiple_rejected():
    rm = RiskManager()
    ctx = MarketContext(tick_size=Decimal("0.05"))
    result = rm.check(_order(price="100.03"), _config(), market_context=ctx)
    assert isinstance(result, RiskRejected)
    assert "price_tick_multiple" in result.failed_checks


def test_price_tick_multiple_passes():
    rm = RiskManager()
    ctx = MarketContext(tick_size=Decimal("0.05"))
    result = rm.check(_order(price="100.05"), _config(), market_context=ctx)
    assert isinstance(result, RiskApproved)


def test_price_collar_rejects_fat_finger_price():
    """A limit price 10x the LTP -- the exact fat-finger scenario the spec
    calls out as having "saved more retail accounts than any other single
    control"."""
    rm = RiskManager()
    ctx = MarketContext(ltp=Decimal("100"))
    result = rm.check(_order(price="1000"), _config(), market_context=ctx)
    assert isinstance(result, RiskRejected)
    assert "price_collar" in result.failed_checks


def test_price_collar_allows_price_within_band():
    rm = RiskManager()
    ctx = MarketContext(ltp=Decimal("100"))
    result = rm.check(_order(price="110"), _config(), market_context=ctx)
    assert isinstance(result, RiskApproved)


def test_price_collar_skipped_for_market_orders():
    """MARKET orders carry no price to collar-check -- must not fail."""
    rm = RiskManager()
    ctx = MarketContext(ltp=Decimal("100"))
    result = rm.check(_order(price=None), _config(), market_context=ctx)
    assert isinstance(result, RiskApproved)


def test_price_outside_circuit_rejected():
    rm = RiskManager()
    ctx = MarketContext(lower_circuit=Decimal("90"), upper_circuit=Decimal("110"))
    result = rm.check(_order(price="115"), _config(), market_context=ctx)
    assert isinstance(result, RiskRejected)
    assert "price_within_circuit" in result.failed_checks


def test_notional_over_cap_rejected():
    from xillion.config import get_settings
    rm = RiskManager()
    over_cap_price = (get_settings().default_max_notional_per_order / 1) + 1000
    ctx = MarketContext(ltp=Decimal(str(over_cap_price)))
    result = rm.check(_order(qty=1), _config(), market_context=ctx)
    assert isinstance(result, RiskRejected)
    assert "notional_sane" in result.failed_checks


# ── OPS limiter: soft throttle + hard ceiling ───────────────────────────────────

def test_ops_soft_limit_throttles_burst(monkeypatch):
    from xillion.config import get_settings
    monkeypatch.setattr(get_settings(), "ops_limit_per_second", 3)
    monkeypatch.setattr(get_settings(), "ops_burst_ceiling", 9)  # keep well clear of the hard ceiling

    rm = RiskManager()
    for _ in range(3):
        result = rm.check(_order(), _config())
        assert isinstance(result, RiskApproved)

    result = rm.check(_order(), _config())
    assert isinstance(result, RiskRejected)
    assert "ops_budget_ok" in result.failed_checks


def test_ops_window_resets_after_one_second(monkeypatch):
    from xillion.config import get_settings
    monkeypatch.setattr(get_settings(), "ops_limit_per_second", 3)
    monkeypatch.setattr(get_settings(), "ops_burst_ceiling", 9)

    rm = RiskManager()
    for _ in range(3):
        rm.check(_order(), _config())

    original_monotonic = time.monotonic
    monkeypatch.setattr(time, "monotonic", lambda: original_monotonic() + 1.1)

    result = rm.check(_order(), _config())
    assert isinstance(result, RiskApproved)


def test_ops_hard_ceiling_breach_fires_kill_switch(monkeypatch):
    """Hitting the burst ceiling is a runaway-loop signal -- spec: 'stop
    trading, don't throttle and continue'. Kill switch must fire."""
    from xillion.config import get_settings
    monkeypatch.setattr(get_settings(), "ops_limit_per_second", 2)
    monkeypatch.setattr(get_settings(), "ops_burst_ceiling", 4)

    rm = RiskManager()
    assert not rm.kill_switch_active
    for _ in range(4):
        rm.check(_order(), _config())  # some approved, some soft-throttled

    assert rm.kill_switch_active
    result = rm.check(_order(), _config())
    assert isinstance(result, RiskRejected)
    assert "ops_ceiling_breach" in result.failed_checks


# ── Idempotency (duplicate order dedup) ────────────────────────────────────────

def test_duplicate_client_order_id_rejected():
    rm = RiskManager()
    req = _order()
    first = rm.check(req, _config())
    assert isinstance(first, RiskApproved)

    second = rm.check(req, _config())  # SAME client_order_id
    assert isinstance(second, RiskRejected)
    assert "not_duplicate" in second.failed_checks


def test_different_order_ids_not_treated_as_duplicates():
    rm = RiskManager()
    assert isinstance(rm.check(_order(), _config()), RiskApproved)
    assert isinstance(rm.check(_order(), _config()), RiskApproved)  # fresh client_order_id each time


def test_duplicate_check_expires_after_the_idempotency_window(monkeypatch):
    rm = RiskManager()
    req = _order()
    rm.check(req, _config())

    original_monotonic = time.monotonic
    monkeypatch.setattr(time, "monotonic", lambda: original_monotonic() + rm._IDEMPOTENCY_WINDOW_SECONDS + 1)
    result = rm.check(req, _config())
    assert isinstance(result, RiskApproved)


# ── Self-trade guard ────────────────────────────────────────────────────────────

def test_opposite_side_open_order_same_symbol_rejected():
    rm = RiskManager()
    ctx = MarketContext(open_orders=[_open_order(symbol="NIFTY", side=Side.SELL)])
    result = rm.check(_order(symbol="NIFTY", side=Side.BUY), _config(), market_context=ctx)
    assert isinstance(result, RiskRejected)
    assert "not_self_trade" in result.failed_checks


def test_same_side_open_order_is_not_a_self_trade():
    rm = RiskManager()
    ctx = MarketContext(open_orders=[_open_order(symbol="NIFTY", side=Side.BUY)])
    result = rm.check(_order(symbol="NIFTY", side=Side.BUY), _config(), market_context=ctx)
    assert isinstance(result, RiskApproved)


def test_opposite_side_open_order_different_symbol_is_fine():
    """A credit spread's own long/short legs are DIFFERENT symbols (different
    strikes) -- must not trip this guard."""
    rm = RiskManager()
    ctx = MarketContext(open_orders=[_open_order(symbol="NIFTY_LONG_PE", side=Side.BUY)])
    result = rm.check(_order(symbol="NIFTY_SHORT_PE", side=Side.SELL), _config(), market_context=ctx)
    assert isinstance(result, RiskApproved)


# ── Daily order-count cap ───────────────────────────────────────────────────────

def test_max_orders_per_day_rejects_beyond_cap():
    rm = RiskManager()
    cfg = _config(max_orders_per_day=2)
    assert isinstance(rm.check(_order(), cfg), RiskApproved)
    assert isinstance(rm.check(_order(), cfg), RiskApproved)
    result = rm.check(_order(), cfg)
    assert isinstance(result, RiskRejected)
    assert "order_count_sane" in result.failed_checks


def test_reset_daily_clears_order_count():
    rm = RiskManager()
    cfg = _config(max_orders_per_day=1)
    rm.check(_order(), cfg)
    rm.reset_daily()
    assert isinstance(rm.check(_order(), cfg), RiskApproved)


# ── Daily loss gates ───────────────────────────────────────────────────────────

def test_account_daily_loss_gate():
    rm = RiskManager()
    cfg = _config(capital=10_000.0)
    rm.record_loss("test-strat", Decimal("-500"))
    result = rm.check(_order(), cfg)
    assert isinstance(result, RiskRejected)
    assert "within_account_daily_loss" in result.failed_checks


def test_no_loss_recorded_allows_order():
    rm = RiskManager()
    assert isinstance(rm.check(_order(), _config()), RiskApproved)


def test_record_loss_ignores_non_negative_amounts():
    """record_loss is only ever meant to track losses; a profitable close
    (amount >= 0) must be a no-op, not accidentally reduce the loss tally."""
    rm = RiskManager()
    rm.record_loss("test-strat", Decimal("500"))  # a gain, not a loss
    assert rm._account_daily_loss == Decimal("0")


def test_record_loss_without_instance_id_still_updates_account_total():
    """Account-wide loss (e.g. a non-strategy-attributed fill) must still
    count even when there's no strategy_instance_id to attribute it to."""
    rm = RiskManager()
    rm.record_loss(None, Decimal("-100"))
    assert rm._account_daily_loss == Decimal("-100")
    assert rm._strategy_daily_loss == {}


def test_status_reports_current_state():
    rm = RiskManager()
    rm.record_loss("test-strat", Decimal("-50"))
    status = rm.status()
    assert status["kill_switch_active"] is False
    assert status["trading_enabled"] is True
    assert status["account_daily_loss"] == "-50"
    assert "ops_limit" in status and "ops_burst_ceiling" in status


def test_approved_order_without_strategy_instance_id_does_not_track_order_count():
    """An order with no strategy_instance_id (e.g. a manual/ungoverned
    order) can still be approved -- there's just nothing to attribute the
    daily order count to."""
    rm = RiskManager()
    req = OrderRequest(symbol="NIFTY", side=Side.BUY, quantity=1, order_type=OrderType.MARKET)
    assert req.strategy_instance_id is None
    result = rm.check(req, _config())
    assert isinstance(result, RiskApproved)
    assert rm._orders_today == {}


def test_reset_daily_clears_loss():
    rm = RiskManager()
    cfg = _config(capital=10_000.0)
    rm.record_loss("test-strat", Decimal("-500"))
    rm.reset_daily()
    assert isinstance(rm.check(_order(), cfg), RiskApproved)


def test_per_strategy_loss_gate():
    rm = RiskManager()
    cfg = _config(capital=10_000.0, daily_loss_pct=2.0)  # ₹200 limit
    rm.record_loss("test-strat", Decimal("-300"))
    result = rm.check(_order(strategy_id="test-strat"), cfg)
    assert isinstance(result, RiskRejected)
    assert "within_strategy_daily_loss" in result.failed_checks


# ── Max open positions ─────────────────────────────────────────────────────────

def test_max_positions_gate():
    rm = RiskManager()
    cfg = _config(max_open_positions=2)
    result = rm.check(_order(), cfg, current_positions=2)
    assert isinstance(result, RiskRejected)
    assert "max_open_positions_ok" in result.failed_checks


def test_below_max_positions_approved():
    rm = RiskManager()
    cfg = _config(max_open_positions=5)
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
    rm.activate_kill_switch()
    await asyncio.sleep(0)  # let the task run

    assert len(calls) == 1
    assert calls[0][1] == "critical"
