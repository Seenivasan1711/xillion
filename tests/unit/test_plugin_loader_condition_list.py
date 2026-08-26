"""
Regression: ConditionStrategy's `condition_list` param type must pass
plugin validation. Found by actually loading the app in a browser during
CP5 verification -- the strategy dropdown silently omitted "Condition
Strategy" because _validate_strategy_class rejected the type and
plugin discovery logged the failure instead of raising where anyone would
see it during normal use.
"""

import pytest

from xillion.core.plugin_loader import PluginLoader


@pytest.mark.asyncio
async def test_condition_strategy_is_discovered_without_error():
    loader = PluginLoader()
    registry = await loader.discover_all()

    assert "condition_strategy" not in registry.errors
    assert "Condition Strategy" in registry.strategies
