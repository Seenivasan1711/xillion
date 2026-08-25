"""CP11 protective order levels (E07): stop/target on spread value, time stop."""
from datetime import date
from decimal import Decimal

import pytest

from xillion.core.multileg import StructureType
from xillion.core.protective_orders import (
    check_exit_trigger, credit_spread_protective_levels, is_defined_risk, spread_value,
)


def test_credit_spread_levels_match_kb_break_even_table():
    # KB 10 §6: 50% target / 100% stop is the base combination.
    spec = credit_spread_protective_levels(Decimal("10"))
    assert spec.stop_value == Decimal("20")     # 2x credit = 100% loss
    assert spec.target_value == Decimal("5")    # 50% of credit captured


def test_credit_spread_levels_reject_nonpositive_credit():
    with pytest.raises(ValueError):
        credit_spread_protective_levels(Decimal("0"))


def test_spread_value_is_short_minus_long():
    assert spread_value(Decimal("12"), Decimal("4")) == Decimal("8")


def test_check_exit_trigger_none_when_between_target_and_stop():
    spec = credit_spread_protective_levels(Decimal("10"))
    assert check_exit_trigger(spec, Decimal("10"), date(2026, 1, 1)) is None


def test_check_exit_trigger_stop():
    spec = credit_spread_protective_levels(Decimal("10"))
    assert check_exit_trigger(spec, Decimal("20"), date(2026, 1, 1)) == "STOP"


def test_check_exit_trigger_target():
    spec = credit_spread_protective_levels(Decimal("10"))
    assert check_exit_trigger(spec, Decimal("5"), date(2026, 1, 1)) == "TARGET"


def test_check_exit_trigger_time_stop_beats_everything():
    spec = credit_spread_protective_levels(Decimal("10"), time_stop_date=date(2026, 1, 5))
    # Even though this value would otherwise read as a target hit, the
    # calendar gate fires first per check_exit_trigger's own ordering.
    assert check_exit_trigger(spec, Decimal("5"), date(2026, 1, 5)) == "TIME_STOP"
    assert check_exit_trigger(spec, Decimal("5"), date(2026, 1, 6)) == "TIME_STOP"


def test_check_exit_trigger_before_time_stop_date_uses_normal_levels():
    spec = credit_spread_protective_levels(Decimal("10"), time_stop_date=date(2026, 1, 5))
    assert check_exit_trigger(spec, Decimal("10"), date(2026, 1, 4)) is None


def test_is_defined_risk():
    assert is_defined_risk(StructureType.CREDIT_SPREAD) is True
    assert is_defined_risk(StructureType.IRON_CONDOR) is True
