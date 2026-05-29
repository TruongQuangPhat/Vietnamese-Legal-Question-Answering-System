#!/usr/bin/env python3
"""Run cleaning quality diagnostic audits."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from time import perf_counter
from typing import Any

from rich.console import Console
from rich.table import Table

from src.services.cleaning_quality_audit_service import (
    run_cleaning_quality_audit,
    run_corpus_inventory,
    run_html_pattern_audit,
    run_pattern_groups,
    run_raw_vs_cleaning_comparison,
    run_selector_candidate_audit,
)


console = Console()


def main() -> int:
    """Parse CLI arguments, run diagnostics, and print summaries."""
    parser = argparse.ArgumentParser(
        description="Run diagnostics for raw HTML, selectors, cleaning quality, and pattern groups."
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path("data/raw"),
        help="Directory containing raw HTML artifacts.",
    )
    parser.add_argument(
        "--interim-dir",
        type=Path,
        default=Path("data/interim"),
        help="Directory containing normalized/cleaned artifacts.",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("data/reports"),
        help="Directory to write audit reports.",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path("configs/laws/corpus_registry.yml"),
        help="Path to corpus registry YAML.",
    )
    args = parser.parse_args()

    try:
        console.print("[bold blue]Cleaning Quality Audit[/bold blue]")
        console.print(f"Raw artifacts:       [cyan]{args.raw_dir}[/cyan]")
        console.print(f"Cleaning artifacts:  [cyan]{args.interim_dir}[/cyan]")
        console.print(f"Report directory:    [cyan]{args.report_dir}[/cyan]")
        console.print(f"Corpus registry:     [cyan]{args.registry}[/cyan]\n")

        audit_steps = [
            (
                "Corpus inventory",
                "cleaning_quality_inventory.json",
                lambda: run_corpus_inventory(
                    registry_path=args.registry,
                    raw_dir=args.raw_dir,
                    interim_dir=args.interim_dir,
                    report_dir=args.report_dir,
                ),
            ),
            (
                "HTML pattern audit",
                "html_pattern_audit.json",
                lambda: run_html_pattern_audit(raw_dir=args.raw_dir, report_dir=args.report_dir),
            ),
            (
                "Selector candidate audit",
                "selector_candidate_audit.json",
                lambda: run_selector_candidate_audit(raw_dir=args.raw_dir, report_dir=args.report_dir),
            ),
            (
                "Cleaning quality audit",
                "cleaning_quality_audit.json",
                lambda: run_cleaning_quality_audit(
                    interim_dir=args.interim_dir,
                    report_dir=args.report_dir,
                ),
            ),
            (
                "Raw-vs-cleaning comparison",
                "raw_vs_cleaning_comparison.json",
                lambda: run_raw_vs_cleaning_comparison(
                    raw_dir=args.raw_dir,
                    interim_dir=args.interim_dir,
                    report_dir=args.report_dir,
                ),
            ),
            (
                "Pattern groups",
                "pattern_groups.json",
                lambda: run_pattern_groups(
                    registry_path=args.registry,
                    raw_dir=args.raw_dir,
                    interim_dir=args.interim_dir,
                    report_dir=args.report_dir,
                ),
            ),
        ]

        reports: list[tuple[str, str, dict[str, Any], float]] = []
        for title, filename, runner in audit_steps:
            reports.append(_run_audit_step(title, filename, args.report_dir, runner))

        console.print("\n[bold green]Cleaning quality diagnostics completed.[/bold green]")
        total_errors = 0
        summary_table = Table(title="Cleaning Quality Audit Summary")
        summary_table.add_column("Audit", style="cyan")
        summary_table.add_column("Records", justify="right")
        summary_table.add_column("Errors", justify="right")
        summary_table.add_column("Duration", justify="right")
        summary_table.add_column("Report", overflow="fold")

        for title, filename, report, duration_seconds in reports:
            total_errors += _error_count(report)
            error_count = _error_count(report)
            error_style = "red" if error_count else "green"
            summary_table.add_row(
                title,
                str(report.get("total_records", 0)),
                f"[{error_style}]{error_count}[/{error_style}]",
                f"{duration_seconds:.2f}s",
                str(args.report_dir / filename),
            )

        console.print(summary_table)
        console.print(f"Total errors captured across all reports: [bold]{total_errors}[/bold]")
        return 0
    except Exception as exc:
        console.print(
            "FATAL ERROR: cleaning quality audit crashed unexpectedly.",
            style="bold red",
            file=sys.stderr,
        )
        console.print(f"Error: {exc}", style="red", file=sys.stderr)
        return 1


def _run_audit_step(
    title: str,
    filename: str,
    report_dir: Path,
    runner: Callable[[], dict[str, Any]],
) -> tuple[str, str, dict[str, Any], float]:
    """Run one diagnostic report and print progress.

    Args:
        title: Human-readable audit title.
        filename: Report filename written by the audit.
        report_dir: Directory where the report is written.
        runner: Zero-argument callable that executes the audit.

    Returns:
        Tuple of title, filename, report dictionary, and duration in seconds.
    """
    report_path = report_dir / filename
    console.print(f"[cyan]Running:[/cyan] {title} -> [dim]{report_path}[/dim]")
    started_at = perf_counter()
    report = runner()
    duration_seconds = perf_counter() - started_at
    error_count = _error_count(report)
    status = "[green]done[/green]" if error_count == 0 else "[yellow]done with errors[/yellow]"
    console.print(
        f"  {status}: records={report.get('total_records', 0)} "
        f"errors={error_count} duration={duration_seconds:.2f}s"
    )
    return title, filename, report, duration_seconds


def _error_count(report: dict[str, Any]) -> int:
    errors = report.get("errors", [])
    return len(errors) if isinstance(errors, list) else 0


if __name__ == "__main__":
    sys.exit(main())
