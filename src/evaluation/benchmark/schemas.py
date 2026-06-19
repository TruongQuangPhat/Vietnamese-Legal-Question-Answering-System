"""Pydantic schemas for legal QA benchmark records and manifests."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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

_SECRET_VALUE_RE = re.compile(
    r"(sk-or-[A-Za-z0-9_.-]+|sk-[A-Za-z0-9_.-]+|Bearer\s+[A-Za-z0-9_.-]+)",
    re.IGNORECASE,
)
_SECRET_KEY_RE = re.compile(r"(api[_-]?key|access[_-]?token|authorization|secret)", re.IGNORECASE)
MANDATORY_GROUPING_FIELDS = frozenset({"case_family_id", "source_provision_group_id"})


class StrictBenchmarkModel(BaseModel):
    """Base schema that rejects unknown benchmark fields."""

    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)


def _normalize_required_text(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("value must not be blank")
    return normalized


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _require_unique(values: list[Any], field_name: str) -> list[Any]:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return values


class TemporalMetadata(StrictBenchmarkModel):
    """Temporal applicability metadata for version-sensitive legal questions.

    Legal assumptions:
        `applicable_law_id` must be a canonical registry identifier. If the
        repository later adds immutable document-version IDs, they need a
        separate schema field rather than being conflated with `law_id`.
    """

    version_sensitive: bool = False
    as_of_date: date | None = None
    applicable_law_id: str | None = None
    applicable_version_notes: str | None = None

    @field_validator("applicable_law_id", "applicable_version_notes")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        """Trim optional temporal strings."""
        return _normalize_optional_text(value)

    @model_validator(mode="after")
    def validate_temporal_metadata(self) -> TemporalMetadata:
        """Require a concrete reference date for version-sensitive cases."""
        if self.version_sensitive and self.as_of_date is None:
            raise ValueError("version_sensitive temporal metadata requires as_of_date")
        return self


class BenchmarkQuery(StrictBenchmarkModel):
    """One benchmark question and its adjudicated answerability metadata."""

    id: str = Field(..., min_length=1)
    query: str = Field(..., min_length=1)
    primary_domain: LegalDomain
    secondary_domains: list[LegalDomain] = Field(default_factory=list)
    question_types: list[QuestionType] = Field(..., min_length=1)
    expected_decision: ExpectedDecision
    fallback_reason: FallbackReason | None = None
    case_family_id: str | None = None
    source_provision_group_id: str | None = None
    complete_evidence_required: bool = False
    blocking: bool = False
    blocking_rationale: str | None = None
    ambiguity_category: AmbiguityCategory | None = None
    temporal_metadata: TemporalMetadata | None = None
    review_status: ReviewStatus = ReviewStatus.DRAFT
    reviewer_notes: str = Field(..., min_length=1)
    split: BenchmarkSplit | None = None
    regression_case_ids: list[str] = Field(default_factory=list)

    @field_validator(
        "id",
        "query",
        "case_family_id",
        "source_provision_group_id",
        "blocking_rationale",
        "reviewer_notes",
    )
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        """Trim text fields while rejecting blank required fields."""
        if value is None:
            return None
        return _normalize_required_text(value)

    @field_validator("secondary_domains")
    @classmethod
    def require_unique_secondary_domains(
        cls,
        values: list[LegalDomain],
    ) -> list[LegalDomain]:
        """Reject duplicate secondary domains."""
        return _require_unique(values, "secondary_domains")

    @field_validator("question_types")
    @classmethod
    def require_unique_question_types(cls, values: list[QuestionType]) -> list[QuestionType]:
        """Reject duplicate question types."""
        return _require_unique(values, "question_types")

    @field_validator("regression_case_ids")
    @classmethod
    def normalize_regression_ids(cls, values: list[str]) -> list[str]:
        """Trim and reject duplicate regression overlap identifiers."""
        normalized = [_normalize_required_text(value) for value in values]
        return _require_unique(normalized, "regression_case_ids")

    @model_validator(mode="after")
    def validate_query_invariants(self) -> BenchmarkQuery:
        """Enforce protocol invariants that are local to one query."""
        if self.primary_domain in self.secondary_domains:
            raise ValueError("secondary_domains must exclude primary_domain")
        has_fallback_type = QuestionType.FALLBACK in self.question_types
        is_fallback = self.expected_decision == ExpectedDecision.FALLBACK_REQUIRED
        if is_fallback != has_fallback_type:
            raise ValueError("fallback decision and fallback question type must match")
        if is_fallback and self.fallback_reason is None:
            raise ValueError("fallback_required queries require fallback_reason")
        if not is_fallback and self.fallback_reason is not None:
            raise ValueError("answer_allowed queries must not include fallback_reason")
        if self.blocking and self.blocking_rationale is None:
            raise ValueError("blocking queries require blocking_rationale")
        if QuestionType.AMBIGUOUS in self.question_types and self.ambiguity_category is None:
            raise ValueError("ambiguous queries require ambiguity_category")
        if QuestionType.TEMPORAL_VERSION_SENSITIVE in self.question_types:
            if self.temporal_metadata is None or self.temporal_metadata.as_of_date is None:
                raise ValueError("temporal_version_sensitive queries require as_of_date")
        if self.review_status == ReviewStatus.FROZEN and self.split is None:
            raise ValueError("frozen queries require an assigned split")
        if self.regression_case_ids and self.split == BenchmarkSplit.HELD_OUT_TEST:
            raise ValueError("regression-overlap queries must not use held_out_test")
        return self


class LegalTargetReference(StrictBenchmarkModel):
    """Typed legal hierarchy reference used inside evidence groups."""

    law_id: str = Field(..., min_length=1)
    article_number: str = Field(..., min_length=1)
    clause_number: str | None = None
    point_label: str | None = None
    match_level: MatchLevel

    @field_validator("law_id", "article_number", "clause_number", "point_label")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        """Trim hierarchy fields and reject blank values when present."""
        if value is None:
            return None
        return _normalize_required_text(value)

    @model_validator(mode="after")
    def validate_hierarchy(self) -> LegalTargetReference:
        """Ensure match level agrees with populated hierarchy fields."""
        if self.point_label is not None and self.clause_number is None:
            raise ValueError("point_label requires clause_number")
        if self.match_level == MatchLevel.CLAUSE and self.clause_number is None:
            raise ValueError("clause match_level requires clause_number")
        if self.match_level == MatchLevel.POINT:
            if self.clause_number is None:
                raise ValueError("point match_level requires clause_number")
            if self.point_label is None:
                raise ValueError("point match_level requires point_label")
        return self


class LegalTarget(StrictBenchmarkModel):
    """Reviewed legal target for one benchmark query.

    Legal assumptions:
        `law_id` is the canonical key. `document_title` is reviewer metadata
        and must never replace the registry identifier.
    """

    id: str = Field(..., min_length=1)
    query_id: str = Field(..., min_length=1)
    law_id: str = Field(..., min_length=1)
    document_title: str = Field(..., min_length=1)
    article_number: str = Field(..., min_length=1)
    clause_number: str | None = None
    point_label: str | None = None
    match_level: MatchLevel
    target_role: TargetRole
    review_notes: str | None = None

    @field_validator(
        "id",
        "query_id",
        "law_id",
        "document_title",
        "article_number",
        "clause_number",
        "point_label",
        "review_notes",
    )
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        """Trim legal target text fields."""
        if value is None:
            return None
        return _normalize_required_text(value)

    def as_reference(self) -> LegalTargetReference:
        """Return this target as a hierarchy-only reference."""
        return LegalTargetReference(
            law_id=self.law_id,
            article_number=self.article_number,
            clause_number=self.clause_number,
            point_label=self.point_label,
            match_level=self.match_level,
        )

    @model_validator(mode="after")
    def validate_hierarchy(self) -> LegalTarget:
        """Require article, clause, and point hierarchy consistency."""
        self.as_reference()
        return self


class EvidenceJudgment(StrictBenchmarkModel):
    """Chunk-level relevance judgment for one query.

    RAG assumptions:
        Direct citability and group completion are derived from `relevance`.
        The record intentionally does not duplicate these as mutable booleans.
    """

    query_id: str = Field(..., min_length=1)
    chunk_id: str = Field(..., min_length=1)
    relevance: RelevanceLevel
    evidence_group_ids: list[str] = Field(default_factory=list)
    review_notes: str | None = None

    @field_validator("query_id", "chunk_id", "review_notes")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        """Trim evidence judgment text fields."""
        if value is None:
            return None
        return _normalize_required_text(value)

    @field_validator("evidence_group_ids")
    @classmethod
    def normalize_group_ids(cls, values: list[str]) -> list[str]:
        """Trim and reject duplicate evidence group references."""
        normalized = [_normalize_required_text(value) for value in values]
        return _require_unique(normalized, "evidence_group_ids")


class EvidenceGroup(StrictBenchmarkModel):
    """Semantic evidence requirement for a benchmark answer."""

    query_id: str = Field(..., min_length=1)
    evidence_group_id: str = Field(..., min_length=1)
    requirement: EvidenceGroupRequirement
    minimum_hits: int = Field(..., ge=0)
    acceptable_chunk_ids: list[str] = Field(default_factory=list)
    acceptable_legal_targets: list[LegalTargetReference] = Field(default_factory=list)
    review_notes: str | None = None

    @field_validator("query_id", "evidence_group_id", "review_notes")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        """Trim evidence group text fields."""
        if value is None:
            return None
        return _normalize_required_text(value)

    @field_validator("acceptable_chunk_ids")
    @classmethod
    def normalize_chunk_ids(cls, values: list[str]) -> list[str]:
        """Trim and reject duplicate acceptable chunk identifiers."""
        normalized = [_normalize_required_text(value) for value in values]
        return _require_unique(normalized, "acceptable_chunk_ids")

    @model_validator(mode="after")
    def validate_group_requirements(self) -> EvidenceGroup:
        """Enforce draft-level evidence group completeness rules."""
        if self.requirement == EvidenceGroupRequirement.REQUIRED and self.minimum_hits < 1:
            raise ValueError("required evidence groups require minimum_hits >= 1")
        if not self.acceptable_chunk_ids and not self.acceptable_legal_targets:
            raise ValueError(
                "evidence groups require acceptable_chunk_ids or acceptable_legal_targets"
            )
        return self


class ReviewRecord(StrictBenchmarkModel):
    """Minimal provenance for primary review, independent review, or adjudication."""

    id: str = Field(..., min_length=1)
    query_id: str = Field(..., min_length=1)
    review_stage: ReviewStage
    reviewer_id: str = Field(..., min_length=1)
    status: ReviewStatus
    reviewed_fields: list[str] = Field(default_factory=list)
    disagreements: list[str] = Field(default_factory=list)
    resolution_notes: str | None = None
    reviewed_at: datetime

    @field_validator("id", "query_id", "reviewer_id", "resolution_notes")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        """Trim review text fields while storing only minimal reviewer IDs."""
        if value is None:
            return None
        return _normalize_required_text(value)

    @field_validator("reviewed_fields", "disagreements")
    @classmethod
    def normalize_string_list(cls, values: list[str]) -> list[str]:
        """Trim and reject duplicate list values."""
        normalized = [_normalize_required_text(value) for value in values]
        return _require_unique(normalized, "review string lists")

    @model_validator(mode="after")
    def validate_disagreement_resolution(self) -> ReviewRecord:
        """Prevent silent disagreement overwrite in adjudication records."""
        if self.disagreements and self.status == ReviewStatus.ADJUDICATED:
            if self.resolution_notes is None:
                raise ValueError("adjudicated disagreements require resolution_notes")
        return self


class SplitManifest(StrictBenchmarkModel):
    """Deterministic grouped split assignment manifest."""

    schema_version: str = Field(..., min_length=1)
    benchmark_version: str = Field(..., min_length=1)
    strategy: str = Field(..., min_length=1)
    seed: int
    development_ratio: float = Field(..., gt=0.0, lt=1.0)
    grouping_fields: list[str] = Field(..., min_length=1)
    stratification_fields: list[str] = Field(default_factory=list)
    input_fingerprint: str = Field(..., min_length=64, max_length=64)
    assignments: dict[str, BenchmarkSplit] = Field(..., min_length=1)
    created_at: datetime
    summary: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "schema_version",
        "benchmark_version",
        "strategy",
        "input_fingerprint",
    )
    @classmethod
    def normalize_text(cls, value: str) -> str:
        """Trim required manifest strings."""
        return _normalize_required_text(value)

    @field_validator("grouping_fields", "stratification_fields")
    @classmethod
    def normalize_string_list(cls, values: list[str]) -> list[str]:
        """Trim and reject duplicate manifest field names."""
        normalized = [_normalize_required_text(value) for value in values]
        return _require_unique(normalized, "manifest field list")

    @model_validator(mode="after")
    def validate_assignments(self) -> SplitManifest:
        """Reject blank query IDs and missing mandatory grouping fields."""
        missing = MANDATORY_GROUPING_FIELDS.difference(self.grouping_fields)
        if missing:
            raise ValueError(
                "split manifest grouping_fields must include mandatory protocol fields: "
                + ", ".join(sorted(missing))
            )
        for query_id in self.assignments:
            _normalize_required_text(query_id)
        return self


class BenchmarkManifest(StrictBenchmarkModel):
    """Frozen benchmark manifest with raw and semantic fingerprints."""

    schema_version: str = Field(..., min_length=1)
    benchmark_version: str = Field(..., min_length=1)
    freeze_date: datetime
    record_counts: dict[str, int]
    raw_file_sha256: dict[str, str]
    canonical_content_sha256: dict[str, str]
    corpus_registry_raw_file_sha256: str = Field(..., min_length=64, max_length=64)
    processed_chunks_raw_file_sha256: str = Field(..., min_length=64, max_length=64)
    split_manifest_raw_file_sha256: str = Field(..., min_length=64, max_length=64)
    split_manifest_canonical_content_sha256: str = Field(..., min_length=64, max_length=64)
    manifest_canonical_content_sha256: str = Field(..., min_length=64, max_length=64)
    review_status: ReviewStatus
    change_log: list[str] = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_manifest_safety(self) -> BenchmarkManifest:
        """Reject secret-like keys or values from source-controlled manifests."""
        payload = self.model_dump(mode="json")
        _reject_secret_like_payload(payload)
        for count_name, count in self.record_counts.items():
            _normalize_required_text(count_name)
            if count < 0:
                raise ValueError("record_counts values must be non-negative")
        for field_name, checksums in (
            ("raw_file_sha256", self.raw_file_sha256),
            ("canonical_content_sha256", self.canonical_content_sha256),
        ):
            for path_name, checksum in checksums.items():
                _normalize_required_text(path_name)
                if len(checksum) != 64:
                    raise ValueError(f"{field_name} values must be SHA-256 hex digests")
        return self


class BenchmarkConfig(StrictBenchmarkModel):
    """Typed configuration for benchmark validation, splitting, and freeze support."""

    schema_version: str = Field(..., min_length=1)
    benchmark_version: str = Field("draft", min_length=1)
    development_ratio: float = Field(..., gt=0.0, lt=1.0)
    split_seed: int
    grouping_fields: list[str] = Field(..., min_length=1)
    stratification_fields: list[str] = Field(default_factory=list)
    require_independent_review_for_held_out: Literal[True] = True
    require_chunk_qrels_for_frozen_answer_allowed: Literal[True] = True
    preserve_vietnamese_diacritics: Literal[True] = True

    @field_validator("schema_version", "benchmark_version")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        """Trim config strings."""
        return _normalize_required_text(value)

    @field_validator("grouping_fields", "stratification_fields")
    @classmethod
    def normalize_string_list(cls, values: list[str]) -> list[str]:
        """Trim and reject duplicate config field names."""
        normalized = [_normalize_required_text(value) for value in values]
        return _require_unique(normalized, "config field list")

    @model_validator(mode="after")
    def validate_protocol_invariants(self) -> BenchmarkConfig:
        """Prevent configuration from disabling protocol-required behavior."""
        missing = MANDATORY_GROUPING_FIELDS.difference(self.grouping_fields)
        if missing:
            raise ValueError(
                "grouping_fields must include mandatory protocol fields: "
                + ", ".join(sorted(missing))
            )
        unknown = set(self.grouping_fields).difference(BenchmarkQuery.model_fields)
        if unknown:
            raise ValueError(
                "grouping_fields contains unknown BenchmarkQuery fields: "
                + ", ".join(sorted(unknown))
            )
        return self


def _reject_secret_like_payload(value: Any) -> None:
    """Reject secret-like keys and values in benchmark manifests."""
    if isinstance(value, dict):
        for key, child in value.items():
            if _SECRET_KEY_RE.search(str(key)):
                raise ValueError("manifest must not include secret-like keys")
            _reject_secret_like_payload(child)
    elif isinstance(value, list):
        for child in value:
            _reject_secret_like_payload(child)
    elif isinstance(value, str) and _SECRET_VALUE_RE.search(value):
        raise ValueError("manifest must not include secret-like values")
