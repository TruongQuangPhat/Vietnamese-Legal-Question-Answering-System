"""In-process request rate limiting for selected public API routes."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from src.api.settings import AppSettings


@dataclass(frozen=True)
class RateLimitPolicy:
    """Fixed-window rate limit configuration."""

    enabled: bool
    requests: int
    window_seconds: int


@dataclass(frozen=True)
class RateLimitDecision:
    """Result of one rate-limit check."""

    allowed: bool
    retry_after_seconds: int | None = None


@dataclass
class _ClientWindow:
    count: int
    reset_at: float


class FixedWindowRateLimiter:
    """Simple single-process fixed-window limiter keyed by client identity.

    This limiter is intentionally local to one application process. It protects
    the current single-instance deployment from simple request bursts, but it is
    not a distributed quota system.
    """

    def __init__(self, policy: RateLimitPolicy) -> None:
        self._policy = policy
        self._windows: dict[str, _ClientWindow] = {}

    @property
    def policy(self) -> RateLimitPolicy:
        """Return immutable limiter policy."""
        return self._policy

    @property
    def active_window_count(self) -> int:
        """Return the number of tracked client windows."""
        return len(self._windows)

    def check(self, key: str, *, now: float | None = None) -> RateLimitDecision:
        """Record one request attempt and return whether it is allowed."""
        if not self._policy.enabled:
            return RateLimitDecision(allowed=True)

        current_time = time.monotonic() if now is None else now
        self._prune_expired_windows(current_time)
        window = self._windows.get(key)
        if window is None or current_time >= window.reset_at:
            self._windows[key] = _ClientWindow(
                count=1,
                reset_at=current_time + self._policy.window_seconds,
            )
            return RateLimitDecision(allowed=True)

        if window.count >= self._policy.requests:
            retry_after = max(1, math.ceil(window.reset_at - current_time))
            return RateLimitDecision(allowed=False, retry_after_seconds=retry_after)

        window.count += 1
        return RateLimitDecision(allowed=True)

    def _prune_expired_windows(self, current_time: float) -> None:
        expired_keys = [
            client_key
            for client_key, window in self._windows.items()
            if current_time >= window.reset_at
        ]
        for client_key in expired_keys:
            del self._windows[client_key]


def build_rate_limiter(settings: AppSettings) -> FixedWindowRateLimiter:
    """Build the application rate limiter from API settings."""
    return FixedWindowRateLimiter(
        RateLimitPolicy(
            enabled=settings.legal_qa_rate_limit_enabled,
            requests=settings.legal_qa_rate_limit_requests,
            window_seconds=settings.legal_qa_rate_limit_window_seconds,
        )
    )


async def enforce_ask_rate_limit(request: Request) -> None:
    """Reject excessive Legal QA ask requests before workflow execution."""
    limiter = _request_rate_limiter(request)
    decision = limiter.check(_client_key(request))
    if decision.allowed:
        return
    retry_after = str(decision.retry_after_seconds or limiter.policy.window_seconds)
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "error": "rate_limit_exceeded",
            "message": "Too many Legal QA requests. Please retry later.",
        },
        headers={"Retry-After": retry_after},
    )


def _request_rate_limiter(request: Request) -> FixedWindowRateLimiter:
    limiter = getattr(request.app.state, "ask_rate_limiter", None)
    if isinstance(limiter, FixedWindowRateLimiter):
        return limiter
    fallback = build_rate_limiter(AppSettings.from_env({}))
    request.app.state.ask_rate_limiter = fallback
    return fallback


def _client_key(request: Request) -> str:
    client = request.client
    if client is None or not client.host:
        return "unknown"
    return client.host
