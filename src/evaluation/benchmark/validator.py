"""Benchmark validation layers for legal QA benchmark construction."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from src.evaluation.benchmark.enums import (
    BenchmarkSplit,
    EvidenceGroupRequirement,
    ExpectedDecision,
    MatchLevel,
    QuestionType,
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
    LegalTargetReference,
    ReviewRecord,
    SplitManifest,
)

_WHITESPACE_RE = re.compile(r"\s+")
_CONTROLLED_PUNCT_RE = re.compile(r"[“”\"'`.,;:!?()\[\]{}]+")


class ValidationIssue(BaseModel):
    """One benchmark validation error or warning."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    severity: str = Field(..., min_length=1)
    query_id: str | None = None
    record_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class BenchmarkValidationReport(BaseModel):
    """Typed validation report for benchmark construction files."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
    record_counts: dict[str, int] = Field(default_factory=dict)
    checked_files: list[str] = Field(default_factory=list)


class CorpusChunk(BaseModel):
    """Small read-only chunk index entry used by corpus-aware validation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_id: str
    law_id: str
    article_number: str | None = None
    clause_number: str | None = None
    point_label: str | None = None
    level: str | None = None


class BenchmarkValidator:
    """Validate benchmark records without running retrieval, generation, or indexing."""

    def __init__(
        self,
        *,
        config: BenchmarkConfig,
        regression_query_texts: set[str] | None = None,
    ) -> None:
        self._config = config
        self._regression_query_texts = regression_query_texts or set()

    def validate(
        self,
        dataset: LoadedBenchmarkDataset,
        *,
        split_manifest: SplitManifest | None = None,
        corpus_registry_path: Path | None = None,
        processed_chunks_path: Path | None = None,
    ) -> BenchmarkValidationReport:
        """Validate benchmark records and optional corpus/split context.

        Args:
            dataset: Typed benchmark dataset.
            split_manifest: Optional split manifest to verify.
            corpus_registry_path: Optional read-only corpus registry path.
            processed_chunks_path: Optional read-only processed chunks JSONL path.

        Returns:
            Validation report with all detected errors and warnings.
        """
        errors: list[ValidationIssue] = []
        warnings: list[ValidationIssue] = []
        registry_law_ids = (
            load_registry_law_ids(corpus_registry_path) if corpus_registry_path else None
        )
        chunk_index = load_chunk_index(processed_chunks_path) if processed_chunks_path else None

        self._validate_referential_integrity(dataset, errors)
        self._validate_decision_invariants(dataset, errors)
        self._validate_qrel_group_consistency(dataset, errors)
        self._validate_question_types(dataset, errors, warnings)
        self._validate_reviews(dataset, errors)
        self._validate_duplicate_normalization(dataset.queries, warnings)
        self._validate_regression_contamination(dataset.queries, errors, warnings)
        if split_manifest is not None:
            self._validate_split_manifest(dataset.queries, split_manifest, errors)
        if registry_law_ids is not None or chunk_index is not None:
            self._validate_corpus_awareness(
                dataset,
                registry_law_ids=registry_law_ids,
                chunk_index=chunk_index,
                errors=errors,
                warnings=warnings,
            )

        return BenchmarkValidationReport(
            status="validation_failed" if errors else "validation_passed",
            errors=errors,
            warnings=warnings,
            record_counts={
                "queries": len(dataset.queries),
                "legal_targets": len(dataset.legal_targets),
                "evidence_judgments": len(dataset.evidence_judgments),
                "evidence_groups": len(dataset.evidence_groups),
                "review_records": len(dataset.review_records),
            },
            checked_files=dataset.checked_files,
        )

    def _validate_referential_integrity(
        self,
        dataset: LoadedBenchmarkDataset,
        errors: list[ValidationIssue],
    ) -> None:
        query_ids = {query.id for query in dataset.queries}
        group_ids = {(group.query_id, group.evidence_group_id) for group in dataset.evidence_groups}
        for target in dataset.legal_targets:
            if target.query_id not in query_ids:
                errors.append(
                    _error(
                        "orphan_legal_target",
                        "legal target query_id is unknown",
                        target.query_id,
                        target.id,
                    )
                )
        for judgment in dataset.evidence_judgments:
            if judgment.query_id not in query_ids:
                errors.append(
                    _error(
                        "orphan_evidence_judgment",
                        "evidence judgment query_id is unknown",
                        judgment.query_id,
                        judgment.chunk_id,
                    )
                )
            for group_id in judgment.evidence_group_ids:
                if (judgment.query_id, group_id) not in group_ids:
                    errors.append(
                        _error(
                            "unknown_evidence_group_reference",
                            "evidence judgment references an unknown evidence group",
                            judgment.query_id,
                            judgment.chunk_id,
                            {"evidence_group_id": group_id},
                        ),
                    )
        for group in dataset.evidence_groups:
            if group.query_id not in query_ids:
                errors.append(
                    _error(
                        "orphan_evidence_group",
                        "evidence group query_id is unknown",
                        group.query_id,
                        group.evidence_group_id,
                    )
                )
        for review in dataset.review_records:
            if review.query_id not in query_ids:
                errors.append(
                    _error(
                        "orphan_review_record",
                        "review record query_id is unknown",
                        review.query_id,
                        review.id,
                    )
                )

    def _validate_decision_invariants(
        self,
        dataset: LoadedBenchmarkDataset,
        errors: list[ValidationIssue],
    ) -> None:
        targets_by_query = _targets_by_query(dataset)
        groups_by_query = _groups_by_query(dataset)
        judgments_by_query = _judgments_by_query(dataset)
        for query in dataset.queries:
            groups = groups_by_query[query.id]
            judgments = judgments_by_query[query.id]
            if query.expected_decision == ExpectedDecision.ANSWER_ALLOWED:
                if query.review_status == ReviewStatus.FROZEN and not _has_direct_evidence(
                    judgments
                ):
                    errors.append(
                        _error(
                            "answer_allowed_missing_direct_evidence",
                            "frozen answer_allowed query requires direct evidence",
                            query.id,
                        )
                    )
                if query.review_status == ReviewStatus.FROZEN and not targets_by_query[query.id]:
                    errors.append(
                        _error(
                            "answer_allowed_missing_legal_target",
                            "frozen answer_allowed query requires legal targets",
                            query.id,
                        )
                    )
            for group in groups:
                if group.requirement != EvidenceGroupRequirement.REQUIRED:
                    continue
                if (
                    query.review_status == ReviewStatus.FROZEN
                    and query.expected_decision == ExpectedDecision.ANSWER_ALLOWED
                    and not group.acceptable_chunk_ids
                ):
                    errors.append(
                        _error(
                            "frozen_required_group_missing_chunk_qrels",
                            "frozen answer_allowed required groups require acceptable_chunk_ids",
                            query.id,
                            group.evidence_group_id,
                        ),
                    )
                if not _required_group_satisfiable(group):
                    errors.append(
                        _error(
                            "required_group_not_satisfiable",
                            "required evidence group is not satisfiable",
                            query.id,
                            group.evidence_group_id,
                        )
                    )
            for judgment in judgments:
                if (
                    judgment.evidence_group_ids
                    and not judgment.relevance.can_satisfy_required_group
                ):
                    referenced_required = [
                        group_id
                        for group_id in judgment.evidence_group_ids
                        if _is_required_group(groups, group_id)
                    ]
                    if referenced_required:
                        errors.append(
                            _error(
                                "non_direct_evidence_group_completion",
                                "supporting, near-miss, or irrelevant evidence cannot complete required groups",
                                query.id,
                                judgment.chunk_id,
                                {"evidence_group_ids": referenced_required},
                            ),
                        )

    def _validate_qrel_group_consistency(
        self,
        dataset: LoadedBenchmarkDataset,
        errors: list[ValidationIssue],
    ) -> None:
        queries_by_id = {query.id: query for query in dataset.queries}
        groups_by_key = {
            (group.query_id, group.evidence_group_id): group for group in dataset.evidence_groups
        }
        judgments_by_query_chunk: dict[tuple[str, str], list[EvidenceJudgment]] = defaultdict(list)
        for judgment in dataset.evidence_judgments:
            judgments_by_query_chunk[(judgment.query_id, judgment.chunk_id)].append(judgment)

        for (query_id, chunk_id), judgments in judgments_by_query_chunk.items():
            relevance_values = {judgment.relevance for judgment in judgments}
            if len(judgments) > 1:
                code = (
                    "contradictory_evidence_judgment"
                    if len(relevance_values) > 1
                    else "duplicate_evidence_judgment"
                )
                errors.append(
                    _error(
                        code,
                        "each query/chunk pair must have one deterministic evidence judgment",
                        query_id,
                        chunk_id,
                        {"relevance_values": sorted(value.value for value in relevance_values)},
                    )
                )

        for group in dataset.evidence_groups:
            query = queries_by_id.get(group.query_id)
            for chunk_id in group.acceptable_chunk_ids:
                judgments = judgments_by_query_chunk.get((group.query_id, chunk_id), [])
                if not judgments:
                    errors.append(
                        _error(
                            "acceptable_chunk_missing_judgment",
                            "acceptable_chunk_ids require matching evidence judgment",
                            group.query_id,
                            group.evidence_group_id,
                            {"chunk_id": chunk_id},
                        )
                    )
                    continue
                direct_judgments = [
                    judgment
                    for judgment in judgments
                    if judgment.relevance.can_satisfy_required_group
                    and group.evidence_group_id in judgment.evidence_group_ids
                ]
                if not direct_judgments:
                    errors.append(
                        _error(
                            "acceptable_chunk_not_direct_for_group",
                            "acceptable chunk judgment must be required_direct or alternative_direct and reference the group",
                            group.query_id,
                            group.evidence_group_id,
                            {
                                "chunk_id": chunk_id,
                                "judgment_relevance": sorted(
                                    judgment.relevance.value for judgment in judgments
                                ),
                            },
                        )
                    )

            direct_acceptable_chunks = {
                chunk_id
                for chunk_id in group.acceptable_chunk_ids
                for judgment in judgments_by_query_chunk.get((group.query_id, chunk_id), [])
                if judgment.relevance.can_satisfy_required_group
                and group.evidence_group_id in judgment.evidence_group_ids
            }
            if (
                query is not None
                and query.review_status == ReviewStatus.FROZEN
                and query.expected_decision == ExpectedDecision.ANSWER_ALLOWED
                and group.acceptable_chunk_ids
                and group.minimum_hits > len(direct_acceptable_chunks)
            ):
                errors.append(
                    _error(
                        "minimum_hits_exceeds_direct_chunks",
                        "minimum_hits must not exceed distinct acceptable direct chunks",
                        group.query_id,
                        group.evidence_group_id,
                        {
                            "minimum_hits": group.minimum_hits,
                            "direct_chunk_count": len(direct_acceptable_chunks),
                        },
                    )
                )

        for judgment in dataset.evidence_judgments:
            for group_id in judgment.evidence_group_ids:
                group = groups_by_key.get((judgment.query_id, group_id))
                if group is None:
                    continue
                if (
                    judgment.relevance.can_satisfy_required_group
                    and judgment.chunk_id not in group.acceptable_chunk_ids
                ):
                    errors.append(
                        _error(
                            "direct_judgment_chunk_not_acceptable",
                            "direct evidence judgments must be listed in the referenced group's acceptable_chunk_ids",
                            judgment.query_id,
                            judgment.chunk_id,
                            {"evidence_group_id": group_id},
                        )
                    )

    def _validate_question_types(
        self,
        dataset: LoadedBenchmarkDataset,
        errors: list[ValidationIssue],
        warnings: list[ValidationIssue],
    ) -> None:
        targets_by_query = _targets_by_query(dataset)
        for query in dataset.queries:
            targets = targets_by_query[query.id]
            if QuestionType.CROSS_LAW in query.question_types:
                law_ids = {
                    target.law_id
                    for target in targets
                    if target.target_role in {TargetRole.REQUIRED, TargetRole.ALTERNATIVE}
                }
                if len(law_ids) < 2:
                    errors.append(
                        _error(
                            "cross_law_requires_two_laws",
                            "cross_law requires at least two required or alternative law IDs",
                            query.id,
                        )
                    )
            if QuestionType.CLAUSE_POINT_LOOKUP in query.question_types:
                if not any(target.clause_number or target.point_label for target in targets):
                    errors.append(
                        _error(
                            "clause_point_requires_child_target",
                            "clause_point_lookup requires a clause or point target",
                            query.id,
                        )
                    )
            if (
                QuestionType.COMPLETE_LIST in query.question_types
                and not query.complete_evidence_required
            ):
                errors.append(
                    _error(
                        "complete_list_requires_completeness",
                        "complete_list requires complete_evidence_required=true",
                        query.id,
                    )
                )
            if QuestionType.TEMPORAL_VERSION_SENSITIVE in query.question_types:
                if query.temporal_metadata is None or query.temporal_metadata.as_of_date is None:
                    errors.append(
                        _error(
                            "temporal_case_missing_reference_date",
                            "temporal_version_sensitive requires as_of_date",
                            query.id,
                        )
                    )
            if QuestionType.AMBIGUOUS in query.question_types and query.ambiguity_category is None:
                errors.append(
                    _error(
                        "ambiguous_missing_category",
                        "ambiguous queries require ambiguity_category",
                        query.id,
                    )
                )
            if QuestionType.NEAR_DUPLICATE_PROVISION in query.question_types and not targets:
                warnings.append(
                    _warning(
                        "near_duplicate_without_targets",
                        "near_duplicate_provision is difficult to validate without legal targets",
                        query.id,
                    )
                )

    def _validate_reviews(
        self,
        dataset: LoadedBenchmarkDataset,
        errors: list[ValidationIssue],
    ) -> None:
        reviews_by_query = _reviews_by_query(dataset)
        self._validate_review_record_consistency(dataset.review_records, errors)
        for query in dataset.queries:
            reviews = reviews_by_query[query.id]
            if query.review_status in {
                ReviewStatus.PRIMARY_REVIEWED,
                ReviewStatus.INDEPENDENT_REVIEWED,
                ReviewStatus.ADJUDICATED,
            } and not _has_review_step(reviews, ReviewStage.PRIMARY_ANNOTATION):
                errors.append(
                    _error(
                        "review_summary_missing_primary_record",
                        "query review_status requires primary review evidence",
                        query.id,
                    )
                )
            if query.review_status == ReviewStatus.INDEPENDENT_REVIEWED and not _has_review_step(
                reviews, ReviewStage.INDEPENDENT_REVIEW
            ):
                errors.append(
                    _error(
                        "review_summary_missing_independent_record",
                        "query review_status=independent_reviewed requires independent review evidence",
                        query.id,
                    )
                )
            if query.review_status == ReviewStatus.ADJUDICATED and not _has_review_step(
                reviews, ReviewStage.ADJUDICATION
            ):
                errors.append(
                    _error(
                        "review_summary_missing_adjudication_record",
                        "query review_status=adjudicated requires adjudication evidence",
                        query.id,
                    )
                )
            if query.blocking and query.blocking_rationale is None:
                errors.append(
                    _error(
                        "blocking_missing_rationale",
                        "blocking query requires blocking_rationale",
                        query.id,
                    )
                )
            if query.review_status == ReviewStatus.FROZEN:
                if not _has_review_step(reviews, ReviewStage.PRIMARY_ANNOTATION):
                    errors.append(
                        _error(
                            "frozen_missing_primary_review",
                            "frozen query requires primary review evidence",
                            query.id,
                        )
                    )
                if _requires_independent_review(query) and not _has_review_step(
                    reviews, ReviewStage.INDEPENDENT_REVIEW
                ):
                    errors.append(
                        _error(
                            "frozen_missing_independent_review",
                            "frozen high-risk or held-out query requires independent review",
                            query.id,
                        )
                    )
                if any(review.status == ReviewStatus.CONFLICT for review in reviews):
                    errors.append(
                        _error(
                            "frozen_has_unresolved_conflict",
                            "unresolved conflict prevents frozen status",
                            query.id,
                        )
                    )
                if any(review.disagreements for review in reviews) and not _has_review_step(
                    reviews, ReviewStage.ADJUDICATION
                ):
                    errors.append(
                        _error(
                            "disagreement_without_adjudication",
                            "recorded disagreements require adjudication",
                            query.id,
                        )
                    )
            if query.split == BenchmarkSplit.HELD_OUT_TEST and not _has_review_step(
                reviews, ReviewStage.INDEPENDENT_REVIEW
            ):
                errors.append(
                    _error(
                        "held_out_missing_independent_review",
                        "held-out cases require independent review",
                        query.id,
                    )
                )

    def _validate_review_record_consistency(
        self,
        reviews: list[ReviewRecord],
        errors: list[ValidationIssue],
    ) -> None:
        by_query_step: dict[tuple[str, ReviewStage], list[ReviewRecord]] = defaultdict(list)
        by_exact: dict[tuple[str, ReviewStage, str, ReviewStatus], list[ReviewRecord]] = (
            defaultdict(list)
        )
        for review in reviews:
            by_query_step[(review.query_id, review.review_stage)].append(review)
            by_exact[
                (review.query_id, review.review_stage, review.reviewer_id, review.status)
            ].append(review)
        for (query_id, review_step), step_reviews in by_query_step.items():
            statuses = {review.status for review in step_reviews}
            if len(statuses) > 1:
                errors.append(
                    _error(
                        "contradictory_review_records",
                        "review records for the same query and review step have conflicting statuses",
                        query_id,
                        review_step.value,
                        {"statuses": sorted(status.value for status in statuses)},
                    )
                )
        for (query_id, review_step, reviewer_id, status), exact_reviews in by_exact.items():
            if len(exact_reviews) > 1:
                errors.append(
                    _error(
                        "duplicate_review_record_evidence",
                        (
                            "duplicate review evidence for the same query, review step, "
                            "reviewer, and status"
                        ),
                        query_id,
                        review_step.value,
                        {"reviewer_id": reviewer_id, "status": status.value},
                    )
                )

    def _validate_duplicate_normalization(
        self,
        queries: list[BenchmarkQuery],
        warnings: list[ValidationIssue],
    ) -> None:
        by_key: dict[str, list[str]] = defaultdict(list)
        by_diacriticless: dict[str, list[str]] = defaultdict(list)
        for query in queries:
            by_key[official_duplicate_key(query.query)].append(query.id)
            by_diacriticless[diacritic_insensitive_key(query.query)].append(query.id)
        for query_ids in by_key.values():
            if len(query_ids) > 1:
                warnings.append(
                    _warning(
                        "normalized_duplicate_query",
                        "official duplicate normalization found duplicate query text",
                        record_id=",".join(sorted(query_ids)),
                    ),
                )
        for key, query_ids in by_diacriticless.items():
            official_keys = {
                official_duplicate_key(_query_by_id(queries, query_id).query)
                for query_id in query_ids
            }
            if len(query_ids) > 1 and len(official_keys) > 1:
                warnings.append(
                    _warning(
                        "diacritic_insensitive_duplicate_candidate",
                        "diacritic-insensitive similarity is manual-review only and did not merge records",
                        record_id=",".join(sorted(query_ids)),
                        details={"diacritic_insensitive_key": key},
                    ),
                )

    def _validate_regression_contamination(
        self,
        queries: list[BenchmarkQuery],
        errors: list[ValidationIssue],
        warnings: list[ValidationIssue],
    ) -> None:
        for query in queries:
            overlaps_regression = bool(query.regression_case_ids) or (
                official_duplicate_key(query.query) in self._regression_query_texts
            )
            if overlaps_regression and query.split == BenchmarkSplit.HELD_OUT_TEST:
                errors.append(
                    _error(
                        "regression_overlap_in_held_out",
                        "regression-overlap case must not be assigned to held_out_test",
                        query.id,
                    )
                )
            if overlaps_regression and query.split is None:
                warnings.append(
                    _warning(
                        "regression_overlap_unsplit",
                        "regression-overlap case must be assigned to development or excluded before freeze",
                        query.id,
                    )
                )

    def _validate_split_manifest(
        self,
        queries: list[BenchmarkQuery],
        split_manifest: SplitManifest,
        errors: list[ValidationIssue],
    ) -> None:
        query_ids = {query.id for query in queries}
        assigned_ids = set(split_manifest.assignments)
        if query_ids != assigned_ids:
            errors.append(
                _error(
                    "split_assignment_mismatch",
                    "split manifest assignments must exactly match query IDs",
                    details={
                        "missing": sorted(query_ids - assigned_ids),
                        "extra": sorted(assigned_ids - query_ids),
                    },
                ),
            )
        for query in queries:
            assigned = split_manifest.assignments.get(query.id)
            if query.split is not None and assigned is not None and query.split != assigned:
                errors.append(
                    _error(
                        "query_split_mismatch",
                        "query split disagrees with split manifest",
                        query.id,
                    )
                )
            overlaps_regression = bool(query.regression_case_ids) or (
                official_duplicate_key(query.query) in self._regression_query_texts
            )
            if overlaps_regression and assigned == BenchmarkSplit.HELD_OUT_TEST:
                errors.append(
                    _error(
                        "regression_overlap_assignment_in_held_out",
                        "canonical split manifest must not assign regression-overlap cases to held_out_test",
                        query.id,
                    )
                )
        self._validate_group_leakage(queries, split_manifest, errors, "case_family_id")
        self._validate_group_leakage(queries, split_manifest, errors, "source_provision_group_id")

    def _validate_group_leakage(
        self,
        queries: list[BenchmarkQuery],
        split_manifest: SplitManifest,
        errors: list[ValidationIssue],
        field_name: str,
    ) -> None:
        split_values: dict[str, set[BenchmarkSplit]] = defaultdict(set)
        for query in queries:
            group_value = getattr(query, field_name)
            if group_value and query.id in split_manifest.assignments:
                split_values[group_value].add(split_manifest.assignments[query.id])
        for group_value, splits in split_values.items():
            if len(splits) > 1:
                errors.append(
                    _error(
                        "group_leakage", f"{field_name} leaked across splits", record_id=group_value
                    )
                )

    def _validate_corpus_awareness(
        self,
        dataset: LoadedBenchmarkDataset,
        *,
        registry_law_ids: set[str] | None,
        chunk_index: dict[str, CorpusChunk] | None,
        errors: list[ValidationIssue],
        warnings: list[ValidationIssue],
    ) -> None:
        if registry_law_ids is not None:
            for target in dataset.legal_targets:
                if target.law_id not in registry_law_ids:
                    errors.append(
                        _error(
                            "unknown_law_id",
                            "legal target law_id is not in corpus registry",
                            target.query_id,
                            target.id,
                        )
                    )
            for group in dataset.evidence_groups:
                for target in group.acceptable_legal_targets:
                    if target.law_id not in registry_law_ids:
                        errors.append(
                            _error(
                                "unknown_group_law_id",
                                "group legal target law_id is not in corpus registry",
                                group.query_id,
                                group.evidence_group_id,
                            )
                        )
        if chunk_index is not None:
            groups_by_key = {
                (group.query_id, group.evidence_group_id): group
                for group in dataset.evidence_groups
            }
            for judgment in dataset.evidence_judgments:
                chunk = chunk_index.get(judgment.chunk_id)
                if chunk is None:
                    errors.append(
                        _error(
                            "unknown_chunk_id",
                            "evidence judgment chunk_id is not in processed chunks",
                            judgment.query_id,
                            judgment.chunk_id,
                        )
                    )
                    continue
                for group_id in judgment.evidence_group_ids:
                    group = groups_by_key.get((judgment.query_id, group_id))
                    if group and not _chunk_matches_group(chunk, group):
                        errors.append(
                            _error(
                                "chunk_group_hierarchy_mismatch",
                                "chunk does not match group chunk IDs or legal targets",
                                judgment.query_id,
                                judgment.chunk_id,
                                {"evidence_group_id": group_id},
                            )
                        )
            for group in dataset.evidence_groups:
                for chunk_id in group.acceptable_chunk_ids:
                    if chunk_id not in chunk_index:
                        errors.append(
                            _error(
                                "unknown_group_chunk_id",
                                "acceptable_chunk_ids entry is not in processed chunks",
                                group.query_id,
                                group.evidence_group_id,
                                {"chunk_id": chunk_id},
                            )
                        )
            if not chunk_index:
                warnings.append(_warning("empty_chunk_index", "processed chunk index is empty"))


