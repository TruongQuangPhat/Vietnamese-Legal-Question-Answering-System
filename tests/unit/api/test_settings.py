from __future__ import annotations

from pathlib import Path

from src.api.dependencies import get_legal_qa_service
from src.api.schemas import LegalQARequest
from src.api.settings import AppSettings, get_settings
from src.services.legal_qa_workflow import LegalQAServiceMode


def test_settings_default_to_local_fake_mode() -> None:
    settings = AppSettings.from_env({})

    assert settings.app_env == "local"
    assert settings.log_level == "INFO"
    assert settings.cors_allowed_origins == ["http://localhost:3000"]
    assert settings.legal_qa_service_mode == LegalQAServiceMode.FAKE


def test_settings_parse_cors_allowed_origins() -> None:
    settings = AppSettings.from_env(
        {"CORS_ALLOWED_ORIGINS": ("http://localhost:3000, http://localhost:5173,, ")}
    )

    assert settings.cors_allowed_origins == [
        "http://localhost:3000",
        "http://localhost:5173",
    ]


def test_settings_convert_to_legal_qa_runtime_settings() -> None:
    settings = AppSettings.from_env(
        {
            "LEGAL_QA_SERVICE_MODE": "real",
            "LEGAL_QA_RETRIEVAL_CONFIG": "configs/retrieval/custom.yml",
            "LEGAL_QA_CHUNKS_PATH": "tmp/chunks.jsonl",
            "LEGAL_QA_LLM_CONFIG": "configs/llm/custom.yml",
            "LEGAL_QA_COLLECTION_NAME": "custom_collection",
            "LEGAL_QA_QDRANT_URL": "http://localhost:6333",
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
    assert runtime_settings.device == "cpu"
    assert runtime_settings.model == "google/gemini-2.5-flash"


def test_dependency_provider_uses_settings_default_fake_mode(monkeypatch) -> None:
    monkeypatch.delenv("LEGAL_QA_SERVICE_MODE", raising=False)
    get_settings.cache_clear()
    get_legal_qa_service.cache_clear()

    service = get_legal_qa_service()

    response = service.answer(LegalQARequest(question="Câu hỏi hợp lệ?"))
    assert response.decision == "answered"
    assert response.metadata.model == "stub"
