from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.api.dependencies import clear_legal_qa_service_cache, get_legal_qa_service
from src.api.schemas import LegalQARequest
from src.api.settings import AppSettings, RuntimeConfigurationError, get_settings
from src.services.legal_qa_workflow import (
    DEFAULT_LLM_CONFIG_PATH,
    DEFAULT_RETRIEVAL_CONFIG_PATH,
    LegalQAServiceMode,
)

REAL_SERVICE_TEST_ENV_VARS = (
    "LEGAL_QA_QDRANT_URL",
    "LEGAL_QA_COLLECTION_NAME",
    "LEGAL_QA_QDRANT_API_KEY",
    "QDRANT_URL",
    "QDRANT_COLLECTION",
    "QDRANT_API_KEY",
    "OPENROUTER_API_KEY",
    "OPENROUTER_MODEL",
)


def test_settings_default_to_local_fake_mode() -> None:
    settings = AppSettings.from_env({})

    assert settings.app_env == "local"
    assert settings.log_level == "INFO"
    assert settings.cors_allowed_origins == ["http://localhost:3000"]
    assert settings.legal_qa_service_mode == LegalQAServiceMode.FAKE
    assert settings.legal_qa_rate_limit_enabled is False
    assert settings.legal_qa_rate_limit_requests == 10
    assert settings.legal_qa_rate_limit_window_seconds == 60
    assert settings.runtime_configuration_issues() == ()


def test_default_pytest_environment_is_isolated_from_real_service_settings() -> None:
    if os.environ.get("LEGAL_QA_ALLOW_REAL_TESTS") == "1":
        pytest.skip("real-service test opt-in is enabled")

    assert os.environ["LEGAL_QA_SERVICE_MODE"] == "fake"
    for name in REAL_SERVICE_TEST_ENV_VARS:
        assert name not in os.environ


def test_settings_default_config_paths_exist() -> None:
    settings = AppSettings.from_env({})

    assert settings.legal_qa_retrieval_config == DEFAULT_RETRIEVAL_CONFIG_PATH
    assert settings.legal_qa_retrieval_config.is_file()
    assert settings.legal_qa_llm_config == DEFAULT_LLM_CONFIG_PATH
    assert settings.legal_qa_llm_config.is_file()


def test_settings_parse_cors_allowed_origins() -> None:
    settings = AppSettings.from_env(
        {"CORS_ALLOWED_ORIGINS": ("http://localhost:3000, http://localhost:5173,, ")}
    )

    assert settings.cors_allowed_origins == [
        "http://localhost:3000",
        "http://localhost:5173",
    ]


def test_settings_parse_cors_allowed_origins_json_array() -> None:
    settings = AppSettings.from_env(
        {"CORS_ALLOWED_ORIGINS": ('["https://vnlaw.example", "https://preview.vnlaw.example"]')}
    )

    assert settings.cors_allowed_origins == [
        "https://vnlaw.example",
        "https://preview.vnlaw.example",
    ]


def test_settings_parse_rate_limit_configuration() -> None:
    settings = AppSettings.from_env(
        {
            "LEGAL_QA_RATE_LIMIT_ENABLED": "true",
            "LEGAL_QA_RATE_LIMIT_REQUESTS": "2",
            "LEGAL_QA_RATE_LIMIT_WINDOW_SECONDS": "30",
        }
    )

    assert settings.legal_qa_rate_limit_enabled is True
    assert settings.legal_qa_rate_limit_requests == 2
    assert settings.legal_qa_rate_limit_window_seconds == 30


