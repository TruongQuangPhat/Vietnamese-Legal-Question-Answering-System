from __future__ import annotations

from datetime import date, datetime

import pytest
from pydantic import ValidationError

from src.evaluation.benchmark.enums import (
    AmbiguityCategory,
    BenchmarkSplit,
    EvidenceGroupRequirement,
    ExpectedDecision,
    FallbackReason,
    LegalDomain,
    MatchLevel,
    QuestionType,
    RelevanceLevel,
    ReviewStage,
    ReviewStatus,
    TargetRole,
)
from src.evaluation.benchmark.schemas import (
    BenchmarkConfig,
    BenchmarkManifest,
    BenchmarkQuery,
    EvidenceGroup,
    EvidenceJudgment,
    LegalTarget,
    LegalTargetReference,
    ReviewRecord,
    SplitManifest,
    TemporalMetadata,
)


def _query(**updates: object) -> BenchmarkQuery:
    payload = {
        "id": "q1",
        "query": "Synthetic legal question?",
        "primary_domain": LegalDomain.CIVIL_FAMILY_IDENTITY,
        "question_types": [QuestionType.SINGLE_ARTICLE_LOOKUP],
        "expected_decision": ExpectedDecision.ANSWER_ALLOWED,
        "reviewer_notes": "Synthetic fixture.",
    }
    payload.update(updates)
    return BenchmarkQuery.model_validate(payload)


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        _query(extra_field="not allowed")


def test_invalid_enum_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _query(primary_domain="not_a_domain")


def test_duplicate_list_values_are_rejected() -> None:
    with pytest.raises(ValidationError, match="question_types"):
        _query(question_types=[QuestionType.PARAPHRASE, QuestionType.PARAPHRASE])


def test_fallback_invariants_are_bidirectional() -> None:
    with pytest.raises(ValidationError, match="fallback decision"):
        _query(expected_decision=ExpectedDecision.FALLBACK_REQUIRED)
    with pytest.raises(ValidationError, match="fallback decision"):
        _query(question_types=[QuestionType.FALLBACK])

    query = _query(
        expected_decision=ExpectedDecision.FALLBACK_REQUIRED,
        question_types=[QuestionType.FALLBACK],
        fallback_reason=FallbackReason.OUT_OF_CORPUS,
    )
    assert query.fallback_reason == FallbackReason.OUT_OF_CORPUS


def test_answer_allowed_rejects_fallback_reason() -> None:
    with pytest.raises(ValidationError, match="must not include fallback_reason"):
        _query(fallback_reason=FallbackReason.INCOMPLETE_EVIDENCE)


def test_blocking_requires_rationale() -> None:
    with pytest.raises(ValidationError, match="blocking queries require"):
        _query(blocking=True)


def test_ambiguous_requires_category() -> None:
    with pytest.raises(ValidationError, match="ambiguous queries require"):
        _query(question_types=[QuestionType.AMBIGUOUS])
    query = _query(
        question_types=[QuestionType.AMBIGUOUS],
        ambiguity_category=AmbiguityCategory.REQUIRES_CLARIFICATION,
    )
    assert query.ambiguity_category == AmbiguityCategory.REQUIRES_CLARIFICATION


def test_temporal_metadata_requires_reference_date() -> None:
    with pytest.raises(ValidationError, match="requires as_of_date"):
        TemporalMetadata(version_sensitive=True)
    query = _query(
        question_types=[QuestionType.TEMPORAL_VERSION_SENSITIVE],
        temporal_metadata=TemporalMetadata(
            version_sensitive=True,
            as_of_date=date(2026, 1, 1),
            applicable_law_id="LAW_A",
        ),
    )
    assert query.temporal_metadata is not None


def test_hierarchy_consistency() -> None:
    with pytest.raises(ValidationError, match="point_label requires clause_number"):
        LegalTarget(
            id="t1",
            query_id="q1",
            law_id="LAW_A",
            document_title="Synthetic Law",
            article_number="1",
            point_label="a",
            match_level=MatchLevel.POINT,
            target_role=TargetRole.REQUIRED,
        )


