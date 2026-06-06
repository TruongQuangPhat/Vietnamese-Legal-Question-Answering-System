#!/usr/bin/env python3
"""Command-line entrypoint for Phase 5 legal hierarchy parsing.

Usage:
    uv run python scripts/parse_legal_hierarchy.py \
      --input-dir data/interim \
      --output-dir data/interim \
      --report artifacts/reports/parsing/legal_parsing_report.json
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.processing.legal_hierarchy_models import LegalParsingReport
from src.services.legal_parsing_service import (
    LegalParsingService,
    LegalParsingServiceError,
)

EXIT_SUCCESS = 0
EXIT_DOCUMENT_FAILURE = 1
EXIT_WARNING_FAILURE = 2
EXIT_SERVICE_FAILURE = 3


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the legal hierarchy parsing CLI argument parser.

    Returns:
        Configured `argparse.ArgumentParser` for Step 10 service invocation.
    """
    parser = argparse.ArgumentParser(
        prog="scripts/parse_legal_hierarchy.py",
        description="Parse normalized Vietnamese legal documents into Phase 5 hierarchy JSON.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("data/interim"),
        help="Directory containing {LAW_ID}/normalized.json inputs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/interim"),
        help="Directory where {LAW_ID}/hierarchy.json outputs are written.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("artifacts/reports/parsing/legal_parsing_report.json"),
        help="Path where legal_parsing_report.json is written.",
    )
    parser.add_argument(
        "--law-ids",
        nargs="+",
        help="Optional list of law IDs to parse. Defaults to all discovered inputs.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwriting existing hierarchy.json outputs.",
    )
    parser.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Return exit code 2 when warnings exist and no documents failed.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-law result lines in addition to the summary.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the Phase 5 legal hierarchy parsing CLI.

    Args:
        argv: Optional argument vector for tests. When omitted, argparse reads
            from `sys.argv`.

    Returns:
        Process exit code according to the Step 10 CLI policy.
    """
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    try:
        result = LegalParsingService().run(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            report_path=args.report,
            law_ids=args.law_ids,
            overwrite=args.overwrite,
        )
    except LegalParsingServiceError as exc:
        print(f"Legal hierarchy parsing failed: {exc.issue.message}", file=sys.stderr)
        return EXIT_SERVICE_FAILURE

    _print_summary(result.report, report_path=args.report)
    if args.verbose:
        _print_verbose_results(result.report)

    return _exit_code(result.report, fail_on_warning=args.fail_on_warning)


def _print_summary(report: LegalParsingReport, *, report_path: Path) -> None:
    """Print the deterministic default batch summary."""
    print("Legal hierarchy parsing completed.")
    print(f"Input dir: {report.input_dir}")
    print(f"Output dir: {report.output_dir}")
    print(f"Report: {report_path}")
    print(f"Total: {report.total_documents}")
    print(f"Success: {report.successful}")
    print(f"Success with warnings: {report.success_with_warnings}")
    print(f"Failed: {report.failed}")


def _print_verbose_results(report: LegalParsingReport) -> None:
    """Print one deterministic line per law result."""
    for result in report.results:
        output_path = result.output_path or "no output"
        print(f"[{result.status.value}] {result.law_id} -> {output_path}")


def _exit_code(report: LegalParsingReport, *, fail_on_warning: bool) -> int:
    """Return the CLI exit code for report status and warning policy."""
    if report.failed > 0:
        return EXIT_DOCUMENT_FAILURE
    if fail_on_warning and _has_warnings(report):
        return EXIT_WARNING_FAILURE
    return EXIT_SUCCESS


def _has_warnings(report: LegalParsingReport) -> bool:
    """Return whether a report contains warning-status docs or warnings."""
    return report.success_with_warnings > 0 or bool(report.warnings)


if __name__ == "__main__":
    raise SystemExit(main())
