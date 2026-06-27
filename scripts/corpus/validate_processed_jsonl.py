#!/usr/bin/env python3
"""Command-line entrypoint for processed JSONL validation.

Usage:
    uv run python scripts/corpus/validate_processed_jsonl.py \
      --input data/processed/legal_chunks.jsonl \
      --config configs/processing/processed_jsonl_validation.yml \
      --output artifacts/reports/chunking/processed_jsonl_validation_report.json \
      --pretty
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.processing.processed_jsonl_validation_models import (
    ProcessedJsonlValidationConfig,
    ProcessedJsonlValidationReport,
)
from src.processing.processed_jsonl_validator import ProcessedJsonlValidator

EXIT_SUCCESS = 0
EXIT_VALIDATION_FAILURE = 1
EXIT_WARNING_FAILURE = 2


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the processed JSONL validation argument parser.

    Returns:
        Configured parser with official processed JSONL validation paths and warning policy.
    """
    parser = argparse.ArgumentParser(
        prog="scripts/corpus/validate_processed_jsonl.py",
        description="Validate parent-child chunking legal chunk JSONL for embedding/indexing readiness.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/processed/legal_chunks.jsonl"),
        help="Processed legal chunk JSONL to validate.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/processing/processed_jsonl_validation.yml"),
        help="processed JSONL validation YAML configuration.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/reports/chunking/processed_jsonl_validation_report.json"),
        help="Destination for the complete processed JSONL validation report.",
    )
    parser.add_argument(
        "--fail-on-warnings",
        action="store_true",
        help="Return exit code 2 for pass_with_warnings reports.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Write indented report JSON.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the normal completion summary.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run processed JSONL validation and write its complete report.

    Args:
        argv: Optional argument vector for tests. When omitted, argparse reads
            from `sys.argv`.

    Returns:
        `0` for pass or warning-only pass, `1` for hard validation failure,
        and `2` for warning-only pass when `--fail-on-warnings` is enabled.
    """
    args = build_arg_parser().parse_args(argv)
    try:
        config = _load_config(
            args.config,
            input_path=args.input,
            report_path=args.output,
        )
        report = ProcessedJsonlValidator(config).validate(args.input)
        _write_report(args.output, report, pretty=args.pretty)
    except (OSError, UnicodeError, yaml.YAMLError, ValidationError, ValueError) as exc:
        print(f"Processed JSONL validation failed: {exc}", file=sys.stderr)
        return EXIT_VALIDATION_FAILURE

    if not args.quiet:
        _print_summary(report, report_path=args.output)
    return _exit_code(report, fail_on_warnings=args.fail_on_warnings)


def _load_config(
    config_path: Path,
    *,
    input_path: Path,
    report_path: Path,
) -> ProcessedJsonlValidationConfig:
    """Load YAML configuration and apply explicit CLI path overrides.

    Args:
        config_path: YAML configuration path.
        input_path: JSONL path selected by the CLI.
        report_path: Report destination selected by the CLI.

    Returns:
        Validated processed JSONL validation configuration.

    Raises:
        ValueError: If the YAML root is not an object.
        OSError: If the configuration cannot be read.
        yaml.YAMLError: If the YAML is malformed.
        ValidationError: If configuration values violate the Pydantic schema.
    """
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("validation config root must be a YAML object")
    config_payload: dict[str, Any] = {
        **payload,
        "input_path": str(input_path),
        "report_path": str(report_path),
    }
    return ProcessedJsonlValidationConfig.model_validate(config_payload)


def _write_report(
    report_path: Path,
    report: ProcessedJsonlValidationReport,
    *,
    pretty: bool,
) -> None:
    """Serialize the complete validation report as UTF-8 JSON.

    Args:
        report_path: Destination JSON path.
        report: Completed processed JSONL validation report.
        pretty: Whether to indent the JSON for human inspection.
    """
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
    )
    report_path.write_text(f"{payload}\n", encoding="utf-8")


def _print_summary(
    report: ProcessedJsonlValidationReport,
    *,
    report_path: Path,
) -> None:
    """Print the concise processed JSONL validation gate and embedding-readiness summary."""
    readiness = report.embedding_readiness
    print("processed JSONL validation complete")
    print(f"Status: {report.status}")
    print(f"Total lines: {report.total_lines}")
    print(f"Valid chunks: {report.valid_chunks}")
    print(f"Invalid chunks: {report.invalid_chunks}")
    print(f"Errors: {report.errors_total}")
    print(f"Warnings: {report.warnings_total}")
    print(f"Embedding readiness: {readiness.get('readiness_status', 'unknown')}")
    print(f"Embedding ready: {str(bool(readiness.get('embedding_ready', False))).lower()}")
    print(f"Report: {report_path}")


def _exit_code(
    report: ProcessedJsonlValidationReport,
    *,
    fail_on_warnings: bool,
) -> int:
    """Return the official processed JSONL validation exit code for report status."""
    if report.status == "fail":
        return EXIT_VALIDATION_FAILURE
    if report.status == "pass_with_warnings" and fail_on_warnings:
        return EXIT_WARNING_FAILURE
    return EXIT_SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
