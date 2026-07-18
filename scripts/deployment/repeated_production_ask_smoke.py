"""Run a bounded repeated production-style ask smoke with sanitized output."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from typing import Any

from scripts.deployment.validate_production_ask_smoke_response import (
    SmokeValidationError,
    validate_response_payload,
    validate_warmup_payload,
)

CONFIRMATION = "I_UNDERSTAND_THIS_CALLS_REAL_PRODUCTION_SERVICES"
DEFAULT_QUESTION = "Hợp đồng dân sự vô hiệu khi nào?"


def main() -> int:
    """Run the optional repeated smoke command."""
    args = _parse_args()
    if args.confirm != CONFIRMATION:
        raise SystemExit("Confirmation phrase did not match; no production request was sent.")
    base_url = args.base_url.rstrip("/")
    if not base_url:
        raise SystemExit("base URL must not be blank")

    warmup = _get_json(f"{base_url}/api/v1/legal-qa/warmup", timeout_seconds=args.timeout)
    warmup_lines = validate_warmup_payload(warmup.payload, http_status=str(warmup.status))
    for line in warmup_lines:
        print(line)
    model_cache_key = str(warmup.payload["model_cache_key"])

    failures = 0
    for index in range(1, args.count + 1):
        started_at = time.perf_counter()
        response = _post_json(
            f"{base_url}/api/v1/legal-qa/ask",
            payload={
                "question": args.question,
                "top_k": 5,
                "include_evidence": True,
                "include_debug": False,
            },
            timeout_seconds=args.timeout,
        )
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        try:
            lines = validate_response_payload(
                response.payload,
                http_status=str(response.status),
                expected_model_cache_key=model_cache_key,
            )
        except SmokeValidationError as exc:
            failures += 1
            print(f"Ask {index}/{args.count}: FAIL elapsed_ms={elapsed_ms} reason={exc}")
        else:
            print(f"Ask {index}/{args.count}: PASS elapsed_ms={elapsed_ms}")
            for line in lines:
                if line.startswith(
                    (
                        "Request ID:",
                        "Decision:",
                        "Retrieval mode:",
                        "Dense retrieval used:",
                        "Dense retrieval fallback used:",
                        "Fallback used:",
                        "Retriever stage failed:",
                        "Warnings:",
                        "Severe warnings:",
                    )
                ):
                    print(line)

    print(f"Repeated smoke summary: total={args.count} failures={failures}")
    return 1 if failures else 0


class JsonResponse:
    """Small response wrapper for sanitized smoke calls."""

    def __init__(self, *, status: int, payload: dict[str, Any]) -> None:
        self.status = status
        self.payload = payload


def _get_json(url: str, *, timeout_seconds: int) -> JsonResponse:
    request = urllib.request.Request(url, method="GET")
    return _send_json_request(request, timeout_seconds=timeout_seconds)


def _post_json(url: str, *, payload: dict[str, Any], timeout_seconds: int) -> JsonResponse:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return _send_json_request(request, timeout_seconds=timeout_seconds)


def _send_json_request(request: urllib.request.Request, *, timeout_seconds: int) -> JsonResponse:
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw_body = response.read().decode("utf-8", errors="replace")
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        raw_body = exc.read().decode("utf-8", errors="replace")
        status = int(exc.code)
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Smoke endpoint returned non-JSON HTTP {status}.") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"Smoke endpoint returned non-object JSON HTTP {status}.")
    return JsonResponse(status=status, payload=payload)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run bounded repeated production-style ask smoke after warmup."
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    args = parser.parse_args()
    if args.count <= 0:
        parser.error("--count must be positive")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    return args


if __name__ == "__main__":
    raise SystemExit(main())