def official_duplicate_key(text: str) -> str:
    """Normalize duplicate keys while preserving Vietnamese diacritics."""
    normalized = unicodedata.normalize("NFC", text)
    normalized = _CONTROLLED_PUNCT_RE.sub(" ", normalized)
    normalized = _WHITESPACE_RE.sub(" ", normalized).strip().casefold()
    return normalized


def diacritic_insensitive_key(text: str) -> str:
    """Return a manual-review-only key that removes combining marks."""
    decomposed = unicodedata.normalize("NFD", text)
    without_marks = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return official_duplicate_key(without_marks)


def load_registry_law_ids(path: Path) -> set[str]:
    """Load canonical law IDs from the read-only corpus registry."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("corpus"), list):
        raise ValueError(f"invalid corpus registry structure: {path}")
    law_ids = {
        item["law_id"]
        for item in payload["corpus"]
        if isinstance(item, dict) and isinstance(item.get("law_id"), str)
    }
    return law_ids


def load_chunk_index(path: Path) -> dict[str, CorpusChunk]:
    """Load minimal read-only hierarchy metadata from processed chunks JSONL."""
    index: dict[str, CorpusChunk] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            chunk_id = payload.get("chunk_id")
            law_id = payload.get("law_id")
            if not isinstance(chunk_id, str) or not isinstance(law_id, str):
                raise ValueError(f"invalid chunk identity at {path}:{line_number}")
            index[chunk_id] = CorpusChunk(
                chunk_id=chunk_id,
                law_id=law_id,
                article_number=payload.get("article_number"),
                clause_number=payload.get("clause_number"),
                point_label=payload.get("point_label"),
                level=payload.get("level"),
            )
    return index


def load_regression_query_texts(paths: list[Path]) -> set[str]:
    """Load official-normalized query text from existing regression inputs.

    The loader is intentionally lightweight and read-only. It records only
    query text for contamination checks and does not reinterpret Naive RAG labels.
    """
    query_texts: set[str] = set()
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                payload = json.loads(stripped)
                query = payload.get("query")
                if not isinstance(query, str):
                    raise ValueError(f"missing query text in regression input {path}:{line_number}")
                query_texts.add(official_duplicate_key(query))
    return query_texts


def _targets_by_query(dataset: LoadedBenchmarkDataset) -> dict[str, list[Any]]:
    result: dict[str, list[Any]] = defaultdict(list)
    for target in dataset.legal_targets:
        result[target.query_id].append(target)
    return result


def _groups_by_query(dataset: LoadedBenchmarkDataset) -> dict[str, list[EvidenceGroup]]:
    result: dict[str, list[EvidenceGroup]] = defaultdict(list)
    for group in dataset.evidence_groups:
        result[group.query_id].append(group)
    return result


def _judgments_by_query(dataset: LoadedBenchmarkDataset) -> dict[str, list[EvidenceJudgment]]:
    result: dict[str, list[EvidenceJudgment]] = defaultdict(list)
    for judgment in dataset.evidence_judgments:
        result[judgment.query_id].append(judgment)
    return result


def _reviews_by_query(dataset: LoadedBenchmarkDataset) -> dict[str, list[ReviewRecord]]:
    result: dict[str, list[ReviewRecord]] = defaultdict(list)
    for review in dataset.review_records:
        result[review.query_id].append(review)
    return result


def _has_direct_evidence(judgments: list[EvidenceJudgment]) -> bool:
    return any(judgment.relevance.can_satisfy_required_group for judgment in judgments)


def _required_group_satisfiable(group: EvidenceGroup) -> bool:
    return bool(group.acceptable_chunk_ids or group.acceptable_legal_targets)


def _is_required_group(groups: list[EvidenceGroup], evidence_group_id: str) -> bool:
    return any(
        group.evidence_group_id == evidence_group_id
        and group.requirement == EvidenceGroupRequirement.REQUIRED
        for group in groups
    )


def _has_review_step(reviews: list[ReviewRecord], review_step: ReviewStage) -> bool:
    return any(review.review_stage == review_step for review in reviews)


def _requires_independent_review(query: BenchmarkQuery) -> bool:
    high_risk = {
        QuestionType.COMPLETE_LIST,
        QuestionType.CROSS_LAW,
        QuestionType.TEMPORAL_VERSION_SENSITIVE,
        QuestionType.FALLBACK,
        QuestionType.AMBIGUOUS,
    }
    return (
        query.split == BenchmarkSplit.HELD_OUT_TEST
        or query.blocking
        or bool(high_risk.intersection(query.question_types))
    )


def _query_by_id(queries: list[BenchmarkQuery], query_id: str) -> BenchmarkQuery:
    for query in queries:
        if query.id == query_id:
            return query
    raise KeyError(query_id)


def _chunk_matches_group(chunk: CorpusChunk, group: EvidenceGroup) -> bool:
    if chunk.chunk_id in group.acceptable_chunk_ids and not group.acceptable_legal_targets:
        return True
    return any(_chunk_matches_target(chunk, target) for target in group.acceptable_legal_targets)


def _chunk_matches_target(chunk: CorpusChunk, target: LegalTargetReference) -> bool:
    if chunk.law_id != target.law_id or chunk.article_number != target.article_number:
        return False
    if target.match_level == MatchLevel.ARTICLE:
        return True
    if target.match_level == MatchLevel.CLAUSE:
        return chunk.clause_number == target.clause_number
    return chunk.clause_number == target.clause_number and chunk.point_label == target.point_label


def _error(
    code: str,
    message: str,
    query_id: str | None = None,
    record_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        message=message,
        severity="error",
        query_id=query_id,
        record_id=record_id,
        details=details or {},
    )


def _warning(
    code: str,
    message: str,
    query_id: str | None = None,
    record_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        message=message,
        severity="warning",
        query_id=query_id,
        record_id=record_id,
        details=details or {},
    )
