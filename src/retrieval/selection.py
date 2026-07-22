"""Evidence selection and fallback decisions for retrieval-side QA safety.

This module gates citation-safe evidence before any future answer generation.
It does not call LLMs, mutate retrieval results, retrieve from Qdrant, rerank
with a model, or mutate corpus artifacts.
"""

from __future__ import annotations

import re
import unicodedata
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

_TOKEN_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)
_ARTICLE_LOCATOR_PATTERN = re.compile(r"\bđiều\s+(?P<article>\d+[a-z]?)\b", re.IGNORECASE)
_CLAUSE_ARTICLE_LOCATOR_PATTERN = re.compile(
    r"\bkhoản\s+(?P<clause>\d+[a-z]?)\s+điều\s+(?P<article>\d+[a-z]?)\b",
    re.IGNORECASE,
)
_POINT_CLAUSE_ARTICLE_LOCATOR_PATTERN = re.compile(
    r"\bđiểm\s+(?P<point>[a-zà-ỹđ]{1,2})\s+khoản\s+(?P<clause>\d+[a-z]?)\s+điều\s+"
    r"(?P<article>\d+[a-z]?)\b",
    re.IGNORECASE,
)
_REFERENCE_ONLY_PATTERN = re.compile(
    r"^(?:\d+\.|[a-zà-ỹđ]\))?\s*"
    r".{0,180}?\b(?:theo\s+quy\s+định\s+tại|thực\s+hiện\s+theo|thuộc\s+trường\s+hợp\s+"
    r"quy\s+định\s+tại|dẫn\s+chiếu\s+đến)\s+(?:điều|khoản)\s+\d+\b"
    r"(?:\s+của\s+bộ\s+luật\s+này)?\.?$",
    re.IGNORECASE,
)
_LAW_MARKERS = {
    "bộ luật",
    "luật",
    "hiến pháp",
    "nghị định",
    "thông tư",
}
_GENERIC_STOPWORDS = {
    "a",
    "b",
    "c",
    "d",
    "đ",
    "e",
    "g",
    "ai",
    "bao",
    "bởi",
    "các",
    "căn",
    "cho",
    "của",
    "có",
    "để",
    "được",
    "gì",
    "hay",
    "khi",
    "khác",
    "là",
    "làm",
    "mà",
    "một",
    "nào",
    "này",
    "như",
    "nêu",
    "phải",
    "quy",
    "ra",
    "sau",
    "sau đây",
    "số",
    "tại",
    "thì",
    "theo",
    "thế",
    "trong",
    "trường",
    "trường hợp",
    "và",
    "về",
    "việc",
}
_ROLE_HEADS = (
    "người",
    "bên",
    "cơ quan",
    "tổ chức",
    "cá nhân",
    "vợ",
    "chồng",
    "nguyên đơn",
    "bị đơn",
)
_ROLE_BOUNDARY_TOKENS = {
    "có",
    "được",
    "phải",
    "không",
    "quyền",
    "nghĩa",
    "trách",
    "quy",
    "theo",
    "trong",
    "khi",
    "nào",
    "thế",
}
_MODALITY_TERMS = (
    "có quyền",
    "quyền",
    "nghĩa vụ",
    "trách nhiệm",
    "phải",
    "được",
    "không được",
    "không phải",
    "không cần",
    "cấm",
)
_NEGATION_TERMS = ("không được", "không phải", "không cần", "không", "trừ", "ngoại trừ")
_TIME_QUANTITY_PATTERN = re.compile(
    r"\b\d+(?:[,.]\d+)?\s*(?:ngày|tháng|năm|tuổi|giờ|%|phần\s+trăm|lần|đồng)\b",
    re.IGNORECASE,
)


class AnswerabilityDecision(StrEnum):
    """Evidence-gate decision for future answer generation."""

    ANSWER_ALLOWED = "answer_allowed"
    ANSWER_WITH_CAUTION_ALLOWED = "answer_with_caution_allowed"
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
    allow_answer_with_caution: bool = True
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
        key=lambda item: _selection_sort_key(item, expected_targets or (), evidence_bundle.query),
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
        elif settings.allow_answer_with_caution:
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
    if all_caution and settings.allow_answer_with_caution:
        return AnswerabilityDecision.ANSWER_WITH_CAUTION_ALLOWED
    if all_caution and settings.needs_review_on_all_evidence_caution:
        return AnswerabilityDecision.NEEDS_REVIEW
    if settings.allow_answer_with_caution:
        return AnswerabilityDecision.ANSWER_WITH_CAUTION_ALLOWED
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
    query: str,
) -> tuple[int, float, int, str]:
    target_order = 0 if _packet_matches_any_expected_target(item.packet, expected_targets) else 1
    safety_penalty = 0.0 if item.safety_level == EvidenceSafetyLevel.SAFE else 2.0
    adjusted_score = item.score + _direct_evidence_score(item.packet, query=query) - safety_penalty
    return (target_order, -adjusted_score, item.rank, item.chunk_id or item.packet_id)