def test_frozen_query_requires_split_and_regression_overlap_not_held_out() -> None:
    with pytest.raises(ValidationError, match="frozen queries require"):
        _query(review_status=ReviewStatus.FROZEN)
    with pytest.raises(ValidationError, match="must not use held_out_test"):
        _query(
            regression_case_ids=["regression_a"],
            split=BenchmarkSplit.HELD_OUT_TEST,
        )


def test_evidence_group_requires_draft_targets_and_required_minimum() -> None:
    with pytest.raises(ValidationError, match="minimum_hits"):
        EvidenceGroup(
            query_id="q1",
            evidence_group_id="g1",
            requirement=EvidenceGroupRequirement.REQUIRED,
            minimum_hits=0,
            acceptable_chunk_ids=["chunk_a"],
        )
    with pytest.raises(ValidationError, match="acceptable_chunk_ids"):
        EvidenceGroup(
            query_id="q1",
            evidence_group_id="g1",
            requirement=EvidenceGroupRequirement.OPTIONAL,
            minimum_hits=0,
        )


def test_evidence_judgment_does_not_store_group_completion_booleans() -> None:
    judgment = EvidenceJudgment(
        query_id="q1",
        chunk_id="chunk_a",
        relevance=RelevanceLevel.SUPPORTING,
        evidence_group_ids=[],
    )
    assert not judgment.relevance.can_satisfy_required_group


def test_review_disagreement_requires_resolution_when_adjudicated() -> None:
    with pytest.raises(ValidationError, match="resolution_notes"):
        ReviewRecord(
            id="r1",
            query_id="q1",
            review_stage=ReviewStage.ADJUDICATION,
            reviewer_id="reviewer_a",
            status=ReviewStatus.ADJUDICATED,
            reviewed_fields=["expected_decision"],
            disagreements=["expected_decision"],
            reviewed_at=datetime(2026, 1, 1),
        )


def test_manifest_rejects_secret_like_values() -> None:
    with pytest.raises(ValidationError, match="secret-like"):
        BenchmarkManifest(
            schema_version="1.0",
            benchmark_version="draft",
            freeze_date=datetime(2026, 1, 1),
            record_counts={"queries": 1},
            raw_file_sha256={"queries": "a" * 64},
            canonical_content_sha256={"queries": "b" * 64},
            corpus_registry_raw_file_sha256="c" * 64,
            processed_chunks_raw_file_sha256="d" * 64,
            split_manifest_raw_file_sha256="e" * 64,
            split_manifest_canonical_content_sha256="f" * 64,
            manifest_canonical_content_sha256="1" * 64,
            review_status=ReviewStatus.FROZEN,
            change_log=["Authorization: Bearer token"],
        )


def test_legal_target_reference_requires_matching_depth() -> None:
    with pytest.raises(ValidationError, match="point match_level"):
        LegalTargetReference(
            law_id="LAW_A",
            article_number="1",
            clause_number="1",
            match_level=MatchLevel.POINT,
        )


def test_config_rejects_disabled_protocol_invariants() -> None:
    base = {
        "schema_version": "1.0",
        "development_ratio": 0.7,
        "split_seed": 1,
        "grouping_fields": ["case_family_id", "source_provision_group_id"],
    }
    for field_name in (
        "require_independent_review_for_held_out",
        "require_chunk_qrels_for_frozen_answer_allowed",
        "preserve_vietnamese_diacritics",
    ):
        payload = dict(base)
        payload[field_name] = False
        with pytest.raises(ValidationError):
            BenchmarkConfig.model_validate(payload)


def test_config_requires_mandatory_grouping_fields() -> None:
    with pytest.raises(ValidationError, match="mandatory protocol fields"):
        BenchmarkConfig(
            schema_version="1.0",
            development_ratio=0.7,
            split_seed=1,
            grouping_fields=["case_family_id"],
        )


def test_split_manifest_requires_mandatory_grouping_fields() -> None:
    with pytest.raises(ValidationError, match="mandatory protocol fields"):
        SplitManifest(
            schema_version="1.0",
            benchmark_version="draft",
            strategy="connected_component_grouped_split",
            seed=1,
            development_ratio=0.5,
            grouping_fields=["case_family_id"],
            input_fingerprint="a" * 64,
            assignments={"q1": BenchmarkSplit.DEVELOPMENT},
            created_at=datetime(2026, 1, 1),
        )
