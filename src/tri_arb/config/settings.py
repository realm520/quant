"""Application settings using pydantic-settings."""

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application settings
    app_name: str = Field(default="tri-arb", description="Application name")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", description="Logging level"
    )
    environment: Literal["development", "testing", "production"] = Field(
        default="development", description="Runtime environment"
    )

    # Database settings
    db_path: str = Field(default="tri_arb.db", description="SQLite database file path")
    db_pool_size: int = Field(
        default=5, ge=1, le=20, description="Database connection pool size"
    )
    db_timeout: float = Field(
        default=5.0, gt=0, description="Database connection timeout (seconds)"
    )

    # Cache settings
    cache_ttl: int = Field(default=60, ge=1, description="Cache TTL in seconds")
    cache_max_size: int = Field(default=1000, ge=10, description="Maximum cache size")

    # Performance settings
    max_concurrent_requests: int = Field(
        default=10, ge=1, le=100, description="Maximum concurrent requests"
    )
    request_timeout: int = Field(
        default=30, ge=1, description="HTTP request timeout (seconds)"
    )

    # Monitoring settings
    metrics_port: int = Field(
        default=9090, ge=1024, le=65535, description="Prometheus metrics port"
    )
    health_check_interval: int = Field(
        default=30, ge=1, description="Health check interval (seconds)"
    )
    enable_metrics: bool = Field(default=True, description="Enable Prometheus metrics")

    # Exchange settings (placeholder)
    binance_enabled: bool = Field(default=False, description="Enable Binance exchange")
    okx_enabled: bool = Field(default=False, description="Enable OKX exchange")

    # XT Exchange Configuration
    # Note: Environment variables are auto-mapped (case_sensitive=False)
    # xt_api_key -> XT_API_KEY, xt_api_secret -> XT_API_SECRET
    xt_api_key: str = Field(default="", description="XT API key")
    xt_api_secret: str = Field(default="", description="XT API secret")


# Global settings instance
settings = Settings()
