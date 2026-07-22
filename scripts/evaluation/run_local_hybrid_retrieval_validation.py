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

from scripts.retrieval.run_dense_retrieval import validate_cli_arguments  # noqa: E402
from src.retrieval.workflows.common import DEFAULT_CONFIG, load_retrieval_config  # noqa: E402

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
                "expected_targets": [_parse_target(item) for item in args.expected_target],
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
            _parse_target(target) if isinstance(target, str) else _target_from_mapping(target)
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
        return {
            "schema_version": "1.0",
            "validation_type": "local_read_only_hybrid_retrieval",
            "collection_name": args.collection_name,
            "collection_metadata": _safe_collection_summary(collection_info),
            "vector_name": config.dense_retrieval.vector_name,
            "expected_vector_dim": config.dense_retrieval.expected_vector_dim,
            "sparse_top_k": args.sparse_top_k,
            "dense_top_k": args.dense_top_k,
            "fusion_top_k": args.fusion_top_k,
            "selected_evidence_budget": args.selected_evidence_budget,
            "cases": case_results,
        }
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
        _summary(item.packet, rank=index)
        for index, item in enumerate(selection.selected_evidence, start=1)
    ]
    citations = [_summary(item, rank=index) for index, item in enumerate(prompt.evidence, start=1)]
    primary_target = targets[0] if targets else None
    direct_primary_pass = bool(
        primary_target and selected and _matches(selected[0], primary_target)
    )
    multi_pass = all(
        any(_matches(item, target) for item in selected)
        and any(_matches(item, target) for item in citations)
        for target in targets
    )
    return {
        "case_id": case["case_id"],
        "question": case["query"],
        "expected_targets": targets,
        "sparse_target_rank": {
            target_key(target): _target_rank(sparse_result.results, target) for target in targets
        },
        "dense_target_rank": {
            target_key(target): _target_rank(dense_result.results, target) for target in targets
        },
        "fused_target_rank": {
            target_key(target): _target_rank(fused.results, target) for target in targets
        },
        "fused_top10_law_article_clause_set": [
            _summary(item, rank=item.rank) for item in fused.results
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


def _parse_target(raw: str) -> dict[str, str | None]:
    parts = [part.strip() for part in raw.split(":")]
    if len(parts) < 2 or len(parts) > 4 or not all(parts[:2]):
        raise ValueError("expected target format is law_id:article[:clause[:point]]")
    return {
        "law_id": parts[0],
        "article_number": parts[1],
        "clause_number": parts[2] if len(parts) >= 3 and parts[2] else None,
        "point_label": parts[3] if len(parts) >= 4 and parts[3] else None,
    }


def _target_from_mapping(raw: dict[str, Any]) -> dict[str, str | None]:
    return {
        "law_id": str(raw["law_id"]),
        "article_number": str(raw["article_number"]),
        "clause_number": str(raw["clause_number"]) if raw.get("clause_number") else None,
        "point_label": str(raw["point_label"]) if raw.get("point_label") else None,
    }


def _summary(item: Any, *, rank: int) -> dict[str, Any]:
    return {
        "rank": rank,
        "chunk_id": getattr(item, "chunk_id", None),
        "law_id": getattr(item, "law_id", None),
        "article_number": getattr(item, "article_number", None),
        "clause_number": getattr(item, "clause_number", None),
        "point_label": getattr(item, "point_label", None),
        "citation": getattr(item, "citation", None),
    }


def _target_rank(candidates: list[Any], target: dict[str, str | None]) -> int | None:
    for candidate in candidates:
        if _object_matches(candidate, target):
            return candidate.rank
    return None


def _matches(summary: dict[str, Any], target: dict[str, str | None]) -> bool:
    return (
        summary["law_id"] == target["law_id"]
        and summary["article_number"] == target["article_number"]
        and (target["clause_number"] is None or summary["clause_number"] == target["clause_number"])
        and (target["point_label"] is None or summary["point_label"] == target["point_label"])
    )


def _object_matches(item: Any, target: dict[str, str | None]) -> bool:
    return (
        getattr(item, "law_id", None) == target["law_id"]
        and getattr(item, "article_number", None) == target["article_number"]
        and (
            target["clause_number"] is None
            or getattr(item, "clause_number", None) == target["clause_number"]
        )
        and (
            target["point_label"] is None
            or getattr(item, "point_label", None) == target["point_label"]
        )
    )


def target_key(target: dict[str, str | None]) -> str:
    parts = [target["law_id"] or "", f"Điều {target['article_number']}"]
    if target["clause_number"]:
        parts.append(f"Khoản {target['clause_number']}")
    if target["point_label"]:
        parts.append(f"Điểm {target['point_label']}")
    return " / ".join(parts)


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