def test_settings_rate_limit_blank_values_use_defaults() -> None:
    settings = AppSettings.from_env(
        {
            "LEGAL_QA_RATE_LIMIT_ENABLED": " ",
            "LEGAL_QA_RATE_LIMIT_REQUESTS": " ",
            "LEGAL_QA_RATE_LIMIT_WINDOW_SECONDS": " ",
        }
    )

    assert settings.legal_qa_rate_limit_enabled is False
    assert settings.legal_qa_rate_limit_requests == 10
    assert settings.legal_qa_rate_limit_window_seconds == 60


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("LEGAL_QA_RATE_LIMIT_ENABLED", "maybe", "LEGAL_QA_RATE_LIMIT_ENABLED"),
        ("LEGAL_QA_RATE_LIMIT_REQUESTS", "0", "LEGAL_QA_RATE_LIMIT_REQUESTS"),
        ("LEGAL_QA_RATE_LIMIT_REQUESTS", "1.5", "LEGAL_QA_RATE_LIMIT_REQUESTS"),
        ("LEGAL_QA_RATE_LIMIT_REQUESTS", "not-an-int", "LEGAL_QA_RATE_LIMIT_REQUESTS"),
        (
            "LEGAL_QA_RATE_LIMIT_WINDOW_SECONDS",
            "-1",
            "LEGAL_QA_RATE_LIMIT_WINDOW_SECONDS",
        ),
        (
            "LEGAL_QA_RATE_LIMIT_WINDOW_SECONDS",
            "not-an-int",
            "LEGAL_QA_RATE_LIMIT_WINDOW_SECONDS",
        ),
    ],
)
def test_settings_reject_invalid_rate_limit_configuration(
    name: str,
    value: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        AppSettings.from_env({name: value})


@pytest.mark.parametrize(
    "raw_value",
    [
        '["https://vnlaw.example"',
        '{"origin":"https://vnlaw.example"}',
        '["https://vnlaw.example", 1]',
        "[]",
    ],
)
def test_settings_reject_invalid_cors_json(raw_value: str) -> None:
    with pytest.raises(ValueError, match="CORS_ALLOWED_ORIGINS"):
        AppSettings.from_env({"CORS_ALLOWED_ORIGINS": raw_value})


def test_settings_convert_to_legal_qa_runtime_settings() -> None:
    settings = AppSettings.from_env(
        {
            "LEGAL_QA_SERVICE_MODE": "real",
            "LEGAL_QA_RETRIEVAL_CONFIG": "configs/retrieval/custom.yml",
            "LEGAL_QA_CHUNKS_PATH": "tmp/chunks.jsonl",
            "LEGAL_QA_LLM_CONFIG": "configs/llm/custom.yml",
            "LEGAL_QA_COLLECTION_NAME": "custom_collection",
            "LEGAL_QA_QDRANT_URL": "http://localhost:6333",
            "QDRANT_API_KEY": "qdrant-test-secret",
            "OPENROUTER_API_KEY": "openrouter-test-secret",
            "LEGAL_QA_DEVICE": "cpu",
            "LEGAL_QA_MODEL": "google/gemini-2.5-flash",
        }
    )

    runtime_settings = settings.to_legal_qa_runtime_settings()

    assert runtime_settings.service_mode == LegalQAServiceMode.REAL
    assert runtime_settings.retrieval_config_path == Path("configs/retrieval/custom.yml")
    assert runtime_settings.chunks_path == Path("tmp/chunks.jsonl")
    assert runtime_settings.llm_config_path == Path("configs/llm/custom.yml")
    assert runtime_settings.collection_name == "custom_collection"
    assert runtime_settings.qdrant_url == "http://localhost:6333"
    assert runtime_settings.qdrant_api_key == "qdrant-test-secret"
    assert runtime_settings.device == "cpu"
    assert runtime_settings.model == "google/gemini-2.5-flash"


def test_settings_load_dotenv_with_process_environment_precedence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "LEGAL_QA_SERVICE_MODE=real\n"
        "QDRANT_URL=http://dotenv-qdrant:6333\n"
        "QDRANT_COLLECTION=dotenv_collection\n"
        "OPENROUTER_API_KEY=dotenv-secret\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LEGAL_QA_SERVICE_MODE", "fake")

    settings = AppSettings.from_env(dotenv_path=dotenv_path)

    assert settings.legal_qa_service_mode == LegalQAServiceMode.FAKE
    assert settings.legal_qa_qdrant_url == "http://dotenv-qdrant:6333"
    assert settings.legal_qa_collection_name == "dotenv_collection"
    assert settings.openrouter_api_key is not None
    assert str(settings.openrouter_api_key) == "**********"


