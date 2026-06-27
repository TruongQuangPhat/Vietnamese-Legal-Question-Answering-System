"""Evidence selection and fallback decisions for retrieval-side QA safety.

This module gates citation-safe evidence before any future answer generation.
It does not call LLMs, mutate retrieval results, retrieve from Qdrant, rerank
with a model, or mutate corpus artifacts.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.retrieval.evaluation import EvidenceRiskFlag, ExpectedTarget
from src.retrieval.evidence import (
    CitationScope,
    EvidenceBundle,
    EvidencePacket,
    EvidenceSafetyLevel,
)


class AnswerabilityDecision(StrEnum):
    """Evidence-gate decision for future answer generation."""

    ANSWER_ALLOWED = "answer_allowed"
    FALLBACK_REQUIRED = "fallback_required"
    NEEDS_REVIEW = "needs_review"


class FallbackReasonCode(StrEnum):
    """Machine-readable reasons for fallback or review decisions."""

    NO_EVIDENCE = "no_evidence"
    NO_CITABLE_EVIDENCE = "no_citable_evidence"
    ALL_EVIDENCE_UNSAFE = "all_evidence_unsafe"
    INSUFFICIENT_SAFE_EVIDENCE = "insufficient_safe_evidence"
    MISSING_REQUIRED_CITATION = "missing_required_citation"
    MISSING_REQUIRED_SOURCE_URL = "missing_required_source_url"
    MISSING_REQUIRED_LAW_ID = "missing_required_law_id"
    MISSING_REQUIRED_CHILD_TEXT = "missing_required_child_text"
    PARENT_CONTEXT_ONLY = "parent_context_only"
    HIGH_CITATION_RISK = "high_citation_risk"
    EXACT_TARGET_MISSING_IN_EVAL_MODE = "exact_target_missing_in_eval_mode"
    AMBIGUOUS_TOP_RESULTS = "ambiguous_top_results"
    ALL_SELECTED_EVIDENCE_CAUTION = "all_selected_evidence_caution"


class EvidenceRejectionReason(StrEnum):
    """Reasons a packet was excluded from selected evidence."""

    UNSAFE_EVIDENCE = "unsafe_evidence"
    MISSING_REQUIRED_CITATION = "missing_required_citation"
    MISSING_REQUIRED_SOURCE_URL = "missing_required_source_url"
    MISSING_REQUIRED_LAW_ID = "missing_required_law_id"
    MISSING_REQUIRED_CHILD_TEXT = "missing_required_child_text"
    CAUTION_EVIDENCE_NOT_ALLOWED = "caution_evidence_not_allowed"
    PARENT_CONTEXT_ONLY = "parent_context_only"
    DUPLICATE_EVIDENCE = "duplicate_evidence"


class SelectionWarningCode(StrEnum):
    """Warnings attached to selected evidence or the whole selection result."""

    CAUTION_EVIDENCE_SELECTED = "caution_evidence_selected"
    AUXILIARY_PARENT_CONTEXT_INCLUDED = "auxiliary_parent_context_included"
    AUXILIARY_PARENT_CONTEXT_SUPPRESSED = "auxiliary_parent_context_suppressed"
    ALL_SELECTED_EVIDENCE_CAUTION = "all_selected_evidence_caution"
    UNSAFE_EVIDENCE_REJECTED = "unsafe_evidence_rejected"
    EVALUATION_RISK_FLAG_PRESENT = "evaluation_risk_flag_present"


class EvidenceSelectionConfig(BaseModel):
    """Configuration for retrieval-side evidence selection.

    Defaults are conservative: at least one citable packet is required, unsafe
    packets are never selected, caution packets are allowed but can force
    fallback/review when they are the only selected evidence.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    min_citable_packets: int = Field(1, gt=0)
    max_selected_packets: int = Field(5, gt=0)
    allow_caution_evidence: bool = True
    allow_auxiliary_parent_context: bool = True
    require_citation: bool = True
    require_source_url: bool = True
    require_law_id: bool = True
    require_child_text: bool = True
    fallback_on_parent_context_only: bool = True
    fallback_on_all_evidence_caution: bool = False
    needs_review_on_all_evidence_caution: bool = True
    max_unsafe_packets: int = Field(0, ge=0)
    include_auxiliary_context_in_rendered_output: bool = True
    enable_eval_exact_target_gate: bool = True
    eval_missing_target_requires_fallback: bool = True


