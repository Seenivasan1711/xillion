import os
import pytest

# Use an in-memory SQLite for tests
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key")
os.environ.setdefault("ENCRYPTION_KEY", "")
os.environ.setdefault("STRATEGIES_DIR", "./strategies")
os.environ.setdefault("BROKERS_DIR", "./brokers")
