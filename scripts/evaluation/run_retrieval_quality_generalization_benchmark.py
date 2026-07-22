"""Run or compare the retrieval-quality generalization benchmark."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.evaluation.benchmark.direct_evidence import (  # noqa: E402
    DEFAULT_CORPUS_PATH,
    DEFAULT_DENSE_RETRIEVAL_TOP_K,
    DEFAULT_DIAGNOSTIC_CANDIDATE_TOP_K,
    DEFAULT_FUSION_OUTPUT_TOP_K,
    DEFAULT_RECALL_DEPTHS,
    DEFAULT_SELECTED_EVIDENCE_BUDGET,
    DEFAULT_SPARSE_RETRIEVAL_TOP_K,
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
    run_parser.add_argument(
        "--mode",
        choices=["runtime_aligned", "deep_diagnostic"],
        default="runtime_aligned",
        help="benchmark cutoff mode; runtime_aligned is production-representative",
    )
    run_parser.add_argument(
        "--sparse-retrieval-top-k",
        type=int,
        default=DEFAULT_SPARSE_RETRIEVAL_TOP_K,
    )
    run_parser.add_argument(
        "--dense-retrieval-top-k",
        type=int,
        default=DEFAULT_DENSE_RETRIEVAL_TOP_K,
    )
    run_parser.add_argument(
        "--diagnostic-candidate-top-k",
        type=int,
        default=DEFAULT_DIAGNOSTIC_CANDIDATE_TOP_K,
        help="retrieval pool retained for Recall@k, MRR, and rank diagnostics",
    )
    run_parser.add_argument(
        "--fusion-output-top-k",
        type=int,
        default=DEFAULT_FUSION_OUTPUT_TOP_K,
        help="production hybrid fusion output size recorded by the deterministic report",
    )
    run_parser.add_argument(
        "--selection-input-top-k",
        type=int,
        default=None,
        help="candidate count available to evidence selection; defaults depend on mode",
    )
    run_parser.add_argument(
        "--selected-evidence-budget",
        type=int,
        default=DEFAULT_SELECTED_EVIDENCE_BUDGET,
    )
    run_parser.add_argument(
        "--candidate-top-k",
        type=int,
        default=None,
        help="deprecated alias for --diagnostic-candidate-top-k",
    )
    run_parser.add_argument(
        "--evidence-budget",
        type=int,
        default=None,
        help="deprecated alias for --selected-evidence-budget",
    )
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
            mode=args.mode,
            sparse_retrieval_top_k=args.sparse_retrieval_top_k,
            dense_retrieval_top_k=args.dense_retrieval_top_k,
            diagnostic_candidate_top_k=args.diagnostic_candidate_top_k,
            fusion_output_top_k=args.fusion_output_top_k,
            selection_input_top_k=args.selection_input_top_k,
            selected_evidence_budget=args.selected_evidence_budget,
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
                    "benchmark_mode": report["benchmark_mode"],
                    "production_aligned": report["production_aligned"],
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
