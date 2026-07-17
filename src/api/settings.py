"""Runtime settings for the VnLaw-QA API."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.services.legal_qa_workflow import (
    DEFAULT_CHUNKS_PATH,
    DEFAULT_LLM_CONFIG_PATH,
    DEFAULT_RETRIEVAL_CONFIG_PATH,
    LegalQARuntimeSettings,
    LegalQAServiceMode,
)

DEFAULT_CORS_ALLOWED_ORIGINS = ["http://localhost:3000"]
DEFAULT_DOTENV_PATH = Path(".env")
DEFAULT_RATE_LIMIT_REQUESTS = 10
DEFAULT_RATE_LIMIT_WINDOW_SECONDS = 60
DEFAULT_ASK_TIMEOUT_SECONDS = 90.0
DEFAULT_RETRIEVAL_TIMEOUT_SECONDS = 60.0
DEFAULT_QUERY_EMBEDDING_TIMEOUT_SECONDS = 45.0
DEFAULT_QDRANT_TIMEOUT_SECONDS = 30.0
DEFAULT_LLM_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_TOP_K = 10
MIN_SESSION_SECRET_LENGTH = 16
WEAK_SESSION_SECRET_PLACEHOLDERS = {
    "changeme",
    "change-me",
    "change_me",
    "replace-me",
    "replace_me",
    "secret",
    "session-secret",
    "test-secret",
    "your-secret",
    "your-session-secret",
    "legal-qa-session-secret",
}


class ConversationStoreMode(StrEnum):
    """Conversation storage backends supported by the API runtime."""

    MEMORY = "memory"
    POSTGRES = "postgres"


class RuntimeConfigurationError(RuntimeError):
    """Raised when the selected API runtime mode is not configured safely."""


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
    qdrant_api_key: SecretStr | None = Field(default=None, repr=False)
    openrouter_api_key: SecretStr | None = Field(default=None, repr=False)
    legal_qa_device: str | None = None
    legal_qa_model: str | None = None
    legal_qa_rate_limit_enabled: bool = False
    legal_qa_rate_limit_requests: int = Field(DEFAULT_RATE_LIMIT_REQUESTS, gt=0)
    legal_qa_rate_limit_window_seconds: int = Field(DEFAULT_RATE_LIMIT_WINDOW_SECONDS, gt=0)
    legal_qa_conversation_store: ConversationStoreMode = ConversationStoreMode.MEMORY
    legal_qa_database_url: SecretStr | None = Field(default=None, repr=False)
    legal_qa_auth_enabled: bool = False
    legal_qa_session_secret: SecretStr | None = Field(default=None, repr=False)
    legal_qa_session_header: str = "X-Legal-QA-Session"
    legal_qa_ask_timeout_seconds: float = Field(DEFAULT_ASK_TIMEOUT_SECONDS, gt=0.0)
    legal_qa_retrieval_timeout_seconds: float = Field(
        DEFAULT_RETRIEVAL_TIMEOUT_SECONDS,
        gt=0.0,
    )
    legal_qa_query_embedding_timeout_seconds: float = Field(
        DEFAULT_QUERY_EMBEDDING_TIMEOUT_SECONDS,
        gt=0.0,
    )
    legal_qa_qdrant_timeout_seconds: float = Field(DEFAULT_QDRANT_TIMEOUT_SECONDS, gt=0.0)
    legal_qa_llm_timeout_seconds: float = Field(DEFAULT_LLM_TIMEOUT_SECONDS, gt=0.0)
    legal_qa_max_top_k: int = Field(DEFAULT_MAX_TOP_K, gt=0)
    legal_qa_reranking_enabled: bool = False

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        dotenv_path: Path = DEFAULT_DOTENV_PATH,
    ) -> AppSettings:
        """Build API settings from environment variables.

        Args:
            environ: Optional complete environment mapping for deterministic
                tests. When omitted, values from ``.env`` are loaded first and
                process environment values override them.
            dotenv_path: Project dotenv path used only when ``environ`` is
                omitted.

        Returns:
            API settings with fake Legal QA mode unless explicitly configured.
        """
        env = _runtime_environment(environ=environ, dotenv_path=dotenv_path)
        return cls(
            app_env=_non_blank(env.get("APP_ENV")) or "local",
            log_level=(_non_blank(env.get("LOG_LEVEL")) or "INFO").upper(),
            cors_allowed_origins=_parse_cors_allowed_origins(
                env.get("CORS_ALLOWED_ORIGINS"),
                default=DEFAULT_CORS_ALLOWED_ORIGINS,
            ),
            legal_qa_service_mode=_service_mode(env.get("LEGAL_QA_SERVICE_MODE")),
            legal_qa_retrieval_config=Path(
                env.get("LEGAL_QA_RETRIEVAL_CONFIG", str(DEFAULT_RETRIEVAL_CONFIG_PATH))
            ),
            legal_qa_chunks_path=Path(env.get("LEGAL_QA_CHUNKS_PATH", str(DEFAULT_CHUNKS_PATH))),
            legal_qa_llm_config=Path(env.get("LEGAL_QA_LLM_CONFIG", str(DEFAULT_LLM_CONFIG_PATH))),
            legal_qa_collection_name=_first_non_blank(
                env,
                "LEGAL_QA_COLLECTION_NAME",
                "QDRANT_COLLECTION",
            ),
            legal_qa_qdrant_url=_first_non_blank(
                env,
                "LEGAL_QA_QDRANT_URL",
                "QDRANT_URL",
            ),
            qdrant_api_key=_secret_from_env(
                env,
                "LEGAL_QA_QDRANT_API_KEY",
                "QDRANT_API_KEY",
            ),
            openrouter_api_key=_secret_from_env(env, "OPENROUTER_API_KEY"),
            legal_qa_device=_non_blank(env.get("LEGAL_QA_DEVICE")),
            legal_qa_model=_first_non_blank(
                env,
                "LEGAL_QA_MODEL",
                "OPENROUTER_MODEL",
            ),
            legal_qa_rate_limit_enabled=_parse_bool(
                env.get("LEGAL_QA_RATE_LIMIT_ENABLED"),
                default=False,
                name="LEGAL_QA_RATE_LIMIT_ENABLED",
            ),
            legal_qa_rate_limit_requests=_parse_positive_int(
                env.get("LEGAL_QA_RATE_LIMIT_REQUESTS"),
                default=DEFAULT_RATE_LIMIT_REQUESTS,
                name="LEGAL_QA_RATE_LIMIT_REQUESTS",
            ),
            legal_qa_rate_limit_window_seconds=_parse_positive_int(
                env.get("LEGAL_QA_RATE_LIMIT_WINDOW_SECONDS"),
                default=DEFAULT_RATE_LIMIT_WINDOW_SECONDS,
                name="LEGAL_QA_RATE_LIMIT_WINDOW_SECONDS",
            ),
            legal_qa_conversation_store=_conversation_store_mode(
                env.get("LEGAL_QA_CONVERSATION_STORE")
            ),
            legal_qa_database_url=_secret_from_env(env, "LEGAL_QA_DATABASE_URL"),
            legal_qa_auth_enabled=_parse_bool(
                env.get("LEGAL_QA_AUTH_ENABLED"),
                default=False,
                name="LEGAL_QA_AUTH_ENABLED",
            ),
            legal_qa_session_secret=_secret_from_env(env, "LEGAL_QA_SESSION_SECRET"),
            legal_qa_session_header=_session_header(env.get("LEGAL_QA_SESSION_HEADER")),
            legal_qa_ask_timeout_seconds=_parse_positive_float(
                env.get("LEGAL_QA_ASK_TIMEOUT_SECONDS"),
                default=DEFAULT_ASK_TIMEOUT_SECONDS,
                name="LEGAL_QA_ASK_TIMEOUT_SECONDS",
            ),
            legal_qa_retrieval_timeout_seconds=_parse_positive_float(
                env.get("LEGAL_QA_RETRIEVAL_TIMEOUT_SECONDS"),
                default=DEFAULT_RETRIEVAL_TIMEOUT_SECONDS,
                name="LEGAL_QA_RETRIEVAL_TIMEOUT_SECONDS",
            ),
            legal_qa_query_embedding_timeout_seconds=_parse_positive_float(
                env.get("LEGAL_QA_QUERY_EMBEDDING_TIMEOUT_SECONDS"),
                default=DEFAULT_QUERY_EMBEDDING_TIMEOUT_SECONDS,
                name="LEGAL_QA_QUERY_EMBEDDING_TIMEOUT_SECONDS",
            ),
            legal_qa_qdrant_timeout_seconds=_parse_positive_float(
                env.get("LEGAL_QA_QDRANT_TIMEOUT_SECONDS"),
                default=DEFAULT_QDRANT_TIMEOUT_SECONDS,
                name="LEGAL_QA_QDRANT_TIMEOUT_SECONDS",
            ),
            legal_qa_llm_timeout_seconds=_parse_positive_float(
                env.get("LEGAL_QA_LLM_TIMEOUT_SECONDS"),
                default=DEFAULT_LLM_TIMEOUT_SECONDS,
                name="LEGAL_QA_LLM_TIMEOUT_SECONDS",
            ),
            legal_qa_max_top_k=_parse_positive_int(
                env.get("LEGAL_QA_MAX_TOP_K"),
                default=DEFAULT_MAX_TOP_K,
                name="LEGAL_QA_MAX_TOP_K",
            ),
            legal_qa_reranking_enabled=_parse_bool(
                env.get("LEGAL_QA_RERANKING_ENABLED"),
                default=False,
                name="LEGAL_QA_RERANKING_ENABLED",
            ),
        )

    def auth_configuration_issues(self) -> tuple[str, ...]:
        """Return safe issue codes for session ownership configuration."""
        if not self.legal_qa_auth_enabled:
            return ()
        if self.legal_qa_session_secret is None:
            return ("missing_session_secret",)
        secret = self.legal_qa_session_secret.get_secret_value()
        if _is_weak_session_secret(secret):
            return ("weak_session_secret",)
        return ()

    def validate_auth_configuration(self) -> None:
        """Reject invalid session ownership configuration.

        Raises:
            RuntimeConfigurationError: If auth is enabled without required
                secret material. The message contains safe issue codes only.
        """
        issues = self.auth_configuration_issues()
        if issues:
            raise RuntimeConfigurationError(
                "Invalid session ownership configuration: " + ", ".join(issues)
            )

    def conversation_configuration_issues(self) -> tuple[str, ...]:
        """Return safe issue codes for conversation storage configuration."""
        issues = list(self.auth_configuration_issues())
        if (
            self.legal_qa_conversation_store == ConversationStoreMode.POSTGRES
            and self.legal_qa_database_url is None
        ):
            issues.append("missing_database_url")
        return tuple(issues)

    def validate_conversation_configuration(self) -> None:
        """Reject invalid conversation storage configuration.

        Raises:
            RuntimeConfigurationError: If the selected conversation storage
                backend lacks required settings. The message contains safe issue
                codes only and never includes credentials.
        """
        issues = self.conversation_configuration_issues()
        if issues:
            raise RuntimeConfigurationError(
                "Invalid conversation storage configuration: " + ", ".join(issues)
            )

    def runtime_configuration_issues(self) -> tuple[str, ...]:
        """Return safe issue codes for the selected runtime mode.

        The check performs local value and file-existence validation only. It
        does not construct clients, load an embedding model, contact Qdrant, or
        call an LLM provider.
        """
        issues = list(self.conversation_configuration_issues())
        if self.legal_qa_service_mode == LegalQAServiceMode.FAKE:
            return tuple(issues)

        if self.legal_qa_qdrant_url is None:
            issues.append("missing_qdrant_url")
        if self.legal_qa_collection_name is None:
            issues.append("missing_qdrant_collection")
        if self.openrouter_api_key is None:
            issues.append("missing_openrouter_api_key")
        if not self.legal_qa_retrieval_config.is_file():
            issues.append("missing_retrieval_config")
        if not self.legal_qa_llm_config.is_file():
            issues.append("missing_llm_config")
        if not self.legal_qa_chunks_path.is_file():
            issues.append("missing_legal_chunks")
        return tuple(issues)

    def validate_runtime_configuration(self) -> None:
        """Reject an invalid real-mode configuration before client construction.

        Raises:
            RuntimeConfigurationError: If real mode lacks required settings or
                local artifacts. The message contains safe issue codes only.
        """
        issues = self.runtime_configuration_issues()
        if issues:
            raise RuntimeConfigurationError(
                "Invalid Legal QA runtime configuration: " + ", ".join(issues)
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
            qdrant_api_key=(
                self.qdrant_api_key.get_secret_value() if self.qdrant_api_key is not None else None
            ),
            device=self.legal_qa_device,
            model=self.legal_qa_model,
            retrieval_timeout_seconds=self.legal_qa_retrieval_timeout_seconds,
            query_embedding_timeout_seconds=self.legal_qa_query_embedding_timeout_seconds,
            qdrant_timeout_seconds=self.legal_qa_qdrant_timeout_seconds,
            llm_timeout_seconds=self.legal_qa_llm_timeout_seconds,
            reranking_enabled=self.legal_qa_reranking_enabled,
        )


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return cached API runtime settings."""
    return AppSettings.from_env()


