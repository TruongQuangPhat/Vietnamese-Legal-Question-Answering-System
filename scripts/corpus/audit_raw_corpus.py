#!/usr/bin/env python3
"""Raw corpus audit CLI.

Usage:
    uv run python scripts/corpus/audit_raw_corpus.py \
      --registry configs/laws/corpus_registry.yml \
      --raw-dir data/raw \
      --output artifacts/reports/audit/raw_corpus_audit.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from services.raw_audit_service import run_raw_audit_pipeline
from src.ingestion.exceptions import AuditError


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit raw corpus artifacts after crawling.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run python scripts/corpus/audit_raw_corpus.py \\
    --registry configs/laws/corpus_registry.yml \\
    --raw-dir data/raw \\
    --output artifacts/reports/audit/raw_corpus_audit.json

  # With custom minimum HTML size:
  uv run python scripts/corpus/audit_raw_corpus.py \\
    --registry configs/laws/corpus_registry.yml \\
    --raw-dir data/raw \\
    --output artifacts/reports/audit/audit.json \\
    --min-html-size 5000
""",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path("configs/laws/corpus_registry.yml"),
        help="Path to corpus registry YAML (default: configs/laws/corpus_registry.yml)",
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path("data/raw"),
        help="Path to raw artifacts directory (default: data/raw)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/reports/audit/raw_corpus_audit.json"),
        help="Output JSON report path (default: artifacts/reports/audit/raw_corpus_audit.json)",
    )
    parser.add_argument(
        "--min-html-size",
        type=int,
        default=10000,
        help="Minimum HTML file size in bytes (default: 10000)",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print detailed per-artifact results"
    )

    args = parser.parse_args()

    try:
        report = run_raw_audit_pipeline(
            registry_path=args.registry,
            raw_dir=args.raw_dir,
            min_html_size=args.min_html_size,
            output_path=args.output,
        )

        summary = report["summary"]

        # Print compact summary
        print("\nRaw Corpus Audit Summary")
        print("------------------------")
        print(f"Registry entries:       {summary['registry_entries']:4d}")
        print(f"Raw artifacts found:   {summary['raw_artifacts_found']:4d}")
        print(f"Valid artifacts:       {summary['valid_artifacts']:4d}")
        print(f"Warning artifacts:     {summary['warning_artifacts']:4d}")
        print(f"Invalid artifacts:     {summary['invalid_artifacts']:4d}")
        print(f"Missing artifacts:     {summary['missing_artifacts']:4d}")
        print(f"Extra artifacts:       {summary['extra_artifacts']:4d}")
        print(f"\nReport: {args.output}")

        # Verbose output
        if args.verbose:
            print("\nPer-artifact details:")
            for item in report["items"]:
                status_icon = {"valid": "✓", "warning": "⚠", "invalid": "✗", "missing": "?"}.get(
                    item["status"], "?"
                )
                print(
                    f"  {status_icon} {item['law_id']:20s} {item['status']:10s} size={item['html_size_bytes']:>6d}"
                )
                if item["issues"]:
                    for issue in item["issues"]:
                        print(f"      ERROR: {issue}")
                if item["warnings"]:
                    for warning in item["warnings"]:
                        print(f"      WARN: {warning}")

        # Exit code: 0 if no invalid and no missing, 1 otherwise
        if summary["invalid_artifacts"] > 0 or summary["missing_artifacts"] > 0:
            print("\nAudit FAILED: critical issues found.")
            return 1
        else:
            print("\nAudit PASSED.")
            return 0

    except AuditError as e:
        print(f"Audit error: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