class FallbackReason(BaseModel):
    """Structured reason explaining fallback or review."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: FallbackReasonCode
    message: str = Field(..., min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)


class SelectionWarning(BaseModel):
    """Structured non-fatal warning from evidence selection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: SelectionWarningCode
    message: str = Field(..., min_length=1)
    packet_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class SelectedEvidence(BaseModel):
    """Evidence packet selected as future generation input."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    packet: EvidencePacket
    packet_id: str
    rank: int = Field(..., ge=1)
    score: float
    chunk_id: str | None = None
    citation: str | None = None
    safety_level: EvidenceSafetyLevel
    citation_scope: CitationScope
    has_auxiliary_context: bool = False
    warnings: list[SelectionWarning] = Field(default_factory=list)


class RejectedEvidence(BaseModel):
    """Evidence packet rejected by the selection gate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    packet: EvidencePacket
    packet_id: str
    rank: int = Field(..., ge=1)
    chunk_id: str | None = None
    reasons: list[EvidenceRejectionReason] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class EvidenceSelectionResult(BaseModel):
    """Selection decision and context prepared for future generation."""

    model_config = ConfigDict(extra="forbid")

    decision: AnswerabilityDecision
    selected_evidence: list[SelectedEvidence] = Field(default_factory=list)
    rejected_evidence: list[RejectedEvidence] = Field(default_factory=list)
    fallback_reasons: list[FallbackReason] = Field(default_factory=list)
    warnings: list[SelectionWarning] = Field(default_factory=list)
    rendered_context: str = ""
    selected_count: int = Field(0, ge=0)
    rejected_count: int = Field(0, ge=0)
    unsafe_rejected_count: int = Field(0, ge=0)
    caution_selected_count: int = Field(0, ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> EvidenceSelectionResult:
        """Require summary counts to match selected/rejected evidence."""
        if self.selected_count != len(self.selected_evidence):
            raise ValueError("selected_count must match selected evidence count")
        if self.rejected_count != len(self.rejected_evidence):
            raise ValueError("rejected_count must match rejected evidence count")
        expected_unsafe = sum(
            1
            for item in self.rejected_evidence
            if item.packet.safety_level == EvidenceSafetyLevel.UNSAFE
        )
        expected_caution = sum(
            1 for item in self.selected_evidence if item.safety_level == EvidenceSafetyLevel.CAUTION
        )
        if self.unsafe_rejected_count != expected_unsafe:
            raise ValueError("unsafe_rejected_count must match rejected unsafe evidence")
        if self.caution_selected_count != expected_caution:
            raise ValueError("caution_selected_count must match selected caution evidence")
        return self


def select_evidence_for_answer(
    evidence_bundle: EvidenceBundle,
    config: EvidenceSelectionConfig | None = None,
    *,
    expected_targets: Sequence[ExpectedTarget] | None = None,
    risk_flags: Sequence[EvidenceRiskFlag] | None = None,
) -> EvidenceSelectionResult:
    """Select citable evidence and decide if future generation may proceed.

    Args:
        evidence_bundle: Evidence packets from evidence safety.
        config: Optional selection settings.
        expected_targets: Optional manual/evaluation targets for stricter
            offline gating.
        risk_flags: Optional dense retrieval evaluation risk flags to surface in the decision.

    Returns:
        Structured answerability decision with selected/rejected evidence and
        rendered selected context.
    """
    settings = config or EvidenceSelectionConfig()
    selected: list[SelectedEvidence] = []
    rejected: list[RejectedEvidence] = []
    warnings: list[SelectionWarning] = []
    fallback_reasons: list[FallbackReason] = []
    seen_keys: set[str] = set()

    if not evidence_bundle.packets:
        fallback_reasons.append(_fallback(FallbackReasonCode.NO_EVIDENCE, "no evidence packets"))
        return _result(
            decision=AnswerabilityDecision.FALLBACK_REQUIRED,
            selected=[],
            rejected=[],
            fallback_reasons=fallback_reasons,
            warnings=[],
            rendered_context="",
        )

    for packet in evidence_bundle.packets:
        key = packet.chunk_id or packet.packet_id
        if key in seen_keys:
            rejected.append(
                _reject(
                    packet,
                    [EvidenceRejectionReason.DUPLICATE_EVIDENCE],
                    details={"dedup_key": key},
                )
            )
            continue
        seen_keys.add(key)

        reasons = _packet_rejection_reasons(packet, settings)
        if reasons:
            rejected.append(_reject(packet, reasons))
            continue
        selected.append(_select(packet, settings))

    selected = sorted(
        selected,
        key=lambda item: _selection_sort_key(item, expected_targets or ()),
    )[: settings.max_selected_packets]

    for item in selected:
        warnings.extend(item.warnings)
    warnings.extend(_risk_flag_warnings(risk_flags or ()))

    unsafe_rejected_count = sum(
        1 for item in rejected if item.packet.safety_level == EvidenceSafetyLevel.UNSAFE
    )
    if unsafe_rejected_count > settings.max_unsafe_packets:
        warnings.append(
            SelectionWarning(
                code=SelectionWarningCode.UNSAFE_EVIDENCE_REJECTED,
                message="unsafe evidence was rejected by the selection gate",
                details={
                    "unsafe_rejected_count": unsafe_rejected_count,
                    "max_unsafe_packets": settings.max_unsafe_packets,
                },
            )
        )

    if not selected:
        fallback_reasons.extend(_no_selection_reasons(rejected))
        return _result(
            decision=AnswerabilityDecision.FALLBACK_REQUIRED,
            selected=[],
            rejected=rejected,
            fallback_reasons=fallback_reasons,
            warnings=warnings,
            rendered_context="",
        )

    if len(selected) < settings.min_citable_packets:
        fallback_reasons.append(
            _fallback(
                FallbackReasonCode.INSUFFICIENT_SAFE_EVIDENCE,
                "fewer selected citable packets than required",
                details={
                    "selected_count": len(selected),
                    "min_citable_packets": settings.min_citable_packets,
                },
            )
        )

    if expected_targets is not None and settings.enable_eval_exact_target_gate:
        if not expected_targets:
            fallback_reasons.append(
                _fallback(
                    FallbackReasonCode.EXACT_TARGET_MISSING_IN_EVAL_MODE,
                    "evaluation target gate is active and no answerable target is defined",
                    details={"expected_targets": []},
                )
            )
        elif not any(
            _packet_matches_expected_target(item.packet, target)
            for item in selected
            for target in expected_targets
        ):
            fallback_reasons.append(
                _fallback(
                    FallbackReasonCode.EXACT_TARGET_MISSING_IN_EVAL_MODE,
                    "selected evidence does not match any expected evaluation target",
                    details={
                        "expected_targets": [
                            target.model_dump(mode="json") for target in expected_targets
                        ],
                    },
                )
            )

    if _has_high_citation_risk(risk_flags or (), selected):
        fallback_reasons.append(
            _fallback(
                FallbackReasonCode.HIGH_CITATION_RISK,
                "evaluation risk flags indicate elevated citation risk",
                details={"risk_codes": [flag.code for flag in risk_flags or ()]},
            )
        )

    all_caution = all(item.safety_level == EvidenceSafetyLevel.CAUTION for item in selected)
    all_parent_context_risk = all(_is_parent_context_only(item) for item in selected)
    if all_caution:
        reason = _fallback(
            FallbackReasonCode.ALL_SELECTED_EVIDENCE_CAUTION,
            "all selected evidence packets require caution",
        )
        warnings.append(
            SelectionWarning(
                code=SelectionWarningCode.ALL_SELECTED_EVIDENCE_CAUTION,
                message="all selected evidence packets are caution-level",
            )
        )
        if all_parent_context_risk and settings.fallback_on_parent_context_only:
            fallback_reasons.append(
                _fallback(
                    FallbackReasonCode.PARENT_CONTEXT_ONLY,
                    (
                        "selected evidence is caution-level because broader parent context "
                        "is auxiliary only"
                    ),
                )
            )
        elif all(_is_auxiliary_parent_context_only_caution(item) for item in selected):
            pass
        elif settings.fallback_on_all_evidence_caution:
            fallback_reasons.append(reason)
        elif settings.needs_review_on_all_evidence_caution:
            fallback_reasons.append(reason)

    decision = _decision_from_reasons(
        fallback_reasons,
        settings=settings,
        all_caution=all_caution,
    )
    rendered_context = ""
    if decision != AnswerabilityDecision.FALLBACK_REQUIRED:
        rendered_context = _render_selected_context(selected, settings)

    return _result(
        decision=decision,
        selected=selected,
        rejected=rejected,
        fallback_reasons=fallback_reasons,
        warnings=warnings,
        rendered_context=rendered_context,
    )


def _packet_rejection_reasons(
    packet: EvidencePacket,
    config: EvidenceSelectionConfig,
) -> list[EvidenceRejectionReason]:
    reasons: list[EvidenceRejectionReason] = []
    if packet.safety_level == EvidenceSafetyLevel.UNSAFE:
        reasons.append(EvidenceRejectionReason.UNSAFE_EVIDENCE)
    if config.require_citation and not packet.citation:
        reasons.append(EvidenceRejectionReason.MISSING_REQUIRED_CITATION)
    if config.require_law_id and not packet.law_id:
        reasons.append(EvidenceRejectionReason.MISSING_REQUIRED_LAW_ID)
    if config.require_source_url and not packet.source_url:
        reasons.append(EvidenceRejectionReason.MISSING_REQUIRED_SOURCE_URL)
    if config.require_child_text and packet.safe_citable_text is None:
        reasons.append(EvidenceRejectionReason.MISSING_REQUIRED_CHILD_TEXT)
    if packet.safety_level == EvidenceSafetyLevel.CAUTION and not config.allow_caution_evidence:
        reasons.append(EvidenceRejectionReason.CAUTION_EVIDENCE_NOT_ALLOWED)
    if (
        config.fallback_on_parent_context_only
        and packet.safe_citable_text is None
        and packet.auxiliary_context is not None
    ):
        reasons.append(EvidenceRejectionReason.PARENT_CONTEXT_ONLY)
    return _unique_reasons(reasons)


def _select(packet: EvidencePacket, config: EvidenceSelectionConfig) -> SelectedEvidence:
    warnings: list[SelectionWarning] = []
    if packet.safety_level == EvidenceSafetyLevel.CAUTION:
        warnings.append(
            SelectionWarning(
                code=SelectionWarningCode.CAUTION_EVIDENCE_SELECTED,
                message="caution-level evidence was selected; review safety issues before use",
                packet_id=packet.packet_id,
                details={"safety_issue_codes": [issue.code for issue in packet.safety_issues]},
            )
        )
    if packet.auxiliary_context is not None:
        code = (
            SelectionWarningCode.AUXILIARY_PARENT_CONTEXT_INCLUDED
            if config.include_auxiliary_context_in_rendered_output
            else SelectionWarningCode.AUXILIARY_PARENT_CONTEXT_SUPPRESSED
        )
        warnings.append(
            SelectionWarning(
                code=code,
                message="selected evidence has auxiliary parent context",
                packet_id=packet.packet_id,
            )
        )
    return SelectedEvidence(
        packet=packet,
        packet_id=packet.packet_id,
        rank=packet.rank,
        score=packet.score,
        chunk_id=packet.chunk_id,
        citation=packet.citation,
        safety_level=packet.safety_level,
        citation_scope=packet.citation_scope,
        has_auxiliary_context=packet.auxiliary_context is not None,
        warnings=warnings,
    )


def _is_parent_context_only(item: SelectedEvidence) -> bool:
    packet = item.packet
    return (
        item.citation_scope == CitationScope.UNSAFE_PARENT_CONTEXT
        and packet.safe_citable_text is None
        and packet.auxiliary_context is not None
    )


def _is_auxiliary_parent_context_only_caution(item: SelectedEvidence) -> bool:
    packet = item.packet
    allowed_issue_codes = {
        "parent_context_auxiliary_only",
        "parent_context_deduplicated",
    }
    issue_codes = {issue.code for issue in packet.safety_issues}
    return (
        item.safety_level == EvidenceSafetyLevel.CAUTION
        and item.citation_scope == CitationScope.CHILD_EXACT
        and packet.chunk_id is not None
        and packet.safe_citable_text is not None
        and packet.law_id is not None
        and packet.source_url is not None
        and packet.citation is not None
        and issue_codes <= allowed_issue_codes
    )


def _reject(
    packet: EvidencePacket,
    reasons: list[EvidenceRejectionReason],
    *,
    details: dict[str, Any] | None = None,
) -> RejectedEvidence:
    return RejectedEvidence(
        packet=packet,
        packet_id=packet.packet_id,
        rank=packet.rank,
        chunk_id=packet.chunk_id,
        reasons=_unique_reasons(reasons),
        details=details or {"safety_issue_codes": [issue.code for issue in packet.safety_issues]},
    )


def _no_selection_reasons(rejected: Sequence[RejectedEvidence]) -> list[FallbackReason]:
    if not rejected:
        return [_fallback(FallbackReasonCode.NO_CITABLE_EVIDENCE, "no citable evidence selected")]
    if all(item.packet.safety_level == EvidenceSafetyLevel.UNSAFE for item in rejected):
        return [
            _fallback(
                FallbackReasonCode.ALL_EVIDENCE_UNSAFE,
                "all available evidence packets were unsafe",
            )
        ]
    codes = {reason for item in rejected for reason in item.reasons}
    fallback_reasons: list[FallbackReason] = []
    if EvidenceRejectionReason.MISSING_REQUIRED_CITATION in codes:
        fallback_reasons.append(
            _fallback(FallbackReasonCode.MISSING_REQUIRED_CITATION, "citation metadata is missing")
        )
    if EvidenceRejectionReason.MISSING_REQUIRED_SOURCE_URL in codes:
        fallback_reasons.append(
            _fallback(
                FallbackReasonCode.MISSING_REQUIRED_SOURCE_URL,
                "source URL metadata is missing",
            )
        )
    if EvidenceRejectionReason.MISSING_REQUIRED_LAW_ID in codes:
        fallback_reasons.append(
            _fallback(FallbackReasonCode.MISSING_REQUIRED_LAW_ID, "law_id metadata is missing")
        )
    if EvidenceRejectionReason.MISSING_REQUIRED_CHILD_TEXT in codes:
        fallback_reasons.append(
            _fallback(FallbackReasonCode.MISSING_REQUIRED_CHILD_TEXT, "child text is missing")
        )
    if not fallback_reasons:
        fallback_reasons.append(
            _fallback(FallbackReasonCode.NO_CITABLE_EVIDENCE, "no citable evidence selected")
        )
    return fallback_reasons


def _decision_from_reasons(
    fallback_reasons: Sequence[FallbackReason],
    *,
    settings: EvidenceSelectionConfig,
    all_caution: bool,
) -> AnswerabilityDecision:
    if not fallback_reasons:
        return AnswerabilityDecision.ANSWER_ALLOWED
    fallback_codes = {reason.code for reason in fallback_reasons}
    hard_fallback_codes = {
        FallbackReasonCode.NO_EVIDENCE,
        FallbackReasonCode.NO_CITABLE_EVIDENCE,
        FallbackReasonCode.ALL_EVIDENCE_UNSAFE,
        FallbackReasonCode.INSUFFICIENT_SAFE_EVIDENCE,
        FallbackReasonCode.MISSING_REQUIRED_CITATION,
        FallbackReasonCode.MISSING_REQUIRED_SOURCE_URL,
        FallbackReasonCode.MISSING_REQUIRED_LAW_ID,
        FallbackReasonCode.MISSING_REQUIRED_CHILD_TEXT,
        FallbackReasonCode.PARENT_CONTEXT_ONLY,
        FallbackReasonCode.HIGH_CITATION_RISK,
    }
    if settings.eval_missing_target_requires_fallback:
        hard_fallback_codes.add(FallbackReasonCode.EXACT_TARGET_MISSING_IN_EVAL_MODE)
    if settings.fallback_on_all_evidence_caution:
        hard_fallback_codes.add(FallbackReasonCode.ALL_SELECTED_EVIDENCE_CAUTION)
    if fallback_codes & hard_fallback_codes:
        return AnswerabilityDecision.FALLBACK_REQUIRED
    if all_caution and settings.needs_review_on_all_evidence_caution:
        return AnswerabilityDecision.NEEDS_REVIEW
    return AnswerabilityDecision.NEEDS_REVIEW


def _render_selected_context(
    selected: Sequence[SelectedEvidence],
    config: EvidenceSelectionConfig,
) -> str:
    packets: list[EvidencePacket] = []
    for item in selected:
        packet = item.packet
        if not config.include_auxiliary_context_in_rendered_output:
            packet = packet.model_copy(update={"auxiliary_context": None})
        packets.append(packet)
    return "\n\n".join(packet.render() for packet in packets)


def _packet_matches_expected_target(packet: EvidencePacket, target: ExpectedTarget) -> bool:
    if not _same(packet.law_id, target.law_id):
        return False
    if not _same(packet.article_number, target.article_number):
        return False
    if target.match_level == "article":
        return True
    if not _same(packet.clause_number, target.clause_number):
        return False
    if target.match_level == "clause":
        return True
    return _same(packet.point_label, target.point_label)


def _packet_matches_any_expected_target(
    packet: EvidencePacket,
    expected_targets: Sequence[ExpectedTarget],
) -> bool:
    return any(_packet_matches_expected_target(packet, target) for target in expected_targets)


def _selection_sort_key(
    item: SelectedEvidence,
    expected_targets: Sequence[ExpectedTarget],
) -> tuple[int, int, int, float]:
    target_order = 0 if _packet_matches_any_expected_target(item.packet, expected_targets) else 1
    safety_order = 0 if item.safety_level == EvidenceSafetyLevel.SAFE else 1
    return (target_order, safety_order, item.rank, -item.score)


def _has_high_citation_risk(
    risk_flags: Sequence[EvidenceRiskFlag],
    selected: Sequence[SelectedEvidence],
) -> bool:
    if not risk_flags:
        return False
    high_risk_codes = {
        "expected_article_hit_without_exact_clause_hit",
        "child_provision_mismatch_under_expected_article",
        "parent_text_mentions_expected_article_but_chunk_metadata_mismatch",
        "top_result_wrong_article_when_expected_article_exists_lower",
    }
    if any(flag.code in high_risk_codes for flag in risk_flags):
        return True
    return all(item.citation_scope == CitationScope.UNSAFE_PARENT_CONTEXT for item in selected)


def _risk_flag_warnings(risk_flags: Sequence[EvidenceRiskFlag]) -> list[SelectionWarning]:
    return [
        SelectionWarning(
            code=SelectionWarningCode.EVALUATION_RISK_FLAG_PRESENT,
            message="evaluation risk flag was provided to evidence selection",
            details={"risk_code": flag.code, "rank": flag.rank, "chunk_id": flag.chunk_id},
        )
        for flag in risk_flags
    ]


def _result(
    *,
    decision: AnswerabilityDecision,
    selected: list[SelectedEvidence],
    rejected: list[RejectedEvidence],
    fallback_reasons: list[FallbackReason],
    warnings: list[SelectionWarning],
    rendered_context: str,
) -> EvidenceSelectionResult:
    return EvidenceSelectionResult(
        decision=decision,
        selected_evidence=selected,
        rejected_evidence=rejected,
        fallback_reasons=fallback_reasons,
        warnings=warnings,
        rendered_context=rendered_context,
        selected_count=len(selected),
        rejected_count=len(rejected),
        unsafe_rejected_count=sum(
            1 for item in rejected if item.packet.safety_level == EvidenceSafetyLevel.UNSAFE
        ),
        caution_selected_count=sum(
            1 for item in selected if item.safety_level == EvidenceSafetyLevel.CAUTION
        ),
    )


def _fallback(
    code: FallbackReasonCode,
    message: str,
    *,
    details: dict[str, Any] | None = None,
) -> FallbackReason:
    return FallbackReason(code=code, message=message, details=details or {})


def _unique_reasons(
    reasons: Sequence[EvidenceRejectionReason],
) -> list[EvidenceRejectionReason]:
    unique: list[EvidenceRejectionReason] = []
    for reason in reasons:
        if reason not in unique:
            unique.append(reason)
    return unique


def _same(left: str | None, right: str | None) -> bool:
    return (
        left is not None
        and right is not None
        and left.strip().casefold() == right.strip().casefold()
    )