def _parse_cors_allowed_origins(raw_value: str | None, *, default: list[str]) -> list[str]:
    """Parse CORS origins from a JSON array or legacy comma-separated value."""
    value = _non_blank(raw_value)
    if value is None:
        return list(default)
    if value.startswith(("[", "{")):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("CORS_ALLOWED_ORIGINS must be a valid JSON array") from exc
        if not isinstance(decoded, list) or not all(isinstance(item, str) for item in decoded):
            raise ValueError("CORS_ALLOWED_ORIGINS must be a JSON array of strings")
        parsed = [item.strip() for item in decoded if item.strip()]
        if not parsed:
            raise ValueError("CORS_ALLOWED_ORIGINS must contain at least one origin")
        return parsed
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


def _conversation_store_mode(raw_value: str | None) -> ConversationStoreMode:
    value = _non_blank(raw_value)
    if value is None:
        return ConversationStoreMode.MEMORY
    try:
        return ConversationStoreMode(value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in ConversationStoreMode)
        raise ValueError(f"LEGAL_QA_CONVERSATION_STORE must be one of: {allowed}") from exc


def _session_header(raw_value: str | None) -> str:
    value = _non_blank(raw_value)
    if value is None:
        return "X-Legal-QA-Session"
    if any(character.isspace() for character in value):
        raise ValueError("LEGAL_QA_SESSION_HEADER must not contain whitespace")
    return value