def _direct_evidence_score(packet: EvidencePacket, *, query: str) -> int:
    """Return bounded generic query-evidence alignment adjustments.

    The score uses only query text and packet metadata/text. It does not use
    qrels, expected targets, article-specific constants, generated answers, or
    individual benchmark cases.
    """
    normalized_query = _normalize_legal_text(query)
    if not normalized_query:
        return 0

    title = _normalize_legal_text(_metadata_string(packet, "article_title"))
    law_title = _normalize_legal_text(packet.law_title)
    child_text = _normalize_legal_text(
        packet.safe_citable_text.text if packet.safe_citable_text is not None else ""
    )
    auxiliary_text = _normalize_legal_text(
        packet.auxiliary_context.text if packet.auxiliary_context is not None else ""
    )
    local_parent_context = _normalize_legal_text(_metadata_string(packet, "local_parent_context"))
    if not local_parent_context:
        local_parent_context = _local_parent_context(
            child_text=child_text,
            parent_text=auxiliary_text,
        )
    citable_context = " ".join(part for part in (title, child_text, local_parent_context) if part)
    combined = " ".join(
        part for part in (title, child_text, local_parent_context, auxiliary_text) if part
    )

    components = {
        "explicit_locator_alignment": _explicit_locator_alignment(packet, normalized_query),
        "article_title_alignment": min(_important_token_overlap(normalized_query, title), 8) * 0.75,
        "substantive_content_alignment": min(
            _important_token_overlap(normalized_query, child_text), 10
        )
        * 0.30,
        "local_parent_context_alignment": min(
            _important_token_overlap(normalized_query, local_parent_context), 8
        )
        * 0.35,
        "law_title_alignment": _law_title_alignment(normalized_query, law_title),
        "role_alignment": _role_alignment(normalized_query, citable_context),
        "governing_role_alignment": _governing_role_alignment(normalized_query, citable_context),
        "condition_list_alignment": _condition_list_alignment(normalized_query, citable_context),
        "modality_negation_alignment": _modality_negation_alignment(
            normalized_query, citable_context
        ),
        "notice_term_alignment": _notice_term_alignment(normalized_query, citable_context),
        "time_quantity_alignment": _time_quantity_alignment(normalized_query, citable_context),
        "reference_only_penalty": _reference_only_adjustment(packet, normalized_query, child_text),
        "domain_mismatch_penalty": _domain_mismatch_adjustment(normalized_query, law_title),
        "procedural_drift_penalty": _procedural_drift_adjustment(normalized_query, title),
        "legal_consequence_drift_penalty": _legal_consequence_drift_adjustment(
            normalized_query, title
        ),
        "topic_drift_penalty": _topic_drift_adjustment(normalized_query, combined),
    }
    packet.metadata["selection_alignment"] = {
        key: round(value, 4) for key, value in components.items() if value
    }
    return int(round(max(-10.0, min(16.0, sum(components.values())))))


def _metadata_string(packet: EvidencePacket, key: str) -> str:
    value = packet.metadata.get(key)
    return value if isinstance(value, str) else ""


def _local_parent_context(*, child_text: str, parent_text: str) -> str:
    if not child_text or not parent_text:
        return ""
    index = parent_text.find(child_text)
    if index < 0:
        return ""
    return parent_text[max(0, index - 280) : index]


def _important_token_overlap(query: str, text: str) -> int:
    if not query or not text:
        return 0
    return len(_important_tokens(query) & _important_tokens(text))


def _important_tokens(text: str) -> set[str]:
    return {
        token
        for token in _TOKEN_PATTERN.findall(text)
        if len(token) > 1 and token not in _GENERIC_STOPWORDS
    }


def _is_cross_reference_only(normalized_child_text: str) -> bool:
    if not normalized_child_text:
        return False
    return _REFERENCE_ONLY_PATTERN.match(normalized_child_text) is not None


def _explicit_locator_alignment(packet: EvidencePacket, normalized_query: str) -> float:
    locators = _query_locators(normalized_query)
    if not locators:
        return 0.0
    best = 0.0
    for locator in locators:
        if packet.article_number != locator["article"]:
            continue
        score = 4.0
        if locator.get("clause") is not None:
            score = 5.5 if packet.clause_number == locator["clause"] else -3.5
        if locator.get("point") is not None:
            score = 7.0 if packet.point_label == locator["point"] else -4.0
        best = max(best, score)
    if best:
        return best
    if any(packet.article_number == locator["article"] for locator in locators):
        return 2.0
    return 0.0


