from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Application
    app_env: str = "development"
    app_port: int = 8000
    app_base_url: str = "http://localhost:8000"

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/xillion.db"

    # Auth
    app_secret_key: str = "change-me-in-production"
    session_lifetime_hours: int = 8
    encryption_key: str = ""

    # Brokers
    zerodha_primary_api_key: str = ""
    zerodha_primary_api_secret: str = ""
    zerodha_primary_user_id: str = ""
    zerodha_primary_password: str = ""
    zerodha_primary_totp_secret: str = ""

    # Notifications
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_from: str = ""

    # Compliance
    app_bind_ip: str = ""
    # CP13: automation-platform-spec/10-RISK-ENGINE.md §10.3 -- SEBI's algo
    # threshold is <10 orders/sec. Cap normal throttling at 7 (soft, orders
    # rejected past this); hitting the 9/sec hard ceiling is treated as a
    # runaway-loop signal (kill switch + P0), not just throttled -- "a loop
    # that generates 9 orders/second will generate 9,000."
    ops_limit_per_second: int = 7
    ops_burst_ceiling: int = 9

    # Risk defaults
    default_account_daily_loss_pct: float = 3.0
    default_per_strategy_daily_loss_pct: float = 2.0
    default_max_open_positions: int = 10
    default_max_orders_per_day: int = 50
    default_max_qty_per_order: int = 10_000
    default_max_notional_per_order: float = 2_000_000.0

    # Plugin paths
    strategies_dir: str = "./strategies"
    brokers_dir: str = "./brokers"
    data_providers_dir: str = "./data_providers"

    # AI confidence hook (CP8) -- empty means disabled, alert mode behaves
    # exactly as before this existed. Points at prosper-engine's /confidence
    # endpoint when configured.
    ai_confidence_url: str = ""
    # 90s: this call runs as a background task (see _fetch_and_store_confidence
    # in strategy_engine.py), never in an alert's critical path, so there's no
    # pressure to keep the timeout tight. A local "thinking" model measured
    # for real against qwen3:8b via Ollama took 30-60s+ per call -- a hosted
    # cloud API would answer far faster, but this has to work for whichever
    # backend prosper-engine's tenant config actually points at.
    ai_confidence_timeout_seconds: float = 90.0

    class Config:
        env_file = ".env"
        case_sensitive = False

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    def get_sync_database_url(self) -> str:
        """Return a sync-compatible DB URL for Alembic migrations."""
        url = self.database_url
        url = url.replace("+aiosqlite", "")
        url = url.replace("+asyncpg", "")
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://")
        return url

    def get_async_database_url(self) -> str:
        """Return an async-driver URL for the running app."""
        url = self.database_url
        if url.startswith("sqlite://") and "+aiosqlite" not in url:
            url = url.replace("sqlite://", "sqlite+aiosqlite://")
        elif url.startswith("postgresql://") and "+asyncpg" not in url:
            url = url.replace("postgresql://", "postgresql+asyncpg://")
        elif url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://")
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
