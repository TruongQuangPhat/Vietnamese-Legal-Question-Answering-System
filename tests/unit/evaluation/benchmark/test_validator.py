from __future__ import annotations

import json
from datetime import datetime
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
from src.evaluation.benchmark.loader import LoadedBenchmarkDataset
from src.evaluation.benchmark.schemas import (
    BenchmarkConfig,
    BenchmarkQuery,
    EvidenceGroup,
    EvidenceJudgment,
    LegalTarget,
    LegalTargetReference,
    ReviewRecord,
    SplitManifest,
)
from src.evaluation.benchmark.validator import BenchmarkValidator, official_duplicate_key


def _config() -> BenchmarkConfig:
    return BenchmarkConfig(
        schema_version="1.0",
        development_ratio=0.7,
        split_seed=7,
        grouping_fields=["case_family_id", "source_provision_group_id"],
        stratification_fields=["primary_domain", "question_types"],
    )


def _query(**updates: object) -> BenchmarkQuery:
    payload = {
        "id": "q1",
        "query": "Synthetic legal question?",
        "primary_domain": LegalDomain.CIVIL_FAMILY_IDENTITY,
        "question_types": [QuestionType.SINGLE_ARTICLE_LOOKUP],
        "expected_decision": ExpectedDecision.ANSWER_ALLOWED,
        "reviewer_notes": "Synthetic fixture.",
        "review_status": ReviewStatus.FROZEN,
        "split": BenchmarkSplit.DEVELOPMENT,
    }
    payload.update(updates)
    return BenchmarkQuery.model_validate(payload)


def _target(query_id: str = "q1", **updates: object) -> LegalTarget:
    payload = {
        "id": f"target_{query_id}",
        "query_id": query_id,
        "law_id": "LAW_A",
        "document_title": "Synthetic Law",
        "article_number": "1",
        "match_level": MatchLevel.ARTICLE,
        "target_role": TargetRole.REQUIRED,
    }
    payload.update(updates)
    return LegalTarget.model_validate(payload)


def _group(query_id: str = "q1", **updates: object) -> EvidenceGroup:
    payload = {
        "query_id": query_id,
        "evidence_group_id": "g1",
        "requirement": EvidenceGroupRequirement.REQUIRED,
        "minimum_hits": 1,
        "acceptable_chunk_ids": ["chunk_a"],
        "acceptable_legal_targets": [
            LegalTargetReference(
                law_id="LAW_A",
                article_number="1",
                match_level=MatchLevel.ARTICLE,
            )
        ],
    }
    payload.update(updates)
    return EvidenceGroup.model_validate(payload)


def _judgment(
    query_id: str = "q1",
    relevance: RelevanceLevel = RelevanceLevel.REQUIRED_DIRECT,
    **updates: object,
) -> EvidenceJudgment:
    payload = {
        "query_id": query_id,
        "chunk_id": "chunk_a",
        "relevance": relevance,
        "evidence_group_ids": ["g1"],
    }
    payload.update(updates)
    return EvidenceJudgment.model_validate(payload)


def _review(
    stage: ReviewStage,
    query_id: str = "q1",
    status: ReviewStatus = ReviewStatus.PRIMARY_REVIEWED,
    **updates: object,
) -> ReviewRecord:
    payload = {
        "id": f"{query_id}_{stage.value}",
        "query_id": query_id,
        "review_stage": stage,
        "reviewer_id": f"reviewer_{stage.value}",
        "status": status,
        "reviewed_fields": ["expected_decision"],
        "reviewed_at": datetime(2026, 1, 1),
    }
    payload.update(updates)
    return ReviewRecord.model_validate(payload)


def _dataset(
    *,
    queries: list[BenchmarkQuery] | None = None,
    targets: list[LegalTarget] | None = None,
    judgments: list[EvidenceJudgment] | None = None,
    groups: list[EvidenceGroup] | None = None,
    reviews: list[ReviewRecord] | None = None,
) -> LoadedBenchmarkDataset:
    return LoadedBenchmarkDataset(
        queries=queries if queries is not None else [_query()],
        legal_targets=targets if targets is not None else [_target()],
        evidence_judgments=judgments if judgments is not None else [_judgment()],
        evidence_groups=groups if groups is not None else [_group()],
        review_records=reviews
        if reviews is not None
        else [
            _review(ReviewStage.PRIMARY_ANNOTATION),
        ],
        checked_files=[],
    )


