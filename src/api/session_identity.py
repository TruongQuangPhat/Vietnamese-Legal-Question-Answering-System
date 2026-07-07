"""Session identity resolution for conversation ownership."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from src.api.settings import AppSettings, get_settings


@dataclass(frozen=True)
class SessionIdentity:
    """Resolved caller identity for owner-scoped conversation operations."""

    owner_id: str | None


async def get_session_identity(request: Request) -> SessionIdentity:
    """Return the current conversation owner identity.

    Auth is disabled by default for compatibility. When enabled, the configured
    session header must be present and is converted to an opaque owner id with
    HMAC-SHA256. The raw token is never stored by the API.

    Raises:
        HTTPException: If auth is enabled and the session token is missing or
            session configuration is invalid.
    """
    settings = get_settings()
    return resolve_session_identity(request=request, settings=settings)


def resolve_session_identity(*, request: Request, settings: AppSettings) -> SessionIdentity:
    """Resolve session identity from a FastAPI request and runtime settings."""
    if not settings.legal_qa_auth_enabled:
        return SessionIdentity(owner_id=None)

    settings.validate_auth_configuration()
    token = request.headers.get(settings.legal_qa_session_header)
    if token is None or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing session token.",
        )
    session_secret = settings.legal_qa_session_secret
    if session_secret is None:
        settings.validate_auth_configuration()
        raise AssertionError("unreachable missing session secret after validation")
    return SessionIdentity(
        owner_id=_owner_id_from_token(
            token=token.strip(),
            secret=session_secret.get_secret_value(),
        )
    )


def _owner_id_from_token(*, token: str, secret: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"session:{digest}"
