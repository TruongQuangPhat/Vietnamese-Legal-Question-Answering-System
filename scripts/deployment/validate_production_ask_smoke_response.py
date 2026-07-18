"""Validate sanitized Production Ask Smoke response JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

MIN_ANSWER_LENGTH = 30
GENERIC_ERROR_ANSWERS = frozenset(
    {
        "Không thể xử lý yêu cầu lúc này. Vui lòng thử lại sau.",
    }
)
SEVERE_WARNINGS = frozenset(
    {
        "ask_timeout",
        "embedding_model_load_timeout",
        "embedding_model_load_error",
        "query_embedding_timeout",
        "query_embedding_error",
        "qdrant_retrieval_timeout",
        "qdrant_retrieval_error",
        "dense_retrieval_fallback_used",
        "dense_retriever_error",
        "internal_error",
        "retrieval_error",
        "llm_timeout",
    }
)


class SmokeValidationError(ValueError):
    """Raised when a Production Ask Smoke response fails validation."""


def validate_warmup_payload(
    payload: dict[str, Any],
    *,
    http_status: str = "200",
    require_cache_hit_before: bool = False,
    expected_model_cache_key: str | None = None,
) -> list[str]:
    """Validate one production embedding warmup response.

    Args:
        payload: Parsed warmup response JSON.
        http_status: HTTP status returned by curl.
        require_cache_hit_before: Whether this is a second warmup that must
            prove the previous warmup populated the process-local cache.
        expected_model_cache_key: Optional opaque cache key from a previous
            warmup that must match this response.

    Returns:
        Sanitized diagnostic log lines.

    Raises:
        SmokeValidationError: If warmup did not prove the model is loaded and
            cached for the following ask request.
    """
    if http_status != "200":
        raise SmokeValidationError("Warmup failed with non-200 HTTP status.")

    model_cache_key = payload.get("model_cache_key")
    lines = [
        f"Warmup warmed: {payload.get('warmed')}",
        f"Warmup elapsed_ms: {payload.get('elapsed_ms')}",
        f"Warmup model_path_configured: {payload.get('model_path_configured')}",
        f"Warmup model_path_exists: {payload.get('model_path_exists')}",
        f"Warmup required_files_present: {payload.get('required_files_present')}",
        f"Warmup model_load_completed: {payload.get('model_load_completed')}",
        f"Warmup model_load_timeout: {payload.get('model_load_timeout')}",
        f"Warmup encode_completed: {payload.get('encode_completed')}",
        f"Warmup encode_timeout: {payload.get('encode_timeout')}",
        f"Warmup cache_hit_before: {payload.get('cache_hit_before')}",
        f"Warmup cache_hit_after: {payload.get('cache_hit_after')}",
        f"Warmup model_cache_key: {model_cache_key}",
    ]
    exception_class = payload.get("exception_class")
    if exception_class is not None:
        lines.append(f"Warmup exception_class: {exception_class}")

    required_true = (
        "warmed",
        "model_path_configured",
        "model_path_exists",
        "required_files_present",
        "model_load_completed",
        "encode_completed",
        "cache_hit_after",
    )
    missing = [name for name in required_true if payload.get(name) is not True]
    if missing:
        raise SmokeValidationError("Warmup missing required true fields: " + ", ".join(missing))
    required_false = ("model_load_timeout", "encode_timeout")
    failed_false = [name for name in required_false if payload.get(name) is not False]
    if failed_false:
        raise SmokeValidationError("Warmup had timeout field(s): " + ", ".join(failed_false))
    if require_cache_hit_before and payload.get("cache_hit_before") is not True:
        raise SmokeValidationError("Second warmup did not start from the embedding cache.")
    if not isinstance(model_cache_key, str) or not model_cache_key.strip():
        raise SmokeValidationError("Warmup did not return a model_cache_key.")
    if expected_model_cache_key is not None and model_cache_key != expected_model_cache_key:
        raise SmokeValidationError("Warmup model_cache_key did not match the first warmup.")
    return lines


def validate_response_payload(
    payload: dict[str, Any],
    *,
    http_status: str = "200",
    expected_model_cache_key: str | None = None,
) -> list[str]:
    """Validate one production `/ask` smoke response.

    Args:
        payload: Parsed response JSON.
        http_status: HTTP status returned by curl.
        expected_model_cache_key: Optional opaque cache key from successful
            warmup that the ask metadata must match.

    Returns:
        Sanitized diagnostic log lines.

    Raises:
        SmokeValidationError: If the response does not satisfy smoke criteria.
    """
    if http_status != "200":
        raise SmokeValidationError("Ask smoke failed with non-200 HTTP status.")

    keys = sorted(payload.keys())
    answer = payload.get("answer")
    citations = payload.get("citations")
    evidence = payload.get("evidence")
    warnings = payload.get("warnings")
    decision = payload.get("decision")
    metadata = payload.get("metadata")

    answer_length = len(answer) if isinstance(answer, str) else 0
    citation_count = len(citations) if isinstance(citations, list) else 0
    evidence_count = len(evidence) if isinstance(evidence, list) else 0
    warning_names = [str(item) for item in warnings] if isinstance(warnings, list) else []

    if not isinstance(metadata, dict):
        raise SmokeValidationError("Ask smoke response metadata was missing or invalid.")

    model = metadata.get("model")
    model_exists = isinstance(model, str) and bool(model.strip())
    retrieval_question_prepared = metadata.get("retrieval_question_prepared")
    follow_up_detected = metadata.get("follow_up_detected")
    latency_ms = metadata.get("latency_ms")
    retrieval_mode = metadata.get("retrieval_mode")
    dense_retrieval_used = metadata.get("dense_retrieval_used")
    dense_retrieval_fallback_used = metadata.get("dense_retrieval_fallback_used")
    fallback_used = metadata.get("fallback_used")
    retriever_stage_failed = metadata.get("retriever_stage_failed")
    embedding_model_cache_hit = metadata.get("embedding_model_cache_hit")
    embedding_model_loaded_before_request = metadata.get("embedding_model_loaded_before_request")
    model_cache_key = metadata.get("model_cache_key")

    lines = [
        "Response JSON keys: " + ", ".join(keys),
        f"Decision: {decision}",
        f"Answer length: {answer_length}",
        f"Citation count: {citation_count}",
        f"Evidence count: {evidence_count}",
    ]
    if latency_ms is not None:
        lines.append(f"Response latency_ms: {latency_ms}")
    lines.extend(
        [
            f"Metadata model exists: {model_exists}",
            f"Retrieval mode: {retrieval_mode}",
            f"Dense retrieval used: {dense_retrieval_used}",
            f"Dense retrieval fallback used: {dense_retrieval_fallback_used}",
            f"Fallback used: {fallback_used}",
            f"Retriever stage failed: {retriever_stage_failed}",
            f"Embedding model cache hit: {embedding_model_cache_hit}",
            f"Embedding model loaded before request: {embedding_model_loaded_before_request}",
            f"Model cache key: {model_cache_key}",
            f"Retrieval question prepared: {retrieval_question_prepared}",
            f"Follow-up detected: {follow_up_detected}",
            "Warnings: " + ", ".join(warning_names),
            (
                "retrieval_question_prepared is diagnostic for standalone questions; "
                "citations, model presence, decision, answer length, and severe warnings "
                "are the primary pass criteria for this smoke."
            ),
        ]
    )

    if decision == "error":
        raise SmokeValidationError("Ask smoke returned decision=error.")
    if not isinstance(answer, str) or answer_length < MIN_ANSWER_LENGTH:
        raise SmokeValidationError("Ask smoke returned a missing or too-short answer.")
    if answer in GENERIC_ERROR_ANSWERS:
        raise SmokeValidationError("Ask smoke returned the generic internal-error answer.")
    if not model_exists:
        raise SmokeValidationError("Ask smoke returned null or empty metadata.model.")

    severe_found = sorted(set(warning_names).intersection(SEVERE_WARNINGS))
    if severe_found:
        raise SmokeValidationError(
            "Ask smoke returned severe warning(s): " + ", ".join(severe_found)
        )
    if citation_count < 1:
        raise SmokeValidationError("Ask smoke returned no citations.")
    if retrieval_mode != "hybrid":
        raise SmokeValidationError("Ask smoke did not report hybrid retrieval mode.")
    if fallback_used is True or dense_retrieval_fallback_used is True:
        raise SmokeValidationError(
            "Ask smoke used degraded dense retrieval fallback in hybrid mode."
        )
    if dense_retrieval_used is not True:
        raise SmokeValidationError("Ask smoke did not use dense retrieval in hybrid mode.")
    if embedding_model_cache_hit is not True:
        raise SmokeValidationError(
            "Ask smoke did not start from the warmed embedding model cache in hybrid mode."
        )
    if embedding_model_loaded_before_request is not True:
        raise SmokeValidationError(
            "Ask smoke did not report embedding model loaded before request in hybrid mode."
        )
    if not isinstance(model_cache_key, str) or not model_cache_key.strip():
        raise SmokeValidationError("Ask smoke did not return a model_cache_key.")
    if expected_model_cache_key is not None and model_cache_key != expected_model_cache_key:
        raise SmokeValidationError("Ask smoke model_cache_key did not match warmup.")
    if follow_up_detected is True and retrieval_question_prepared is False:
        raise SmokeValidationError(
            "Ask smoke detected a follow-up question but did not prepare a retrieval question."
        )
    if follow_up_detected is not True and retrieval_question_prepared is False:
        lines.append(
            "retrieval_question_prepared=false is acceptable for this standalone smoke question."
        )

    return lines


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate sanitized Production Ask Smoke response JSON."
    )
    parser.add_argument("--response-file", required=True, type=Path)
    parser.add_argument("--http-status", required=True)
    parser.add_argument("--expected-model-cache-key")
    return parser.parse_args()


def main() -> int:
    """Run CLI validation."""
    args = _parse_args()
    if args.http_status != "200":
        raise SystemExit("Ask smoke failed with non-200 HTTP status.")

    try:
        payload = json.loads(args.response_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit("Ask smoke response was not JSON.") from exc

    try:
        lines = validate_response_payload(
            payload,
            http_status=args.http_status,
            expected_model_cache_key=args.expected_model_cache_key,
        )
    except SmokeValidationError as exc:
        raise SystemExit(str(exc)) from exc

    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