def _error_codes(report: object) -> set[str]:
    return {issue.code for issue in report.errors}


def test_orphan_references_fail() -> None:
    dataset = _dataset(targets=[_target(query_id="missing")])
    report = BenchmarkValidator(config=_config()).validate(dataset)
    assert "orphan_legal_target" in _error_codes(report)


def test_answer_allowed_without_direct_evidence_fails_when_frozen() -> None:
    dataset = _dataset(judgments=[])
    report = BenchmarkValidator(config=_config()).validate(dataset)
    assert "answer_allowed_missing_direct_evidence" in _error_codes(report)


def test_supporting_evidence_cannot_complete_required_group() -> None:
    dataset = _dataset(judgments=[_judgment(relevance=RelevanceLevel.SUPPORTING)])
    report = BenchmarkValidator(config=_config()).validate(dataset)
    assert "non_direct_evidence_group_completion" in _error_codes(report)


def test_frozen_answer_allowed_without_chunk_ids_fails() -> None:
    dataset = _dataset(
        groups=[
            _group(
                acceptable_chunk_ids=[],
                acceptable_legal_targets=[
                    LegalTargetReference(
                        law_id="LAW_A",
                        article_number="1",
                        match_level=MatchLevel.ARTICLE,
                    )
                ],
            )
        ]
    )
    report = BenchmarkValidator(config=_config()).validate(dataset)
    assert "frozen_required_group_missing_chunk_qrels" in _error_codes(report)


def test_unresolved_conflict_cannot_freeze() -> None:
    dataset = _dataset(
        reviews=[
            _review(ReviewStage.PRIMARY_ANNOTATION),
            _review(
                ReviewStage.INDEPENDENT_REVIEW,
                status=ReviewStatus.CONFLICT,
                disagreements=["expected_decision"],
            ),
        ]
    )
    report = BenchmarkValidator(config=_config()).validate(dataset)
    assert "frozen_has_unresolved_conflict" in _error_codes(report)
    assert "disagreement_without_adjudication" in _error_codes(report)


def test_held_out_without_independent_review_fails() -> None:
    dataset = _dataset(queries=[_query(split=BenchmarkSplit.HELD_OUT_TEST)])
    report = BenchmarkValidator(config=_config()).validate(dataset)
    assert "held_out_missing_independent_review" in _error_codes(report)


def test_regression_overlap_in_held_out_fails() -> None:
    query = _query(
        id="q_reg",
        query="Known regression query?",
        review_status=ReviewStatus.PRIMARY_REVIEWED,
        split=BenchmarkSplit.HELD_OUT_TEST,
    )
    report = BenchmarkValidator(
        config=_config(),
        regression_query_texts={official_duplicate_key("Known regression query?")},
    ).validate(_dataset(queries=[query], targets=[], judgments=[], groups=[], reviews=[]))
    assert "regression_overlap_in_held_out" in _error_codes(report)


def test_fallback_consistency_is_schema_enforced() -> None:
    try:
        _query(question_types=[QuestionType.FALLBACK])
    except ValueError as exc:
        assert "fallback decision" in str(exc)


