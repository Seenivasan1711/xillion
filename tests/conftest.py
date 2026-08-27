import os

# Use an in-memory SQLite for tests
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
# Same for the warehouse DB (bar/bar_coverage/option_chain_snapshot) --
# without this it defaults to a real file (data/backtest_warehouse.db),
# which would leak state across test runs instead of being fresh/isolated
# like the main test DB.
os.environ.setdefault("BACKTEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key")
os.environ.setdefault("ENCRYPTION_KEY", "")
os.environ.setdefault("STRATEGIES_DIR", "./strategies")
os.environ.setdefault("BROKERS_DIR", "./brokers")
