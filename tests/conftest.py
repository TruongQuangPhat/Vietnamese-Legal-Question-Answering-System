"""Shared pytest safety fixtures.

Routine tests must not inherit a developer's local real-mode `.env` or shell
environment. Real-service tests are opt-in only through
`LEGAL_QA_ALLOW_REAL_TESTS=1`.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from src.api.dependencies import (
    clear_conversation_service_cache,
    clear_legal_qa_service_cache,
)
from src.api.settings import get_settings

_REAL_TEST_OPT_IN = "LEGAL_QA_ALLOW_REAL_TESTS"
_REAL_SERVICE_ENV_VARS = (
    "LEGAL_QA_SERVICE_MODE",
    "LEGAL_QA_QDRANT_URL",
    "LEGAL_QA_COLLECTION_NAME",
    "LEGAL_QA_QDRANT_API_KEY",
    "LEGAL_QA_RETRIEVAL_CONFIG",
    "LEGAL_QA_CHUNKS_PATH",
    "LEGAL_QA_LLM_CONFIG",
    "LEGAL_QA_DEVICE",
    "LEGAL_QA_MODEL",
    "QDRANT_URL",
    "QDRANT_COLLECTION",
    "QDRANT_API_KEY",
    "OPENROUTER_API_KEY",
    "OPENROUTER_MODEL",
    "OPENROUTER_BASE_URL",
)


def _real_tests_enabled() -> bool:
    return os.environ.get(_REAL_TEST_OPT_IN) == "1"


def _force_safe_test_environment() -> None:
    if _real_tests_enabled():
        return
    for name in _REAL_SERVICE_ENV_VARS:
        os.environ.pop(name, None)
    os.environ["LEGAL_QA_SERVICE_MODE"] = "fake"


_force_safe_test_environment()


@pytest.fixture(autouse=True)
def isolate_real_service_environment() -> Iterator[None]:
    """Keep default tests in fake mode and clear cached runtime services."""
    _force_safe_test_environment()
    get_settings.cache_clear()
    clear_legal_qa_service_cache()
    clear_conversation_service_cache()
    yield
    _force_safe_test_environment()
    get_settings.cache_clear()
    clear_legal_qa_service_cache()
    clear_conversation_service_cache()
