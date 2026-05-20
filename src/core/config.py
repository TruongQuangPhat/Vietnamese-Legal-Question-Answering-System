"""Application configuration via Pydantic Settings.

This module loads configuration from environment variables and .env files.
All configuration values are strongly typed and validated at startup.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Attributes:
        crawler_rate_limit_seconds: Delay between requests per host.
        crawler_max_concurrency: Maximum concurrent crawl tasks.
        crawler_max_retries: Maximum retry attempts for failed requests.
        crawler_timeout_seconds: Request timeout in seconds.
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR).
        log_format: Log format (json or text).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Crawler configuration
    crawler_rate_limit_seconds: float = 2.0
    crawler_max_concurrency: int = 2
    crawler_max_retries: int = 3
    crawler_timeout_seconds: int = 60

    # Logging configuration
    log_level: str = "INFO"
    log_format: str = "json"

    @property
    def trusted_domain(self) -> str:
        """The trusted domain for crawling."""
        return "thuvienphapluat.vn"


@lru_cache
def get_settings() -> Settings:
    """Get cached Settings instance.

    Returns:
        Global Settings instance.
    """
    return Settings()
