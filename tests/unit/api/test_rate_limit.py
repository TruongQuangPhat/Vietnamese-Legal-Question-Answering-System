from __future__ import annotations

from src.api.rate_limit import FixedWindowRateLimiter, RateLimitPolicy


def test_fixed_window_limiter_allows_requests_within_quota() -> None:
    limiter = FixedWindowRateLimiter(RateLimitPolicy(enabled=True, requests=2, window_seconds=60))

    first = limiter.check("client-a", now=100.0)
    second = limiter.check("client-a", now=101.0)

    assert first.allowed is True
    assert second.allowed is True
    assert limiter.active_window_count == 1


def test_fixed_window_limiter_returns_positive_retry_after() -> None:
    limiter = FixedWindowRateLimiter(RateLimitPolicy(enabled=True, requests=1, window_seconds=60))

    allowed = limiter.check("client-a", now=100.0)
    blocked = limiter.check("client-a", now=115.2)
    still_blocked = limiter.check("client-a", now=159.5)

    assert allowed.allowed is True
    assert blocked.allowed is False
    assert blocked.retry_after_seconds == 45
    assert still_blocked.allowed is False
    assert still_blocked.retry_after_seconds == 1


def test_fixed_window_limiter_resets_after_window_expires() -> None:
    limiter = FixedWindowRateLimiter(RateLimitPolicy(enabled=True, requests=1, window_seconds=10))

    limiter.check("client-a", now=100.0)
    blocked = limiter.check("client-a", now=109.0)
    reset = limiter.check("client-a", now=110.0)

    assert blocked.allowed is False
    assert reset.allowed is True
    assert limiter.active_window_count == 1


def test_fixed_window_limiter_prunes_expired_client_windows() -> None:
    limiter = FixedWindowRateLimiter(RateLimitPolicy(enabled=True, requests=1, window_seconds=10))

    limiter.check("client-a", now=100.0)
    limiter.check("client-b", now=101.0)
    assert limiter.active_window_count == 2

    limiter.check("client-c", now=111.0)

    assert limiter.active_window_count == 1


def test_disabled_fixed_window_limiter_does_not_track_clients() -> None:
    limiter = FixedWindowRateLimiter(RateLimitPolicy(enabled=False, requests=1, window_seconds=60))

    first = limiter.check("client-a", now=100.0)
    second = limiter.check("client-a", now=101.0)

    assert first.allowed is True
    assert second.allowed is True
    assert limiter.active_window_count == 0
