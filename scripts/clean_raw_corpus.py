#!/usr/bin/env python3
"""Cleaning & Normalization CLI.

Usage:
    uv run python scripts/clean_raw_corpus.py \
      --raw-dir data/raw \
      --output-dir data/interim \
      --report data/reports/cleaning_report.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from services.cleaning_service import execute_cleaning_pipeline, CleaningPipelineConfig
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Clean and normalize raw legal HTML artifacts.",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path("data/raw"),
        help="Path to raw artifacts directory (default: data/raw)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/interim"),
        help="Path to output normalized artifacts (default: data/interim)"
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("data/reports/cleaning_report.json"),
        help="Path to write the cleaning report (default: data/reports/cleaning_report.json)"
    )
    parser.add_argument(
        "--min-text-length",
        type=int,
        default=10000,
        help="Minimum normalized text length before a warning is issued (default: 10000)"
    )
    parser.add_argument(
        "--write-txt",
        action="store_true",
        help="Write optional cleaned.txt files for manual debugging"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed per-artifact results"
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Print a detailed quality audit table for all laws"
    )

    args = parser.parse_args()

    try:
        console.print("[bold blue]Starting Cleaning & Normalization...[/bold blue]")
        console.print(f"Raw directory: [cyan]{args.raw_dir}[/cyan]")
        console.print(f"Output directory: [cyan]{args.output_dir}[/cyan]")

        # Construct pipeline config
        config = CleaningPipelineConfig(
            raw_dir=args.raw_dir,
            output_dir=args.output_dir,
            report_path=args.report,
            min_text_length=args.min_text_length,
            write_txt=args.write_txt,
            verbose=args.verbose,
        )

        report = execute_cleaning_pipeline(config)

        summary = report["summary"]


        summary_table = Table(title="Cleaning & Normalization Summary", show_header=False, box=None)
        summary_table.add_row("Input artifacts", f"{summary['total_artifacts']:4d}")
        summary_table.add_row("Successfully cleaned", f"[green]{summary['successfully_cleaned']:4d}[/green]")
        summary_table.add_row("Warning artifacts", f"[yellow]{summary['warning_artifacts']:4d}[/yellow]")
        summary_table.add_row("Failed artifacts", f"[red]{summary['failed']:4d}[/red]")
        summary_table.add_row("Suspiciously short", f"{summary['suspiciously_short_texts']:4d}")
        summary_table.add_row("Missing article marker", f"{summary['missing_article_marker']:4d}")

        console.print("\n", Panel(summary_table))
        console.print(f"Report saved to: [cyan]{args.report}[/cyan]")

        if args.audit:
            audit_table = Table(title="Law Quality Audit", show_lines=True)
            audit_table.add_column("Law ID", style="cyan")
            audit_table.add_column("Status", justify="center")
            audit_table.add_column("Length", justify="right")
            audit_table.add_column("Headings", justify="right")
            audit_table.add_column("Refs", justify="right")
            audit_table.add_column("Max Art", justify="right")
            audit_table.add_column("Seq Score", justify="right")
            audit_table.add_column("Has Art 1", justify="center")

            for item in report["items"]:
                status_color = {
                    "success": "green",
                    "warning": "yellow",
                    "failed": "red"
                }.get(item["status"], "white")

                status_icon = {
                    "success": "✓",
                    "warning": "⚠",
                    "failed": "✗"
                }.get(item["status"], "?")

                audit_table.add_row(
                    item["law_id"],
                    f"[{status_color}]{status_icon}[/{status_color}]",
                    f"{item['normalized_text_chars']:>6d}",
                    f"{item.get('article_heading_count', 0):>3d}",
                    f"{item.get('article_reference_count', item.get('article_count_estimate', 0)):>3d}",
                    f"{item.get('max_heading_article_number', 'N/A'):>4}",
                    f"{item.get('heading_sequence_score', 0.0):.2f}",
                    "Yes" if item.get("has_heading_article_1") else "No"
                )
            console.print("\n", audit_table)

        if args.verbose:
            console.print("\n[bold]Per-artifact details:[/bold]")
            for item in report["items"]:
                status_color = {"success": "green", "warning": "yellow", "failed": "red"}.get(item["status"], "white")
                console.print(
                    f"  [{status_color}]{item['status']}[/{status_color}] "
                    f"{item['law_id']:20s} chars={item['normalized_text_chars']:>6d} "
                    f"headings={item.get('article_heading_count', 0):>3d} "
                    f"refs={item.get('article_reference_count', item.get('article_count_estimate', 0)):>3d}"
                )
                for err in item["errors"]:
                    console.print(f"      [red]ERROR:[/red] {err}")
                for warn in item["warnings"]:
                    console.print(f"      [yellow]WARN:[/yellow] {warn}")

        if summary["failed"] > 0:
            console.print("\n[bold red]Cleaning finished with errors.[/bold red]")
            return 1

        console.print("\n[bold green]Cleaning completed successfully.[/bold green]")
        return 0

    except Exception as e:
        console.print(f"[bold red]Unexpected error: {e}[/bold red]", style="red")
        import traceback
        traceback.print_exc()
        return 2

if __name__ == "__main__":
    sys.exit(main())
