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


def validate_response_payload(payload: dict[str, Any], *, http_status: str = "200") -> list[str]:
    """Validate one production `/ask` smoke response.

    Args:
        payload: Parsed response JSON.
        http_status: HTTP status returned by curl.

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
    if retrieval_mode in {None, "hybrid"}:
        if fallback_used is True or dense_retrieval_fallback_used is True:
            raise SmokeValidationError(
                "Ask smoke used degraded dense retrieval fallback in hybrid mode."
            )
        if dense_retrieval_used is not True:
            raise SmokeValidationError("Ask smoke did not use dense retrieval in hybrid mode.")
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
        lines = validate_response_payload(payload, http_status=args.http_status)
    except SmokeValidationError as exc:
        raise SystemExit(str(exc)) from exc

    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
