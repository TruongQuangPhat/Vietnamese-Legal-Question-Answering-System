"""Run or compare the retrieval-quality generalization benchmark."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.evaluation.retrieval_quality_generalization import (  # noqa: E402
    DEFAULT_CANDIDATE_TOP_K,
    DEFAULT_CORPUS_PATH,
    DEFAULT_EVIDENCE_BUDGET,
    DEFAULT_RECALL_DEPTHS,
    compare_reports,
    load_json_report,
    run_sparse_selection_benchmark,
    write_json_report,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Run deterministic direct-evidence benchmark diagnostics or compare "
            "two machine-readable reports."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="run benchmark")
    run_parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    run_parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS_PATH)
    run_parser.add_argument("--candidate-top-k", type=int, default=DEFAULT_CANDIDATE_TOP_K)
    run_parser.add_argument("--evidence-budget", type=int, default=DEFAULT_EVIDENCE_BUDGET)
    run_parser.add_argument(
        "--recall-depth",
        action="append",
        type=int,
        dest="recall_depths",
        help="candidate depth for target recall; repeatable",
    )
    run_parser.add_argument("--output", type=Path, required=True)

    compare_parser = subparsers.add_parser("compare", help="compare reports")
    compare_parser.add_argument("--before", type=Path, required=True)
    compare_parser.add_argument("--after", type=Path, required=True)
    compare_parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the requested benchmark command."""
    args = build_parser().parse_args(argv)
    if args.command == "run":
        recall_depths = tuple(args.recall_depths or DEFAULT_RECALL_DEPTHS)
        report = run_sparse_selection_benchmark(
            repo_root=args.repo_root,
            corpus_path=args.corpus,
            candidate_top_k=args.candidate_top_k,
            evidence_budget=args.evidence_budget,
            recall_depths=recall_depths,
        )
        write_json_report(report, args.output)
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "case_count": report["case_count"],
                    "aggregate_metrics": report["aggregate_metrics"],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0

    comparison = compare_reports(load_json_report(args.before), load_json_report(args.after))
    write_json_report(comparison, args.output)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "regression_count": comparison["regression_count"],
                "largest_positive_rank_change": comparison["largest_positive_rank_change"],
                "largest_negative_rank_change": comparison["largest_negative_rank_change"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
