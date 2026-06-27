from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from src.evaluation.benchmark.enums import (
    BenchmarkSplit,
    EvidenceGroupRequirement,
    ExpectedDecision,
    LegalDomain,
    MatchLevel,
    QuestionType,
    RelevanceLevel,
    ReviewStage,
    ReviewStatus,
    TargetRole,
)
from src.evaluation.benchmark.fingerprinting import create_benchmark_manifest
from src.evaluation.benchmark.loader import (
    BenchmarkFileSet,
    load_benchmark_dataset,
    load_benchmark_manifest,
    load_split_manifest,
)
from src.evaluation.benchmark.schemas import BenchmarkConfig
from src.evaluation.benchmark.splitting import create_grouped_split
from src.evaluation.benchmark.validator import BenchmarkValidator
from src.indexing.official_artifacts import write_json_atomic


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def test_synthetic_benchmark_workflow(tmp_path: Path) -> None:
    config = BenchmarkConfig(
        schema_version="1.0",
        benchmark_version="synthetic_test",
        development_ratio=0.5,
        split_seed=11,
        grouping_fields=["case_family_id", "source_provision_group_id"],
        stratification_fields=["primary_domain", "expected_decision", "question_types"],
    )
    queries = tmp_path / "queries.jsonl"
    targets = tmp_path / "targets.jsonl"
    judgments = tmp_path / "judgments.jsonl"
    groups = tmp_path / "groups.jsonl"
    reviews = tmp_path / "reviews.jsonl"
    registry = tmp_path / "registry.yml"
    chunks = tmp_path / "chunks.jsonl"
    split_path = tmp_path / "split.json"
    manifest_path = tmp_path / "manifest.json"

    _write_jsonl(
        queries,
        [
            {
                "id": "q1",
                "query": "Synthetic question one?",
                "primary_domain": LegalDomain.CIVIL_FAMILY_IDENTITY.value,
                "question_types": [QuestionType.SINGLE_ARTICLE_LOOKUP.value],
                "expected_decision": ExpectedDecision.ANSWER_ALLOWED.value,
                "complete_evidence_required": True,
                "review_status": ReviewStatus.FROZEN.value,
                "reviewer_notes": "Synthetic fixture.",
                "split": BenchmarkSplit.DEVELOPMENT.value,
            },
            {
                "id": "q2",
                "query": "Synthetic question two?",
                "primary_domain": LegalDomain.CIVIL_FAMILY_IDENTITY.value,
                "question_types": [QuestionType.SINGLE_ARTICLE_LOOKUP.value],
                "expected_decision": ExpectedDecision.ANSWER_ALLOWED.value,
                "complete_evidence_required": True,
                "review_status": ReviewStatus.FROZEN.value,
                "reviewer_notes": "Synthetic fixture.",
                "split": BenchmarkSplit.HELD_OUT_TEST.value,
            },
        ],
    )
    _write_jsonl(
        targets,
        [
            _target("q1", "t1", "chunk_1"),
            _target("q2", "t2", "chunk_2"),
        ],
    )
    _write_jsonl(
        judgments,
        [
            _judgment("q1", "chunk_1"),
            _judgment("q2", "chunk_2"),
        ],
    )
    _write_jsonl(
        groups,
        [
            _group("q1", "chunk_1"),
            _group("q2", "chunk_2"),
        ],
    )
    _write_jsonl(
        reviews,
        [
            _review(
                "q1", ReviewStage.PRIMARY_ANNOTATION, "q1_primary", ReviewStatus.PRIMARY_REVIEWED
            ),
            _review(
                "q1",
                ReviewStage.INDEPENDENT_REVIEW,
                "q1_independent",
                ReviewStatus.INDEPENDENT_REVIEWED,
            ),
            _review(
                "q2", ReviewStage.PRIMARY_ANNOTATION, "q2_primary", ReviewStatus.PRIMARY_REVIEWED
            ),
            _review(
                "q2",
                ReviewStage.INDEPENDENT_REVIEW,
                "q2_independent",
                ReviewStatus.INDEPENDENT_REVIEWED,
            ),
        ],
    )
    registry.write_text("corpus:\n  - law_id: LAW_A\n", encoding="utf-8")
    _write_jsonl(
        chunks,
        [
            _chunk("chunk_1"),
            _chunk("chunk_2"),
        ],
    )

    file_set = BenchmarkFileSet(
        queries=queries,
        legal_targets=targets,
        evidence_judgments=judgments,
        evidence_groups=groups,
        review_records=reviews,
    )
    dataset = load_benchmark_dataset(file_set)
    report = BenchmarkValidator(config=config).validate(
        dataset,
        corpus_registry_path=registry,
        processed_chunks_path=chunks,
    )
    assert report.status == "validation_passed"

    plan = create_grouped_split(dataset.queries, config=config)
    assignments = {
        "q1": BenchmarkSplit.DEVELOPMENT,
        "q2": BenchmarkSplit.HELD_OUT_TEST,
    }
    split_manifest = plan.manifest.model_copy(update={"assignments": assignments})
    write_json_atomic(split_path, split_manifest.model_dump(mode="json"))
    reloaded_split = load_split_manifest(split_path)
    assert reloaded_split.assignments == assignments

    manifest = create_benchmark_manifest(
        file_set=file_set,
        config=config,
        split_manifest_path=split_path,
        corpus_registry_path=registry,
        processed_chunks_path=chunks,
        output_path=manifest_path,
        change_log=["Synthetic freeze fixture."],
    )
    reloaded_manifest = load_benchmark_manifest(manifest_path)
    assert reloaded_manifest.benchmark_version == manifest.benchmark_version
    assert reloaded_manifest.record_counts["queries"] == 2


def _target(query_id: str, target_id: str, _chunk_id: str) -> dict[str, object]:
    return {
        "id": target_id,
        "query_id": query_id,
        "law_id": "LAW_A",
        "document_title": "Synthetic Law",
        "article_number": "1",
        "match_level": MatchLevel.ARTICLE.value,
        "target_role": TargetRole.REQUIRED.value,
    }


def _judgment(query_id: str, chunk_id: str) -> dict[str, object]:
    return {
        "query_id": query_id,
        "chunk_id": chunk_id,
        "relevance": RelevanceLevel.REQUIRED_DIRECT.value,
        "evidence_group_ids": ["g1"],
    }


def _group(query_id: str, chunk_id: str) -> dict[str, object]:
    return {
        "query_id": query_id,
        "evidence_group_id": "g1",
        "requirement": EvidenceGroupRequirement.REQUIRED.value,
        "minimum_hits": 1,
        "acceptable_chunk_ids": [chunk_id],
        "acceptable_legal_targets": [
            {
                "law_id": "LAW_A",
                "article_number": "1",
                "match_level": MatchLevel.ARTICLE.value,
            }
        ],
    }


def _review(
    query_id: str,
    review_step: ReviewStage,
    record_id: str,
    status: ReviewStatus,
) -> dict[str, object]:
    return {
        "id": record_id,
        "query_id": query_id,
        "review_stage": review_step.value,
        "reviewer_id": f"reviewer_{record_id}",
        "status": status.value,
        "reviewed_fields": ["expected_decision", "legal_targets"],
        "reviewed_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
    }


def _chunk(chunk_id: str) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "law_id": "LAW_A",
        "article_number": "1",
        "clause_number": None,
        "point_label": None,
        "level": "article",
    }
