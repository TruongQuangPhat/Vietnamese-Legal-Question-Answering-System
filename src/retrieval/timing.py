"""Request-scoped sanitized timing for retrieval internals."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

RetrievalTimingLogger = Callable[..., None]


@dataclass(frozen=True)
class RetrievalTimingContext:
    """Sanitized per-request timing context for retrieval internals."""

    logger: RetrievalTimingLogger
    request_id: str
    timing_started_at: float


_TIMING_CONTEXT: ContextVar[RetrievalTimingContext | None] = ContextVar(
    "retrieval_timing_context",
    default=None,
)


@contextmanager
def retrieval_timing_context(context: RetrievalTimingContext | None) -> Iterator[None]:
    """Temporarily attach sanitized timing metadata to the current request context."""
    token = _TIMING_CONTEXT.set(context)
    try:
        yield
    finally:
        _TIMING_CONTEXT.reset(token)


def emit_retrieval_timing(
    *,
    stage: str,
    stage_started_at: float | None = None,
    exception_class: str | None = None,
    timeout_seconds: float | None = None,
    fallback_used: bool = False,
    top_k: int | None = None,
    **safe_metadata: object,
) -> None:
    """Emit one sanitized retrieval timing event when a request context is active."""
    context = _TIMING_CONTEXT.get()
    if context is None:
        return
    now = time.perf_counter()
    elapsed_ms = int((now - stage_started_at) * 1000) if stage_started_at is not None else 0
    total_elapsed_ms = int((now - context.timing_started_at) * 1000)
    context.logger(
        stage,
        context.request_id,
        elapsed_ms,
        total_elapsed_ms,
        exception_class,
        timeout_seconds=timeout_seconds,
        fallback_used=fallback_used,
        top_k=top_k,
        **safe_metadata,
    )


def safe_exception_class(exc: BaseException) -> str:
    """Return only the exception class name, never exception text."""
    return type(exc).__name__
