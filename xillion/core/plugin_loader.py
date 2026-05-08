"""
Plugin loader: scans strategies/ and brokers/ directories, imports each .py
file, validates the plugin contract, and registers valid plugins.
Failed plugins are logged and skipped — they never crash the host process.
"""
import hashlib
import importlib.util
import inspect
import sys
from pathlib import Path
from typing import Type

import structlog

from xillion.config import get_settings
from xillion.core.broker_base import Broker
from xillion.core.strategy_base import Strategy

logger = structlog.get_logger(__name__)


class PluginLoadError(Exception):
    pass


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _import_module_from_file(path: Path):
    module_name = f"_xillion_plugin_{path.stem}_{abs(hash(str(path)))}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise PluginLoadError(f"Cannot load spec for {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _validate_strategy_class(cls: Type[Strategy]) -> None:
    if not cls.name:
        raise PluginLoadError(f"{cls.__name__} has empty 'name' attribute")
    for spec in cls.params_schema:
        if spec.type not in {"int", "float", "str", "bool", "choice"}:
            raise PluginLoadError(
                f"{cls.__name__} param '{spec.name}' has unsupported type '{spec.type}'"
            )
        if spec.type == "choice" and not spec.choices:
            raise PluginLoadError(
                f"{cls.__name__} param '{spec.name}' is 'choice' but has no choices"
            )


def _validate_broker_class(cls: Type[Broker]) -> None:
    if not cls.name:
        raise PluginLoadError(f"{cls.__name__} has empty 'name' attribute")


class PluginRegistry:
    def __init__(self) -> None:
        self.strategies: dict[str, Type[Strategy]] = {}
        self.brokers: dict[str, Type[Broker]] = {}
        self.strategy_file_hashes: dict[str, str] = {}
        self.broker_file_hashes: dict[str, str] = {}
        self.errors: dict[str, str] = {}


class PluginLoader:
    def __init__(self) -> None:
        self.registry = PluginRegistry()
        s = get_settings()
        self._strategies_dir = Path(s.strategies_dir)
        self._brokers_dir = Path(s.brokers_dir)

    async def discover_all(self) -> PluginRegistry:
        self.registry = PluginRegistry()
        self._discover_strategies()
        self._discover_brokers()
        logger.info(
            "plugin discovery complete",
            strategies=list(self.registry.strategies.keys()),
            brokers=list(self.registry.brokers.keys()),
            errors=self.registry.errors,
        )
        return self.registry

    def _discover_strategies(self) -> None:
        if not self._strategies_dir.exists():
            logger.warning("strategies dir not found", path=str(self._strategies_dir))
            return
        for py_file in sorted(self._strategies_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            self._load_strategy_file(py_file)

    def _discover_brokers(self) -> None:
        if not self._brokers_dir.exists():
            logger.warning("brokers dir not found", path=str(self._brokers_dir))
            return
        for py_file in sorted(self._brokers_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            self._load_broker_file(py_file)

    def _load_strategy_file(self, path: Path) -> None:
        try:
            module = _import_module_from_file(path)
            found = 0
            for _, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, Strategy) and obj is not Strategy:
                    _validate_strategy_class(obj)
                    if obj.name in self.registry.strategies:
                        logger.warning(
                            "duplicate strategy name, skipping",
                            name=obj.name,
                            file=str(path),
                        )
                        continue
                    self.registry.strategies[obj.name] = obj
                    self.registry.strategy_file_hashes[obj.name] = _file_hash(path)
                    logger.info("strategy loaded", name=obj.name, file=path.name)
                    found += 1
            if found == 0:
                logger.warning("no Strategy subclass found", file=str(path))
        except Exception as exc:
            key = f"strategy:{path.stem}"
            self.registry.errors[key] = str(exc)
            logger.error("strategy load failed", file=str(path), error=str(exc))

    def _load_broker_file(self, path: Path) -> None:
        try:
            module = _import_module_from_file(path)
            found = 0
            for _, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, Broker) and obj is not Broker:
                    _validate_broker_class(obj)
                    if obj.name in self.registry.brokers:
                        logger.warning(
                            "duplicate broker name, skipping",
                            name=obj.name,
                            file=str(path),
                        )
                        continue
                    self.registry.brokers[obj.name] = obj
                    self.registry.broker_file_hashes[obj.name] = _file_hash(path)
                    logger.info("broker loaded", name=obj.name, file=path.name)
                    found += 1
            if found == 0:
                logger.warning("no Broker subclass found", file=str(path))
        except Exception as exc:
            key = f"broker:{path.stem}"
            self.registry.errors[key] = str(exc)
            logger.error("broker load failed", file=str(path), error=str(exc))