def _parse_bool(raw_value: str | None, *, default: bool, name: str) -> bool:
    value = _non_blank(raw_value)
    if value is None:
        return default
    normalized = value.casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


def _parse_positive_int(raw_value: str | None, *, default: int, name: str) -> int:
    value = _non_blank(raw_value)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return parsed


def _parse_positive_float(raw_value: str | None, *, default: float, name: str) -> float:
    value = _non_blank(raw_value)
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive number") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be a positive number")
    return parsed


def _non_blank(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _runtime_environment(
    *,
    environ: Mapping[str, str] | None,
    dotenv_path: Path,
) -> Mapping[str, str]:
    if environ is not None:
        return environ
    dotenv_environment = {
        key: value for key, value in dotenv_values(dotenv_path).items() if value is not None
    }
    return {**dotenv_environment, **os.environ}


def _first_non_blank(environment: Mapping[str, str], *names: str) -> str | None:
    for name in names:
        value = _non_blank(environment.get(name))
        if value is not None:
            return value
    return None


def _secret_from_env(environment: Mapping[str, str], *names: str) -> SecretStr | None:
    value = _first_non_blank(environment, *names)
    return SecretStr(value) if value is not None else None


def _is_weak_session_secret(secret: str) -> bool:
    normalized = secret.strip().casefold()
    return len(secret) < MIN_SESSION_SECRET_LENGTH or normalized in WEAK_SESSION_SECRET_PLACEHOLDERS