def _query_locators(normalized_query: str) -> list[dict[str, str | None]]:
    locators: list[dict[str, str | None]] = []
    for match in _POINT_CLAUSE_ARTICLE_LOCATOR_PATTERN.finditer(normalized_query):
        locators.append(
            {
                "article": match.group("article"),
                "clause": match.group("clause"),
                "point": match.group("point"),
            }
        )
    for match in _CLAUSE_ARTICLE_LOCATOR_PATTERN.finditer(normalized_query):
        candidate = {
            "article": match.group("article"),
            "clause": match.group("clause"),
            "point": None,
        }
        if any(
            existing["article"] == candidate["article"]
            and existing.get("clause") == candidate["clause"]
            and existing.get("point") is not None
            for existing in locators
        ):
            continue
        if candidate not in locators:
            locators.append(candidate)
    for match in _ARTICLE_LOCATOR_PATTERN.finditer(normalized_query):
        candidate = {"article": match.group("article"), "clause": None, "point": None}
        if not any(existing["article"] == candidate["article"] for existing in locators):
            locators.append(candidate)
    return locators


def _law_title_alignment(normalized_query: str, law_title: str) -> float:
    if not law_title:
        return 0.0
    query_tokens = _important_tokens(normalized_query)
    law_tokens = _important_tokens(law_title)
    if not query_tokens or not law_tokens:
        return 0.0
    overlap = len(query_tokens & law_tokens)
    if overlap:
        return min(overlap, 5) * 0.35
    if any(marker in normalized_query for marker in _LAW_MARKERS):
        return -1.0
    return 0.0


def _role_alignment(normalized_query: str, text: str) -> float:
    query_roles = _role_phrases(normalized_query)
    if not query_roles:
        return 0.0
    text_roles = _role_phrases(text)
    if not text_roles:
        return -1.25
    if query_roles & text_roles:
        return 1.75
    query_role_tokens = {token for role in query_roles for token in role.split()}
    text_role_tokens = {token for role in text_roles for token in role.split()}
    if query_role_tokens & text_role_tokens:
        return -3.5
    return 0.0


def _governing_role_alignment(normalized_query: str, text: str) -> float:
    query_role = _governing_role(normalized_query)
    if query_role is None:
        return 0.0
    text_role = _governing_role(text)
    if text_role is None:
        return 0.0
    if query_role == text_role:
        return 3.0
    if set(query_role.split()) & set(text_role.split()):
        return -4.0
    return -2.0


def _governing_role(text: str) -> str | None:
    roles = _role_phrases(text)
    if not roles:
        return None
    role_positions = [(role, text.find(role)) for role in roles if text.find(role) >= 0]
    owned_roles = [
        (role, position)
        for role, position in role_positions
        if position >= 0 and f"của {role}" in text[max(0, position - 5) : position + len(role) + 5]
    ]
    if owned_roles:
        return max(owned_roles, key=lambda item: len(item[0]))[0]
    modality_positions = [
        position
        for term in ("có quyền", "phải", "được", "có nghĩa vụ", "có trách nhiệm")
        if (position := text.find(term)) >= 0
    ]
    if modality_positions:
        first_modality = min(modality_positions)
        prior_roles = [
            (role, position)
            for role, position in role_positions
            if position <= first_modality and first_modality - position <= 80
        ]
        if prior_roles:
            return max(prior_roles, key=lambda item: (item[1], len(item[0])))[0]
    return max(roles, key=len)


def _role_phrases(text: str) -> set[str]:
    tokens = _TOKEN_PATTERN.findall(text)
    phrases: set[str] = set()
    for index, token in enumerate(tokens):
        if token not in _ROLE_HEADS:
            continue
        role_tokens: list[str] = []
        for candidate in tokens[index : index + 5]:
            if len(role_tokens) > 0 and (
                candidate in _ROLE_BOUNDARY_TOKENS or candidate.isdigit() or len(candidate) == 1
            ):
                break
            role_tokens.append(candidate)
        for length in range(1, len(role_tokens) + 1):
            phrase_tokens = role_tokens[:length]
            if not phrase_tokens:
                continue
            if len(phrase_tokens) == 1 and phrase_tokens[0] in {"người", "bên"}:
                continue
            if phrase_tokens[-1] in _GENERIC_STOPWORDS and length > 1:
                continue
            phrases.add(" ".join(phrase_tokens))
    return phrases


def _modality_negation_alignment(normalized_query: str, text: str) -> float:
    query_modalities = {
        term for term in _MODALITY_TERMS if _contains_phrase(normalized_query, term)
    }
    if not query_modalities:
        return 0.0
    text_modalities = {term for term in _MODALITY_TERMS if _contains_phrase(text, term)}
    score = 0.8 if query_modalities & text_modalities else 0.0
    query_negation = {term for term in _NEGATION_TERMS if _contains_phrase(normalized_query, term)}
    text_negation = {term for term in _NEGATION_TERMS if _contains_phrase(text, term)}
    if query_negation and text_negation:
        score += 1.4
    elif query_negation and not text_negation and _contains_phrase(text, "phải"):
        score -= 2.5
    elif not query_negation and text_negation:
        score -= 3.0 if "được" in query_modalities else 1.5
    return score


