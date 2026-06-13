#!/usr/bin/env python3
"""Command-line entrypoint for Phase 6 parent-child legal chunking.

Usage:
    uv run python scripts/corpus/chunk_legal_corpus.py \
      --input-dir data/interim \
      --output data/processed/legal_chunks.jsonl \
      --report artifacts/reports/chunking/chunking_report.json
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.processing.legal_chunk_models import ChunkingReport
from src.services.chunking_service import ChunkingService, ChunkingServiceError

EXIT_SUCCESS = 0
EXIT_DOCUMENT_FAILURE = 1
EXIT_WARNING_FAILURE = 2
EXIT_SERVICE_FAILURE = 3
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_STATUS_COLORS = {
    "success": "\x1b[32m",
    "success_with_warnings": "\x1b[33m",
    "failed": "\x1b[31m",
}
_RESET = "\x1b[0m"


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the parent-child chunking CLI argument parser.

    Returns:
        Configured `argparse.ArgumentParser` for Phase 6 service invocation.
    """
    parser = argparse.ArgumentParser(
        prog="scripts/corpus/chunk_legal_corpus.py",
        description="Chunk Phase 5 Vietnamese legal hierarchy JSON into Phase 6 JSONL.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("data/interim"),
        help="Directory containing {LAW_ID}/hierarchy.json inputs.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/legal_chunks.jsonl"),
        help="Path where legal chunk JSONL output is written.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("artifacts/reports/chunking/chunking_report.json"),
        help="Path where chunking_report.json is written.",
    )
    parser.add_argument(
        "--law-ids",
        nargs="+",
        help="Optional list of law IDs to chunk. Defaults to all discovered inputs.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwriting existing JSONL and report outputs.",
    )
    parser.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Return exit code 2 when warnings exist and no laws failed.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-law result lines in addition to the summary.",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI status colors in terminal output.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the Phase 6 parent-child chunking CLI.

    Args:
        argv: Optional argument vector for tests. When omitted, argparse reads
            from `sys.argv`.

    Returns:
        Process exit code according to the Phase 6 CLI policy.
    """
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    try:
        result = ChunkingService().run(
            input_dir=args.input_dir,
            output_path=args.output,
            report_path=args.report,
            law_ids=args.law_ids,
            overwrite=args.overwrite,
        )
    except ChunkingServiceError as exc:
        print(f"Legal chunking failed: {exc.issue.message}", file=sys.stderr)
        return EXIT_SERVICE_FAILURE

    use_color = _supports_color(no_color=args.no_color)
    _print_summary(result.report, report_path=args.report)
    if args.verbose:
        _print_verbose_results(result.report, use_color=use_color)

    return _exit_code(result.report, fail_on_warning=args.fail_on_warning)


def _print_summary(report: ChunkingReport, *, report_path: Path) -> None:
    """Print the deterministic default batch summary table."""
    print("Legal chunking completed.")
    print()
    print(f"Input dir: {report.input_dir}")
    print(f"Output   : {report.output_path}")
    print(f"Report   : {report_path}")
    print()
    print("Summary")
    print(
        _format_table(
            headers=["Metric", "Count"],
            rows=[
                ["Total laws", str(report.total_laws)],
                ["Success", str(report.successful)],
                ["Success with warnings", str(report.success_with_warnings)],
                ["Failed", str(report.failed)],
                ["Total chunks", str(report.total_chunks)],
            ],
        )
    )


def _print_verbose_results(report: ChunkingReport, *, use_color: bool) -> None:
    """Print a deterministic per-law chunking result table."""
    rows: list[list[str]] = []
    for index, summary in enumerate(report.law_summaries, start=1):
        rows.append(
            [
                str(index),
                summary.law_id,
                _status_label(summary.status.value, use_color=use_color),
                str(summary.total_chunks),
                str(summary.warning_count),
                str(summary.error_count),
                summary.input_path or "no input",
            ]
        )

    print()
    print("Results")
    print(
        _format_table(
            headers=["No.", "Law ID", "Status", "Chunks", "Warnings", "Errors", "Input"],
            rows=rows,
        )
    )


def _exit_code(report: ChunkingReport, *, fail_on_warning: bool) -> int:
    """Return the CLI exit code for report status and warning policy."""
    if report.failed > 0:
        return EXIT_DOCUMENT_FAILURE
    if fail_on_warning and _has_warnings(report):
        return EXIT_WARNING_FAILURE
    return EXIT_SUCCESS


def _has_warnings(report: ChunkingReport) -> bool:
    """Return whether a report contains warning-status laws or warnings."""
    return report.success_with_warnings > 0 or bool(report.warnings)


def _supports_color(*, no_color: bool) -> bool:
    """Return whether ANSI color should be emitted for console status text."""
    return not no_color and sys.stdout.isatty()


def _status_label(status: str, *, use_color: bool) -> str:
    """Return a status label with optional ANSI color."""
    if not use_color or status not in _STATUS_COLORS:
        return status
    return f"{_STATUS_COLORS[status]}{status}{_RESET}"


def _format_table(*, headers: list[str], rows: list[list[str]]) -> str:
    """Format rows as a deterministic Unicode table.

    Args:
        headers: Column header labels.
        rows: Table rows. Each row must have the same number of columns as
            `headers`.

    Returns:
        A box-drawing table suitable for deterministic CLI output.
    """
    widths = [
        max(_visible_len(value) for value in [header, *(row[index] for row in rows)])
        for index, header in enumerate(headers)
    ]
    top = _table_rule("┌", "┬", "┐", widths)
    middle = _table_rule("├", "┼", "┤", widths)
    bottom = _table_rule("└", "┴", "┘", widths)
    lines = [top, _table_row(headers, widths), middle]
    lines.extend(_table_row(row, widths) for row in rows)
    lines.append(bottom)
    return "\n".join(lines)


def _table_rule(left: str, joiner: str, right: str, widths: list[int]) -> str:
    """Return a table border rule for the provided column widths."""
    return left + joiner.join("─" * (width + 2) for width in widths) + right


def _table_row(row: list[str], widths: list[int]) -> str:
    """Return one padded table row."""
    cells = [f" {_pad_cell(value, widths[index])} " for index, value in enumerate(row)]
    return "│" + "│".join(cells) + "│"


def _pad_cell(value: str, width: int) -> str:
    """Pad a cell based on visible length so ANSI status colors align."""
    return value + " " * (width - _visible_len(value))


def _visible_len(value: str) -> int:
    """Return string length excluding ANSI escape sequences."""
    return len(_ANSI_RE.sub("", value))


if __name__ == "__main__":
    raise SystemExit(main())
