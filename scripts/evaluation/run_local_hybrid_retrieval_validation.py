"""Run read-only local hybrid retrieval validation without generation."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.evaluation.benchmark.direct_evidence import (  # noqa: E402
    DIRECT_EVIDENCE_CASE_SET_IDENTITY,
    BenchmarkRuntimeConfig,
    build_report_metadata,
    compute_aggregate_metrics,
    evidence_target_from_mapping,
    parse_evidence_target,
    provision_summary,
    summary_matches_target,
    target_key,
    target_rank,
)
from src.retrieval.workflows.common import DEFAULT_CONFIG, load_retrieval_config  # noqa: E402
from src.retrieval.workflows.dense_retrieval import validate_cli_arguments  # noqa: E402

DEFAULT_CHUNKS_PATH = Path("data/processed/legal_chunks.jsonl")
DEFAULT_COLLECTION_NAME = "vnlaw_chunks_bgem3_v1_full"
DEFAULT_SPARSE_TOP_K = 50
DEFAULT_DENSE_TOP_K = 50
DEFAULT_FUSION_TOP_K = 10
DEFAULT_SELECTED_EVIDENCE_BUDGET = 5


def build_parser() -> argparse.ArgumentParser:
    """Build the read-only local hybrid validation CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Validate the local BGE-M3 -> Qdrant dense retrieval -> sparse retrieval -> "
            "hybrid fusion -> evidence selection -> prompt citation mapping path. "
            "This script is read-only and never calls an LLM."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--confirm-local-read-only",
        action="store_true",
        help="required safety confirmation before loading BGE-M3 or querying Qdrant",
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS_PATH)
    parser.add_argument("--question", default=None)
    parser.add_argument("--case-id", default="manual_question")
    parser.add_argument("--cases", type=Path, default=None, help="JSON or JSONL benchmark cases")
    parser.add_argument(
        "--expected-target",
        action="append",
        default=[],
        help="expected target for --question as law_id:article[:clause[:point]]",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--url", default=None, help="local Qdrant URL override")
    parser.add_argument("--collection-name", default=DEFAULT_COLLECTION_NAME)
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default=None)
    parser.add_argument("--sparse-top-k", type=int, default=DEFAULT_SPARSE_TOP_K)
    parser.add_argument("--dense-top-k", type=int, default=DEFAULT_DENSE_TOP_K)
    parser.add_argument("--fusion-top-k", type=int, default=DEFAULT_FUSION_TOP_K)
    parser.add_argument(
        "--selected-evidence-budget",
        type=int,
        default=DEFAULT_SELECTED_EVIDENCE_BUDGET,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the local hybrid validation command."""
    return asyncio.run(_main_async(argv))


async def _main_async(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.confirm_local_read_only:
        print("Refusing to run without --confirm-local-read-only.", file=sys.stderr)
        return 2
    try:
        _validate_args(args)
        cases = _load_cases(args)
        report = await _run_cases(args, cases)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"output": str(args.output), "case_count": len(cases)}, sort_keys=True))
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Local hybrid validation failed safely: {exc}", file=sys.stderr)
        return 1
    return 0


def _validate_args(args: argparse.Namespace) -> None:
    if bool(args.question) == bool(args.cases):
        raise ValueError("provide exactly one of --question or --cases")
    if args.question:
        validate_cli_arguments(
            query=args.question,
            top_k=args.dense_top_k,
            output_path=args.output,
            preview_chars=1,
        )
    for name in ("sparse_top_k", "dense_top_k", "fusion_top_k", "selected_evidence_budget"):
        if getattr(args, name) <= 0:
            raise ValueError(f"{name.replace('_', '-')} must be positive")
    if args.selected_evidence_budget > args.fusion_top_k:
        raise ValueError("selected evidence budget cannot exceed fusion top-k")


def _load_cases(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.question:
        return [
            {
                "case_id": args.case_id,
                "query": args.question,
                "expected_targets": [parse_evidence_target(item) for item in args.expected_target],
            }
        ]
    assert args.cases is not None
    if args.cases.suffix.lower() == ".jsonl":
        return [
            _normalize_case(json.loads(line))
            for line in args.cases.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    payload = json.loads(args.cases.read_text(encoding="utf-8"))
    rows = payload["cases"] if isinstance(payload, dict) and "cases" in payload else payload
    if not isinstance(rows, list):
        raise ValueError("case file must contain a list or an object with a cases list")
    return [_normalize_case(item) for item in rows]


def _normalize_case(item: dict[str, Any]) -> dict[str, Any]:
    query = item.get("query") or item.get("question")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("each case requires query or question")
    raw_targets = item.get("expected_targets") or []
    return {
        "case_id": str(item.get("case_id") or item.get("id") or "case"),
        "query": query,
        "expected_targets": [
            parse_evidence_target(target)
            if isinstance(target, str)
            else evidence_target_from_mapping(target)
            for target in raw_targets
        ],
    }


async def _run_cases(args: argparse.Namespace, cases: list[dict[str, Any]]) -> dict[str, Any]:
    from src.indexing.embedding_model import BgeM3EmbeddingModel
    from src.indexing.qdrant_collection import build_qdrant_client
    from src.retrieval.coverage_aware import CoverageAwareFusionConfig, CoverageAwareQuotaRetriever
    from src.retrieval.dense_retriever import DenseRetriever
    from src.retrieval.evidence import ContextAssemblyConfig, build_evidence_bundle
    from src.retrieval.prompting import build_naive_rag_prompt
    from src.retrieval.selection import EvidenceSelectionConfig, select_evidence_for_answer
    from src.retrieval.sparse_retriever import SparseBM25Retriever

    config = load_retrieval_config(args.config)
    qdrant_url = args.url or config.qdrant.url
    api_key = os.getenv("LEGAL_QA_QDRANT_API_KEY") or os.getenv("QDRANT_API_KEY")
    model_path = os.getenv("EMBEDDING_MODEL_PATH") or os.getenv("LEGAL_QA_EMBEDDING_MODEL_PATH")
    model_name = model_path or config.embedding.model_name
    client = build_qdrant_client(
        url=qdrant_url,
        timeout_seconds=config.qdrant.timeout_seconds,
        api_key=api_key,
    )
    try:
        collection_info = await client.get_collection(args.collection_name)
        embedding_model = BgeM3EmbeddingModel(
            model_name=model_name,
            model_revision=None if model_path else config.embedding.model_revision,
            device=args.device or config.embedding.device,
            normalize_embeddings=config.embedding.normalize_embeddings,
            max_length=config.embedding.max_length,
            dense_vector_name=config.dense_retrieval.vector_name,
            require_local_files=bool(model_path),
        )
        dense = DenseRetriever(
            qdrant_client=client,
            embedding_model=embedding_model,
            collection_name=args.collection_name,
            dense_vector_name=config.dense_retrieval.vector_name,
            expected_vector_dim=config.dense_retrieval.expected_vector_dim,
            default_top_k=args.dense_top_k,
            embedding_batch_size=config.embedding.batch_size,
        )
        sparse = SparseBM25Retriever.from_jsonl(args.chunks, default_top_k=args.sparse_top_k)
        retriever = CoverageAwareQuotaRetriever(
            dense_retriever=dense,
            sparse_retriever=sparse,
            config=CoverageAwareFusionConfig(
                config_id="selected_coverage_aware_quota",
                mode="quota",
                dense_candidate_k=args.dense_top_k,
                sparse_candidate_k=args.sparse_top_k,
                final_top_k=args.fusion_top_k,
                rrf_k=60,
                dense_weight=1.0,
                sparse_weight=1.5,
                fused_best=5,
                sparse_quota=4,
                dense_quota=1,
            ),
            collection_name=args.collection_name,
            vector_name=config.dense_retrieval.vector_name,
        )
        case_results = []
        for case in cases:
            case_results.append(
                await _run_one_case(
                    case,
                    retriever=retriever,
                    dense=dense,
                    sparse=sparse,
                    context_config=ContextAssemblyConfig(max_packets=args.fusion_top_k),
                    selection_config=EvidenceSelectionConfig(
                        max_selected_packets=args.selected_evidence_budget
                    ),
                    fusion_top_k=args.fusion_top_k,
                    prompt_builder=build_naive_rag_prompt,
                    bundle_builder=build_evidence_bundle,
                    selector=select_evidence_for_answer,
                )
            )
        runtime_config = BenchmarkRuntimeConfig(
            mode="runtime_aligned",
            sparse_retrieval_top_k=args.sparse_top_k,
            dense_retrieval_top_k=args.dense_top_k,
            diagnostic_candidate_top_k=max(args.sparse_top_k, args.dense_top_k),
            fusion_output_top_k=args.fusion_top_k,
            selection_input_top_k=args.fusion_top_k,
            selected_evidence_budget=args.selected_evidence_budget,
            production_aligned=(
                args.sparse_top_k == DEFAULT_SPARSE_TOP_K
                and args.dense_top_k == DEFAULT_DENSE_TOP_K
                and args.fusion_top_k == DEFAULT_FUSION_TOP_K
                and args.selected_evidence_budget == DEFAULT_SELECTED_EVIDENCE_BUDGET
            ),
        )
        per_case = [
            _case_metrics_row(item, selection_input_top_k=args.fusion_top_k)
            for item in case_results
        ]
        metadata = build_report_metadata(
            git_revision=None,
            corpus_identity=str(args.chunks),
            case_set_identity=DIRECT_EVIDENCE_CASE_SET_IDENTITY,
            pipeline_family="direct_evidence",
            evaluation_stage="local_hybrid_read_only_validation",
            retrieval_mode="hybrid",
            runtime_config=runtime_config,
            warnings=(),
            limitations=("manual local validation requires user-provided BGE-M3 and Qdrant",),
        )
        report = {
            "validation_type": "local_read_only_hybrid_retrieval",
            "collection_name": args.collection_name,
            "collection_metadata": _safe_collection_summary(collection_info),
            "vector_name": config.dense_retrieval.vector_name,
            "expected_vector_dim": config.dense_retrieval.expected_vector_dim,
            "sparse_top_k": args.sparse_top_k,
            "dense_top_k": args.dense_top_k,
            "fusion_top_k": args.fusion_top_k,
            "selected_evidence_budget": args.selected_evidence_budget,
            "aggregate_metrics": compute_aggregate_metrics(per_case),
            "cases": case_results,
        }
        report.update(metadata.to_dict())
        return report
    finally:
        await client.close()


async def _run_one_case(
    case: dict[str, Any],
    *,
    retriever: Any,
    dense: Any,
    sparse: Any,
    context_config: Any,
    selection_config: Any,
    fusion_top_k: int,
    prompt_builder: Any,
    bundle_builder: Any,
    selector: Any,
) -> dict[str, Any]:
    dense_result = await dense.retrieve(case["query"], top_k=dense.default_top_k)
    sparse_result = await sparse.retrieve(case["query"], top_k=sparse.default_top_k)
    fused = await retriever.retrieve(query=case["query"], top_k=fusion_top_k)
    bundle = bundle_builder(fused, config=context_config)
    selection = selector(bundle, config=selection_config)
    prompt = prompt_builder(query=case["query"], selection_result=selection)
    targets = case["expected_targets"]
    selected = [
        provision_summary(item.packet, rank=index)
        for index, item in enumerate(selection.selected_evidence, start=1)
    ]
    citations = [
        provision_summary(item, rank=index) for index, item in enumerate(prompt.evidence, start=1)
    ]
    primary_target = targets[0] if targets else None
    direct_primary_pass = bool(
        primary_target and selected and summary_matches_target(selected[0], primary_target)
    )
    multi_pass = all(
        any(summary_matches_target(item, target) for item in selected)
        and any(summary_matches_target(item, target) for item in citations)
        for target in targets
    )
    return {
        "case_id": case["case_id"],
        "question": case["query"],
        "expected_targets": [target.to_dict() for target in targets],
        "sparse_target_rank": {
            target_key(target): target_rank(sparse_result.results, target) for target in targets
        },
        "dense_target_rank": {
            target_key(target): target_rank(dense_result.results, target) for target in targets
        },
        "fused_target_rank": {
            target_key(target): target_rank(fused.results, target) for target in targets
        },
        "fused_top10_law_article_clause_set": [
            provision_summary(item, rank=item.rank) for item in fused.results
        ],
        "selected_evidence_set": selected,
        "citation_set": citations,
        "direct_primary_pass": direct_primary_pass,
        "multi_article_coverage_pass": multi_pass,
        "warnings": [warning.model_dump(mode="json") for warning in selection.warnings],
        "fallback_metadata": {
            "decision": selection.decision,
            "fallback_reasons": [
                reason.model_dump(mode="json") for reason in selection.fallback_reasons
            ],
        },
        "pass_reason": "pass"
        if direct_primary_pass and multi_pass
        else "primary or coverage mismatch",
    }


def _case_metrics_row(
    case: dict[str, Any],
    *,
    selection_input_top_k: int,
) -> dict[str, Any]:
    """Convert local-hybrid diagnostics into canonical aggregate-metric input."""
    target_rows = []
    for target in case["expected_targets"]:
        target_row = dict(target)
        key = target_key(evidence_target_from_mapping(target))
        rank = case["fused_target_rank"].get(key)
        target_row.update(
            {
                "target_key": key,
                "candidate_rank": rank,
                "selection_input_rank": rank
                if rank is not None and rank <= selection_input_top_k
                else None,
                "available_to_selection": rank is not None and rank <= selection_input_top_k,
            }
        )
        target_rows.append(target_row)
    return {
        "case_id": case["case_id"],
        "expected_targets": target_rows,
        "primary_evidence_accuracy": case["direct_primary_pass"],
        "citation_alignment_accuracy": case["multi_article_coverage_pass"],
        "cross_reference_only_primary_error": False,
        "wrong_actor_primary_error": False,
        "wrong_domain_primary_error": False,
        "multi_article_coverage_accuracy": case["multi_article_coverage_pass"]
        if len(target_rows) > 1
        else None,
        "pass": case["direct_primary_pass"] and case["multi_article_coverage_pass"],
    }


def _safe_collection_summary(collection_info: Any) -> dict[str, Any]:
    payload = (
        collection_info.model_dump(mode="json") if hasattr(collection_info, "model_dump") else {}
    )
    config = payload.get("config") or {}
    params = config.get("params") or {}
    vectors = params.get("vectors") or {}
    return {
        "status": payload.get("status"),
        "points_count": payload.get("points_count"),
        "vectors_count": payload.get("vectors_count"),
        "vectors": vectors,
    }


if __name__ == "__main__":
    raise SystemExit(main())
