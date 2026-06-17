"""Unit tests for OpenRouter non-secret config and dotenv resolution."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.retrieval.openrouter_config import (
    OpenRouterRuntimeSettings,
    load_openrouter_config,
    load_project_dotenv,
    resolve_openrouter_settings,
)


def test_project_dotenv_loads_api_key_without_printing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The project loader exposes dotenv values without printing credentials."""
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "OPENROUTER_API_KEY=test-openrouter-key\nOPENROUTER_MODEL=dotenv/model\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)

    loaded = load_project_dotenv(dotenv_path)

    assert loaded is True
    assert os.environ["OPENROUTER_API_KEY"] == "test-openrouter-key"
    assert os.environ["OPENROUTER_MODEL"] == "dotenv/model"
    captured = capsys.readouterr()
    assert "test-openrouter-key" not in captured.out
    assert "test-openrouter-key" not in captured.err


def test_project_dotenv_does_not_override_exported_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exported environment values take precedence over project dotenv values."""
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("OPENROUTER_MODEL=dotenv/model\n", encoding="utf-8")
    monkeypatch.setenv("OPENROUTER_MODEL", "exported/model")

    load_project_dotenv(dotenv_path)

    assert os.environ["OPENROUTER_MODEL"] == "exported/model"


def test_cli_model_overrides_environment_and_config(tmp_path: Path) -> None:
    """An explicit CLI model has highest precedence."""
    config_path = _write_config(tmp_path)

    settings = resolve_openrouter_settings(
        cli_model="cli/model",
        config_path=config_path,
        environ={"OPENROUTER_MODEL": "env/model"},
    )

    assert settings.model == "cli/model"


def test_environment_model_overrides_config_default(tmp_path: Path) -> None:
    """Environment model overrides the YAML default when CLI omits model."""
    config_path = _write_config(tmp_path)

    settings = resolve_openrouter_settings(
        config_path=config_path,
        environ={"OPENROUTER_MODEL": "env/model"},
    )

    assert settings.model == "env/model"


def test_config_default_model_used_without_cli_or_environment(tmp_path: Path) -> None:
    """YAML default model is used when higher-priority values are absent."""
    config_path = _write_config(tmp_path)

    settings = resolve_openrouter_settings(config_path=config_path, environ={})

    assert settings.model == "config/model"


def test_environment_base_url_overrides_config(tmp_path: Path) -> None:
    """Environment base URL overrides the YAML default."""
    config_path = _write_config(tmp_path)

    settings = resolve_openrouter_settings(
        config_path=config_path,
        environ={"OPENROUTER_BASE_URL": "https://example-openrouter.test/api/v1/"},
    )

    assert settings.base_url == "https://example-openrouter.test/api/v1"


def test_config_base_url_used_without_environment(tmp_path: Path) -> None:
    """YAML base URL is used when no environment override exists."""
    config_path = _write_config(tmp_path)

    settings = resolve_openrouter_settings(config_path=config_path, environ={})

    assert settings.base_url == "https://config-openrouter.test/api/v1"


def test_openrouter_config_rejects_api_key_field(tmp_path: Path) -> None:
    """Secret fields are forbidden in the non-secret YAML configuration."""
    config_path = _write_config(
        tmp_path,
        extra_line="api_key: test-openrouter-key\n",
    )

    with pytest.raises(ValidationError):
        load_openrouter_config(config_path)


def test_runtime_settings_never_serialize_or_repr_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolved settings have no credential field or credential representation."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    settings = OpenRouterRuntimeSettings(
        base_url="https://example-openrouter.test/api/v1",
        model="test/model",
    )

    assert "api_key" not in settings.model_dump()
    assert "test-openrouter-key" not in repr(settings)
    assert "test-openrouter-key" not in settings.model_dump_json()


def _write_config(tmp_path: Path, *, extra_line: str = "") -> Path:
    path = tmp_path / "openrouter.yml"
    path.write_text(
        "provider: openrouter\n"
        'base_url: "https://config-openrouter.test/api/v1"\n'
        'default_model: "config/model"\n'
        'dev_model: "config/dev-model"\n'
        f"{extra_line}",
        encoding="utf-8",
    )
    return path