def test_corpus_law_and_chunk_mismatch_using_temp_fixtures(tmp_path: Path) -> None:
    registry = tmp_path / "registry.yml"
    registry.write_text("corpus:\n  - law_id: LAW_A\n", encoding="utf-8")
    chunks = tmp_path / "chunks.jsonl"
    chunks.write_text(
        json.dumps(
            {
                "chunk_id": "chunk_a",
                "law_id": "LAW_B",
                "article_number": "9",
                "clause_number": None,
                "point_label": None,
                "level": "article",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    report = BenchmarkValidator(config=_config()).validate(
        _dataset(),
        corpus_registry_path=registry,
        processed_chunks_path=chunks,
    )
    assert "chunk_group_hierarchy_mismatch" in _error_codes(report)


def test_complete_list_requires_explicit_completeness() -> None:
    query = _query(
        question_types=[QuestionType.COMPLETE_LIST],
        review_status=ReviewStatus.PRIMARY_REVIEWED,
    )
    report = BenchmarkValidator(config=_config()).validate(
        _dataset(queries=[query], reviews=[]),
    )
    assert "complete_list_requires_completeness" in _error_codes(report)


def test_acceptable_chunk_requires_matching_direct_judgment() -> None:
    dataset = _dataset(judgments=[_judgment(relevance=RelevanceLevel.SUPPORTING)])
    report = BenchmarkValidator(config=_config()).validate(dataset)
    assert "acceptable_chunk_not_direct_for_group" in _error_codes(report)


def test_minimum_hits_must_not_exceed_direct_acceptable_chunks() -> None:
    dataset = _dataset(groups=[_group(minimum_hits=3, acceptable_chunk_ids=["chunk_a", "chunk_b"])])
    report = BenchmarkValidator(config=_config()).validate(dataset)
    assert "minimum_hits_exceeds_direct_chunks" in _error_codes(report)


def test_direct_judgment_must_be_listed_as_acceptable_chunk() -> None:
    dataset = _dataset(
        groups=[_group(acceptable_chunk_ids=["chunk_other"])],
        judgments=[_judgment(chunk_id="chunk_a")],
    )
    report = BenchmarkValidator(config=_config()).validate(dataset)
    assert "direct_judgment_chunk_not_acceptable" in _error_codes(report)


def test_contradictory_evidence_judgments_fail() -> None:
    dataset = _dataset(
        judgments=[
            _judgment(relevance=RelevanceLevel.REQUIRED_DIRECT),
            _judgment(relevance=RelevanceLevel.SUPPORTING),
        ]
    )
    report = BenchmarkValidator(config=_config()).validate(dataset)
    assert "contradictory_evidence_judgment" in _error_codes(report)


def test_review_summary_requires_matching_review_record() -> None:
    query = _query(review_status=ReviewStatus.INDEPENDENT_REVIEWED)
    report = BenchmarkValidator(config=_config()).validate(
        _dataset(queries=[query], reviews=[_review(ReviewStage.PRIMARY_ANNOTATION)])
    )
    assert "review_summary_missing_independent_record" in _error_codes(report)


def test_adjudicated_summary_requires_adjudication_record() -> None:
    query = _query(review_status=ReviewStatus.ADJUDICATED)
    report = BenchmarkValidator(config=_config()).validate(
        _dataset(queries=[query], reviews=[_review(ReviewStage.PRIMARY_ANNOTATION)])
    )
    assert "review_summary_missing_adjudication_record" in _error_codes(report)


def test_contradictory_review_records_fail() -> None:
    report = BenchmarkValidator(config=_config()).validate(
        _dataset(
            reviews=[
                _review(ReviewStage.INDEPENDENT_REVIEW, status=ReviewStatus.CONFLICT),
                _review(
                    ReviewStage.INDEPENDENT_REVIEW,
                    status=ReviewStatus.INDEPENDENT_REVIEWED,
                    id="q1_independent_review_second",
                    reviewer_id="reviewer_b",
                ),
            ]
        )
    )
    assert "contradictory_review_records" in _error_codes(report)


def test_split_manifest_assignment_is_canonical_for_regression_overlap() -> None:
    query = _query(
        id="q_reg",
        query="Known regression query?",
        review_status=ReviewStatus.PRIMARY_REVIEWED,
        split=BenchmarkSplit.DEVELOPMENT,
    )
    split_manifest = SplitManifest(
        schema_version="1.0",
        benchmark_version="draft",
        strategy="connected_component_grouped_split",
        seed=1,
        development_ratio=0.5,
        grouping_fields=["case_family_id", "source_provision_group_id"],
        input_fingerprint="a" * 64,
        assignments={"q_reg": BenchmarkSplit.HELD_OUT_TEST},
        created_at=datetime(2026, 1, 1),
    )
    report = BenchmarkValidator(
        config=_config(),
        regression_query_texts={official_duplicate_key("Known regression query?")},
    ).validate(
        _dataset(queries=[query], targets=[], judgments=[], groups=[], reviews=[]),
        split_manifest=split_manifest,
    )
    assert "regression_overlap_assignment_in_held_out" in _error_codes(report)
