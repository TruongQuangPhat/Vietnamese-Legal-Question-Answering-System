"""OpenRouter non-secret configuration and environment resolution."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OPENROUTER_CONFIG = REPO_ROOT / "configs/llm/openrouter.yml"

FALLBACK_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
FALLBACK_OPENROUTER_MODEL = "google/gemini-2.5-flash"
FALLBACK_OPENROUTER_DEV_MODEL = "google/gemini-2.5-flash-lite"


class OpenRouterConfig(BaseModel):
    """Validated non-secret OpenRouter defaults loaded from YAML."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["openrouter"] = "openrouter"
    base_url: str = Field(..., min_length=1)
    default_model: str = Field(..., min_length=1)
    dev_model: str = Field(..., min_length=1)

    @field_validator("base_url", "default_model", "dev_model")
    @classmethod
    def normalize_non_blank(cls, value: str) -> str:
        """Trim non-secret configuration values and reject blanks."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("OpenRouter configuration values must not be blank")
        return stripped


class OpenRouterRuntimeSettings(BaseModel):
    """Resolved non-secret OpenRouter runtime settings.

    The API key is intentionally absent so representations and serialized
    settings cannot expose credentials.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["openrouter"] = "openrouter"
    base_url: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)


def load_project_dotenv(path: Path | None = None) -> bool:
    """Load the project ``.env`` without overriding exported environment values."""
    dotenv_path = path or REPO_ROOT / ".env"
    return load_dotenv(dotenv_path=dotenv_path, override=False)


def load_openrouter_config(
    path: Path = DEFAULT_OPENROUTER_CONFIG,
) -> OpenRouterConfig:
    """Load validated non-secret OpenRouter defaults from YAML.

    Raises:
        OSError: If the configuration file cannot be read.
        ValueError: If the YAML root is not an object.
        yaml.YAMLError: If the YAML is malformed.
        ValidationError: If fields are missing, invalid, or include secrets.
    """
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("OpenRouter config root must be a YAML object")
    return OpenRouterConfig.model_validate(payload)


def resolve_openrouter_settings(
    *,
    cli_model: str | None = None,
    config_path: Path = DEFAULT_OPENROUTER_CONFIG,
    environ: Mapping[str, str] | None = None,
) -> OpenRouterRuntimeSettings:
    """Resolve non-secret OpenRouter settings using CLI, env, config, fallback."""
    environment = os.environ if environ is None else environ
    try:
        config = load_openrouter_config(config_path)
    except (OSError, UnicodeError, yaml.YAMLError, ValidationError, ValueError):
        config = None

    model = (
        _non_blank(cli_model)
        or _non_blank(environment.get("OPENROUTER_MODEL"))
        or (config.default_model if config is not None else None)
        or FALLBACK_OPENROUTER_MODEL
    )
    base_url = (
        _non_blank(environment.get("OPENROUTER_BASE_URL"))
        or (config.base_url if config is not None else None)
        or FALLBACK_OPENROUTER_BASE_URL
    )
    return OpenRouterRuntimeSettings(
        base_url=base_url.rstrip("/"),
        model=model,
    )


def _non_blank(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
