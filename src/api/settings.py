"""Runtime settings for the VnLaw-QA API."""

from __future__ import annotations

import os
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.services.legal_qa_workflow import (
    DEFAULT_CHUNKS_PATH,
    DEFAULT_LLM_CONFIG_PATH,
    DEFAULT_RETRIEVAL_CONFIG_PATH,
    LegalQARuntimeSettings,
    LegalQAServiceMode,
)

DEFAULT_CORS_ALLOWED_ORIGINS = ["http://localhost:3000"]


class AppSettings(BaseSettings):
    """Environment-backed settings for the API runtime.

    The default service mode is fake so application startup and routine tests do
    not construct Qdrant, embedding, reranking, or LLM provider clients.
    """

    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    app_env: str = "local"
    log_level: str = "INFO"
    cors_allowed_origins: list[str] = Field(
        default_factory=lambda: list(DEFAULT_CORS_ALLOWED_ORIGINS)
    )
    legal_qa_service_mode: LegalQAServiceMode = LegalQAServiceMode.FAKE
    legal_qa_retrieval_config: Path = DEFAULT_RETRIEVAL_CONFIG_PATH
    legal_qa_chunks_path: Path = DEFAULT_CHUNKS_PATH
    legal_qa_llm_config: Path = DEFAULT_LLM_CONFIG_PATH
    legal_qa_collection_name: str | None = None
    legal_qa_qdrant_url: str | None = None
    legal_qa_device: str | None = None
    legal_qa_model: str | None = None

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> AppSettings:
        """Build API settings from environment variables.

        Args:
            environ: Optional environment mapping for tests.

        Returns:
            API settings with fake Legal QA mode unless explicitly configured.
        """
        env = os.environ if environ is None else environ
        return cls(
            app_env=_non_blank(env.get("APP_ENV")) or "local",
            log_level=(_non_blank(env.get("LOG_LEVEL")) or "INFO").upper(),
            cors_allowed_origins=_parse_csv(
                env.get("CORS_ALLOWED_ORIGINS"),
                default=DEFAULT_CORS_ALLOWED_ORIGINS,
            ),
            legal_qa_service_mode=_service_mode(env.get("LEGAL_QA_SERVICE_MODE")),
            legal_qa_retrieval_config=Path(
                env.get("LEGAL_QA_RETRIEVAL_CONFIG", str(DEFAULT_RETRIEVAL_CONFIG_PATH))
            ),
            legal_qa_chunks_path=Path(env.get("LEGAL_QA_CHUNKS_PATH", str(DEFAULT_CHUNKS_PATH))),
            legal_qa_llm_config=Path(env.get("LEGAL_QA_LLM_CONFIG", str(DEFAULT_LLM_CONFIG_PATH))),
            legal_qa_collection_name=_non_blank(env.get("LEGAL_QA_COLLECTION_NAME")),
            legal_qa_qdrant_url=_non_blank(env.get("LEGAL_QA_QDRANT_URL")),
            legal_qa_device=_non_blank(env.get("LEGAL_QA_DEVICE")),
            legal_qa_model=_non_blank(env.get("LEGAL_QA_MODEL")),
        )

    def to_legal_qa_runtime_settings(self) -> LegalQARuntimeSettings:
        """Convert API settings to the Legal QA service runtime contract."""
        return LegalQARuntimeSettings(
            service_mode=self.legal_qa_service_mode,
            retrieval_config_path=self.legal_qa_retrieval_config,
            chunks_path=self.legal_qa_chunks_path,
            llm_config_path=self.legal_qa_llm_config,
            collection_name=self.legal_qa_collection_name,
            qdrant_url=self.legal_qa_qdrant_url,
            device=self.legal_qa_device,
            model=self.legal_qa_model,
        )


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return cached API runtime settings."""
    return AppSettings.from_env()


def _parse_csv(raw_value: str | None, *, default: list[str]) -> list[str]:
    value = _non_blank(raw_value)
    if value is None:
        return list(default)
    parsed = [item.strip() for item in value.split(",") if item.strip()]
    return parsed or list(default)


def _service_mode(raw_value: str | None) -> LegalQAServiceMode:
    value = _non_blank(raw_value)
    if value is None:
        return LegalQAServiceMode.FAKE
    try:
        return LegalQAServiceMode(value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in LegalQAServiceMode)
        raise ValueError(f"LEGAL_QA_SERVICE_MODE must be one of: {allowed}") from exc


def _non_blank(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
