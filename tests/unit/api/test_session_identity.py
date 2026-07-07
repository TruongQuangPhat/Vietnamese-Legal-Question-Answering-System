from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.api.session_identity import resolve_session_identity
from src.api.settings import AppSettings


def test_session_identity_disabled_returns_legacy_owner() -> None:
    settings = AppSettings.from_env({"LEGAL_QA_AUTH_ENABLED": "false"})
    request = SimpleNamespace(headers={})

    identity = resolve_session_identity(request=request, settings=settings)

    assert identity.owner_id is None


def test_session_identity_enabled_derives_stable_owner_id() -> None:
    settings = AppSettings.from_env(
        {
            "LEGAL_QA_AUTH_ENABLED": "true",
            "LEGAL_QA_SESSION_SECRET": "unit-test-secret",
        }
    )
    first_request = SimpleNamespace(headers={"X-Legal-QA-Session": "session-a"})
    second_request = SimpleNamespace(headers={"X-Legal-QA-Session": "session-a"})
    other_request = SimpleNamespace(headers={"X-Legal-QA-Session": "session-b"})

    first = resolve_session_identity(request=first_request, settings=settings)
    second = resolve_session_identity(request=second_request, settings=settings)
    other = resolve_session_identity(request=other_request, settings=settings)

    assert first.owner_id is not None
    assert first.owner_id.startswith("session:")
    assert first.owner_id == second.owner_id
    assert first.owner_id != other.owner_id


def test_session_identity_enabled_rejects_missing_session_token() -> None:
    settings = AppSettings.from_env(
        {
            "LEGAL_QA_AUTH_ENABLED": "true",
            "LEGAL_QA_SESSION_SECRET": "unit-test-secret",
        }
    )
    request = SimpleNamespace(headers={})

    with pytest.raises(HTTPException) as exc_info:
        resolve_session_identity(request=request, settings=settings)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Missing session token."