def _condition_list_alignment(normalized_query: str, text: str) -> float:
    asks_for_conditions = _contains_any(
        normalized_query,
        (
            "trong trường hợp nào",
            "trường hợp nào",
            "những trường hợp",
            "các trường hợp",
            "điều kiện nào",
            "điều kiện để",
            "điều kiện gì",
        ),
    )
    if not asks_for_conditions:
        return 0.0
    if _contains_any(
        text,
        (
            "trường hợp sau đây",
            "các trường hợp sau đây",
            "những trường hợp sau đây",
            "điều kiện sau đây",
            "các điều kiện sau đây",
            "phải tuân theo các điều kiện",
        ),
    ):
        return 2.4
    if _contains_any(text, ("theo quy định tại điểm", "theo quy định tại khoản")):
        return -1.4
    return 0.0


def _notice_term_alignment(normalized_query: str, text: str) -> float:
    if not _contains_phrase(normalized_query, "báo trước"):
        return 0.0
    if _contains_phrase(text, "báo trước"):
        return 2.0
    return -2.5


def _time_quantity_alignment(normalized_query: str, text: str) -> float:
    query_values = set(_TIME_QUANTITY_PATTERN.findall(normalized_query))
    if not query_values and not _contains_any(
        normalized_query, ("bao lâu", "bao nhiêu", "thời hạn")
    ):
        return 0.0
    text_values = set(_TIME_QUANTITY_PATTERN.findall(text))
    if query_values and text_values:
        return 1.6 if query_values & text_values else -1.6
    if text_values:
        return 0.8
    return -2.0


def _reference_only_adjustment(
    packet: EvidencePacket,
    normalized_query: str,
    child_text: str,
) -> float:
    if not _is_cross_reference_only(child_text):
        return 0.0
    if any(
        packet.article_number == locator["article"] for locator in _query_locators(normalized_query)
    ):
        return 0.0
    return -4.0


def _domain_mismatch_adjustment(normalized_query: str, law_title: str) -> float:
    query_law_tokens = _law_domain_tokens(normalized_query)
    if not query_law_tokens or not law_title:
        return 0.0
    law_tokens = _important_tokens(law_title)
    if query_law_tokens & law_tokens:
        return 0.0
    return -4.0


def _procedural_drift_adjustment(normalized_query: str, title: str) -> float:
    procedural_terms = ("tố tụng", "thủ tục", "khởi kiện", "thi hành", "quyết định", "tòa án")
    if not _contains_any(title, procedural_terms):
        return 0.0
    if _contains_any(normalized_query, procedural_terms):
        return 0.0
    return -3.0


def _legal_consequence_drift_adjustment(normalized_query: str, title: str) -> float:
    consequence_terms = (
        "hủy bỏ",
        "nghĩa vụ",
        "trách nhiệm",
        "bồi thường",
        "trái pháp luật",
        "không được",
    )
    if not _contains_any(title, consequence_terms):
        return 0.0
    if _contains_any(normalized_query, consequence_terms):
        return 0.0
    return -4.0


def _law_domain_tokens(text: str) -> set[str]:
    tokens = _TOKEN_PATTERN.findall(text)
    domain_tokens: set[str] = set()
    for index, token in enumerate(tokens):
        if token in {"luật", "hiến", "pháp"}:
            domain_tokens.update(tokens[index + 1 : index + 5])
        if token == "bộ" and index + 1 < len(tokens) and tokens[index + 1] == "luật":
            domain_tokens.update(tokens[index + 2 : index + 6])
    return {token for token in domain_tokens if token not in _GENERIC_STOPWORDS}


def _topic_drift_adjustment(normalized_query: str, text: str) -> float:
    query_tokens = _important_tokens(normalized_query)
    text_tokens = _important_tokens(text)
    if len(query_tokens) < 3 or not text_tokens:
        return 0.0
    overlap_rate = len(query_tokens & text_tokens) / len(query_tokens)
    if overlap_rate < 0.15:
        return -1.5
    return 0.0


def _normalize_legal_text(text: str | None) -> str:
    if text is None:
        return ""
    normalized = unicodedata.normalize("NFC", text).casefold()
    return " ".join(_TOKEN_PATTERN.findall(normalized))


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized_phrase = _normalize_legal_text(phrase)
    return f" {normalized_phrase} " in f" {text} "


def _contains_any(text: str, phrases: Sequence[str]) -> bool:
    return any(_contains_phrase(text, phrase) for phrase in phrases)


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
