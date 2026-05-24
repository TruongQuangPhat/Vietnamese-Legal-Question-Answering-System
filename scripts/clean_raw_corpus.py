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

from ingestion.cleaning import clean_raw_corpus, write_cleaning_report

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

    args = parser.parse_args()

    try:
        print(f"Starting Cleaning & Normalization...")
        print(f"Raw directory: {args.raw_dir}")
        print(f"Output directory: {args.output_dir}")

        report = clean_raw_corpus(
            raw_dir=args.raw_dir,
            output_dir=args.output_dir,
            min_text_length=args.min_text_length,
            write_txt=args.write_txt
        )

        write_cleaning_report(report, args.report)

        summary = report["summary"]
        print("\nCleaning & Normalization Summary")
        print("--------------------------------")
        print(f"Input artifacts:          {summary['total_artifacts']:4d}")
        print(f"Successfully cleaned:     {summary['successfully_cleaned']:4d}")
        print(f"Warning artifacts:        {summary['warning_artifacts']:4d}")
        print(f"Failed artifacts:         {summary['failed']:4d}")
        print(f"Suspiciously short texts: {summary['suspiciously_short_texts']:4d}")
        print(f"Missing article markers:  {summary['missing_article_marker']:4d}")
        print(f"Output directory:         {args.output_dir}")
        print(f"Report:                   {args.report}")

        if args.verbose:
            print("\nPer-artifact details:")
            for item in report["items"]:
                status_icon = {
                    "success": "✓",
                    "warning": "⚠",
                    "failed": "✗"
                }.get(item["status"], "?")
                print(f"  {status_icon} {item['law_id']:20s} {item['status']:10s} chars={item['normalized_text_chars']:>6d} arts={item['article_count_estimate']:>3d}")
                if item["errors"]:
                    for err in item["errors"]:
                        print(f"      ERROR: {err}")
                if item["warnings"]:
                    for warn in item["warnings"]:
                        print(f"      WARN: {warn}")

        if summary["failed"] > 0:
            print("\nCleaning finished with errors.")
            return 1

        print("\nCleaning completed successfully.")
        return 0

    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 2

if __name__ == "__main__":
    sys.exit(main())