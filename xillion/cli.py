"""
Xillion CLI. Entry point: `xillion <command>`.
"""
import asyncio
import csv
import json
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(name="xillion", help="Xillion — Personal Algorithmic Trading Platform")
db_app = typer.Typer(help="Database commands")
backtest_app = typer.Typer(help="Backtest commands")
plugin_app = typer.Typer(help="Plugin commands")

app.add_typer(db_app, name="db")
app.add_typer(backtest_app, name="backtest")
app.add_typer(plugin_app, name="plugins")

console = Console()


# ── Database ──────────────────────────────────────────────────────────────────

@db_app.command("upgrade")
def db_upgrade():
    """Run Alembic migrations to the latest revision."""
    import subprocess

    result = subprocess.run(["alembic", "upgrade", "head"], capture_output=False)
    if result.returncode != 0:
        raise typer.Exit(result.returncode)
    console.print("[green]Database upgraded.[/green]")


@db_app.command("init")
def db_init():
    """Create the data directory and run migrations."""
    Path("data").mkdir(exist_ok=True)
    db_upgrade()


# ── Plugin commands ────────────────────────────────────────────────────────────

@plugin_app.command("list")
def plugin_list():
    """Discover and list all plugins."""

    async def _run():
        from xillion.core.plugin_loader import PluginLoader

        loader = PluginLoader()
        registry = await loader.discover_all()

        strat_table = Table(title="Strategies")
        strat_table.add_column("Name", style="cyan")
        strat_table.add_column("Version")
        strat_table.add_column("Timeframe")
        strat_table.add_column("Description")
        for name, cls in registry.strategies.items():
            strat_table.add_row(name, cls.version, cls.timeframe, cls.description[:60])
        console.print(strat_table)

        broker_table = Table(title="Brokers")
        broker_table.add_column("Name", style="cyan")
        broker_table.add_column("Version")
        for name, cls in registry.brokers.items():
            broker_table.add_row(name, cls.version)
        console.print(broker_table)

        if registry.errors:
            console.print("[red]Load errors:[/red]")
            for key, err in registry.errors.items():
                console.print(f"  {key}: {err}")

    asyncio.run(_run())


# ── Backtest commands ──────────────────────────────────────────────────────────

@backtest_app.command("run")
def backtest_run(
    strategy: str = typer.Argument(..., help="Strategy name (as defined in strategy file)"),
    data: str = typer.Argument(..., help="Path to CSV file with OHLCV bars"),
    from_ts: Optional[str] = typer.Option(None, "--from", help="Start datetime (ISO format)"),
    to_ts: Optional[str] = typer.Option(None, "--to", help="End datetime (ISO format)"),
    capital: float = typer.Option(100000.0, "--capital", "-c", help="Initial capital"),
    slippage: int = typer.Option(5, "--slippage", help="Slippage in basis points"),
    params: Optional[str] = typer.Option(None, "--params", "-p", help="JSON params override"),
):
    """Run a backtest of a strategy against a CSV data file."""

    async def _run():
        from xillion.core.events import Bar
        from xillion.core.plugin_loader import PluginLoader
        from xillion.engine.backtest_engine import BacktestEngine

        # Load plugins
        loader = PluginLoader()
        registry = await loader.discover_all()
        cls = registry.strategies.get(strategy)
        if cls is None:
            console.print(f"[red]Strategy '{strategy}' not found.[/red]")
            console.print(f"Available: {list(registry.strategies.keys())}")
            raise typer.Exit(1)

        # Load CSV
        data_path = Path(data)
        if not data_path.exists():
            console.print(f"[red]File not found: {data}[/red]")
            raise typer.Exit(1)

        bars: list[Bar] = []
        with open(data_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts = datetime.fromisoformat(row["ts"])
                if from_ts and ts < datetime.fromisoformat(from_ts):
                    continue
                if to_ts and ts > datetime.fromisoformat(to_ts):
                    continue
                bars.append(
                    Bar(
                        symbol=row["symbol"],
                        timeframe=row.get("timeframe", cls.timeframe),
                        ts=ts,
                        open=Decimal(row["open"]),
                        high=Decimal(row["high"]),
                        low=Decimal(row["low"]),
                        close=Decimal(row["close"]),
                        volume=int(row.get("volume", 0)),
                    )
                )

        if not bars:
            console.print("[red]No bars found in file (check --from/--to filters).[/red]")
            raise typer.Exit(1)

        instruments = list({b.symbol for b in bars})
        extra_params = json.loads(params) if params else {}
        # Merge defaults from schema with overrides
        merged_params = {p.name: p.default for p in cls.params_schema}
        merged_params.update(extra_params)

        console.print(
            f"Running backtest: [cyan]{strategy}[/cyan] | "
            f"{len(bars)} bars | capital={capital:,.0f} | slippage={slippage}bps"
        )

        engine = BacktestEngine()
        result = await engine.run(
            strategy=cls(),
            bars=bars,
            instruments=instruments,
            timeframe=bars[0].timeframe,
            initial_capital=capital,
            params=merged_params,
            slippage_bps=slippage,
        )

        if result.status == "failed":
            console.print(f"[red]Backtest failed: {result.error}[/red]")
            raise typer.Exit(1)

        # Print metrics table
        m = result.metrics
        table = Table(title=f"Backtest Results — {strategy}")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")
        rows = [
            ("Total Return", f"{m.get('total_return_pct', 0):.2f}%"),
            ("Total PnL", f"₹{m.get('total_pnl', 0):,.2f}"),
            ("CAGR", f"{m.get('cagr_pct', 0):.2f}%"),
            ("Sharpe Ratio", f"{m.get('sharpe_ratio', 0):.3f}"),
            ("Sortino Ratio", f"{m.get('sortino_ratio', 0):.3f}"),
            ("Max Drawdown", f"₹{m.get('max_drawdown', 0):,.2f} ({m.get('max_drawdown_pct', 0):.2f}%)"),
            ("Trades", str(m.get("trade_count", 0))),
            ("Win Rate", f"{m.get('win_rate_pct', 0):.2f}%"),
            ("Profit Factor", str(m.get("profit_factor", 0))),
            ("Expectancy", f"₹{m.get('expectancy', 0):,.2f}"),
        ]
        for label, value in rows:
            table.add_row(label, value)
        console.print(table)
        console.print(f"\nRun ID: [dim]{result.run_id}[/dim]")

    asyncio.run(_run())
