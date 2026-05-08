"""Tests for plugin discovery and validation."""
import pytest

from xillion.core.plugin_loader import PluginLoader


@pytest.mark.asyncio
async def test_discovers_example_strategy():
    loader = PluginLoader()
    registry = await loader.discover_all()
    assert "SMA Cross" in registry.strategies


@pytest.mark.asyncio
async def test_discovers_paper_broker():
    loader = PluginLoader()
    registry = await loader.discover_all()
    assert "Paper" in registry.brokers


@pytest.mark.asyncio
async def test_discovers_backtest_broker():
    loader = PluginLoader()
    registry = await loader.discover_all()
    assert "Backtest" in registry.brokers


@pytest.mark.asyncio
async def test_no_crashes_on_missing_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("STRATEGIES_DIR", str(tmp_path / "nonexistent_strategies"))
    monkeypatch.setenv("BROKERS_DIR", str(tmp_path / "nonexistent_brokers"))
    # Must re-import config to pick up new env
    from xillion import config as cfg
    cfg.get_settings.cache_clear()
    loader = PluginLoader()
    registry = await loader.discover_all()
    assert registry.strategies == {}
    assert registry.brokers == {}
    # Restore
    cfg.get_settings.cache_clear()


@pytest.mark.asyncio
async def test_sma_cross_has_params_schema():
    loader = PluginLoader()
    registry = await loader.discover_all()
    cls = registry.strategies["SMA Cross"]
    param_names = [p.name for p in cls.params_schema]
    assert "fast" in param_names
    assert "slow" in param_names
    assert "qty" in param_names