def test_fake_mode_does_not_require_real_runtime_configuration(tmp_path: Path) -> None:
    settings = AppSettings.from_env(
        {
            "LEGAL_QA_SERVICE_MODE": "fake",
            "LEGAL_QA_RETRIEVAL_CONFIG": str(tmp_path / "missing-retrieval.yml"),
            "LEGAL_QA_CHUNKS_PATH": str(tmp_path / "missing-chunks.jsonl"),
            "LEGAL_QA_LLM_CONFIG": str(tmp_path / "missing-llm.yml"),
        }
    )

    settings.validate_runtime_configuration()
    assert settings.runtime_configuration_issues() == ()


def test_real_mode_reports_safe_missing_configuration_codes(tmp_path: Path) -> None:
    settings = AppSettings.from_env(
        {
            "LEGAL_QA_SERVICE_MODE": "real",
            "LEGAL_QA_RETRIEVAL_CONFIG": str(tmp_path / "missing-retrieval.yml"),
            "LEGAL_QA_CHUNKS_PATH": str(tmp_path / "missing-chunks.jsonl"),
            "LEGAL_QA_LLM_CONFIG": str(tmp_path / "missing-llm.yml"),
        }
    )

    with pytest.raises(RuntimeConfigurationError) as exc_info:
        settings.validate_runtime_configuration()

    message = str(exc_info.value)
    assert "missing_qdrant_url" in message
    assert "missing_qdrant_collection" in message
    assert "missing_openrouter_api_key" in message
    assert "missing_retrieval_config" in message
    assert "missing_llm_config" in message
    assert "missing_legal_chunks" in message
    assert "secret" not in message


def test_real_mode_accepts_required_configuration_without_external_calls(
    tmp_path: Path,
) -> None:
    retrieval_config = tmp_path / "retrieval.yml"
    chunks = tmp_path / "chunks.jsonl"
    llm_config = tmp_path / "llm.yml"
    for path in (retrieval_config, chunks, llm_config):
        path.touch()
    settings = AppSettings.from_env(
        {
            "LEGAL_QA_SERVICE_MODE": "real",
            "QDRANT_URL": "http://qdrant:6333",
            "QDRANT_COLLECTION": "legal_chunks",
            "QDRANT_API_KEY": "qdrant-secret-value",
            "OPENROUTER_API_KEY": "openrouter-secret-value",
            "LEGAL_QA_RETRIEVAL_CONFIG": str(retrieval_config),
            "LEGAL_QA_CHUNKS_PATH": str(chunks),
            "LEGAL_QA_LLM_CONFIG": str(llm_config),
        }
    )

    settings.validate_runtime_configuration()

    assert settings.runtime_configuration_issues() == ()
    assert "qdrant-secret-value" not in repr(settings)
    assert "openrouter-secret-value" not in repr(settings)


async def test_dependency_provider_uses_settings_default_fake_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LEGAL_QA_SERVICE_MODE", raising=False)
    get_settings.cache_clear()
    clear_legal_qa_service_cache()

    service = await get_legal_qa_service()

    response = service.answer(LegalQARequest(question="Câu hỏi hợp lệ?"))
    assert response.decision == "answered"
    assert response.metadata.model == "stub"


async def test_dependency_provider_rejects_real_mode_before_workflow_construction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = AppSettings.from_env(
        {
            "LEGAL_QA_SERVICE_MODE": "real",
            "OPENROUTER_API_KEY": "must-not-appear",
            "LEGAL_QA_RETRIEVAL_CONFIG": str(tmp_path / "missing-retrieval.yml"),
            "LEGAL_QA_CHUNKS_PATH": str(tmp_path / "missing-chunks.jsonl"),
            "LEGAL_QA_LLM_CONFIG": str(tmp_path / "missing-llm.yml"),
        }
    )
    builder_called = False

    def fail_if_called(*args, **kwargs):
        nonlocal builder_called
        builder_called = True
        raise AssertionError("workflow builder must not run")

    monkeypatch.setattr("src.api.dependencies.get_settings", lambda: settings)
    monkeypatch.setattr("src.api.dependencies.build_legal_qa_service", fail_if_called)
    clear_legal_qa_service_cache()

    with pytest.raises(RuntimeConfigurationError) as exc_info:
        await get_legal_qa_service()

    assert builder_called is False
    assert "must-not-appear" not in str(exc_info.value)
