"""Evidence safety and context assembly for retrieved legal chunks.

This module turns dense retrieval baseline retrieval results into citation-aware evidence
packets. It does not retrieve, rerank, call LLMs, mutate Qdrant, or mutate
corpus files.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.retrieval.models import RetrievalIssueSeverity, RetrievalResult, RetrievedChunk

TRUNCATION_MARKER = "...[TRUNCATED]"


class EvidenceSafetyLevel(StrEnum):
    """Safety level for downstream use of retrieved evidence."""

    SAFE = "safe"
    CAUTION = "caution"
    UNSAFE = "unsafe"


class CitationScope(StrEnum):
    """Scope that can be safely associated with a packet citation."""

    CHILD_EXACT = "child_exact"
    ARTICLE_CONTEXT = "article_context"
    UNSAFE_PARENT_CONTEXT = "unsafe_parent_context"
    MISSING_CITATION = "missing_citation"


class ParentContextPolicy(StrEnum):
    """How parent Article context may be used in an evidence packet."""

    ABSENT = "absent"
    EXCLUDED = "excluded"
    AUXILIARY_ONLY = "auxiliary_only"
    CITABLE_ARTICLE_CONTEXT = "citable_article_context"
    EQUIVALENT_TO_CHILD = "equivalent_to_child"
    DEDUPLICATED = "deduplicated"


class EvidenceIssueSeverity(StrEnum):
    """Severity values for evidence safety diagnostics."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class EvidenceCitation(BaseModel):
    """Citation and legal hierarchy metadata for one evidence packet."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    citation: str | None = None
    law_id: str | None = None
    law_title: str | None = None
    article_number: str | None = None
    clause_number: str | None = None
    point_label: str | None = None
    source_url: str | None = None
    source_domain: str | None = None


class EvidenceText(BaseModel):
    """Text value with explicit truncation metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str
    truncated: bool = False
    original_chars: int = Field(..., ge=0)
    max_chars: int | None = Field(None, gt=0)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        """Reject blank evidence text."""
        if not value.strip():
            raise ValueError("evidence text must not be blank")
        return value


class EvidenceSafetyIssue(BaseModel):
    """Structured issue explaining evidence safety classification."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    severity: EvidenceIssueSeverity
    rank: int | None = Field(None, ge=1)
    chunk_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ContextAssemblyConfig(BaseModel):
    """Configuration for building evidence packets and rendered context.

    Legal assumptions:
        Truncated text is marked explicitly. Parent Article context is auxiliary
        by default for child chunks and must not be cited as if it were the
        retrieved child provision.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_packets: int = Field(10, gt=0)
    include_parent_text: bool = True
    max_child_chars: int = Field(2000, gt=0)
    max_parent_chars: int = Field(4000, gt=0)
    deduplicate_parent_text: bool = True
    include_scores: bool = True
    min_safety_level: EvidenceSafetyLevel = EvidenceSafetyLevel.CAUTION

    @model_validator(mode="after")
    def validate_truncation_limits(self) -> ContextAssemblyConfig:
        """Require truncation limits to leave room for the truncation marker."""
        if self.max_child_chars <= len(TRUNCATION_MARKER):
            raise ValueError("max_child_chars must be greater than the truncation marker length")
        if self.max_parent_chars <= len(TRUNCATION_MARKER):
            raise ValueError("max_parent_chars must be greater than the truncation marker length")
        return self


class EvidencePacket(BaseModel):
    """Citation-aware evidence packet derived from one retrieved chunk."""

    model_config = ConfigDict(extra="forbid")

    packet_id: str = Field(..., min_length=1)
    rank: int = Field(..., ge=1)
    score: float
    chunk_id: str | None = None
    law_id: str | None = None
    law_title: str | None = None
    citation: str | None = None
    article_number: str | None = None
    clause_number: str | None = None
    point_label: str | None = None
    level: str | None = None
    chunk_kind: str | None = None
    source_url: str | None = None
    source_domain: str | None = None
    citation_metadata: EvidenceCitation
    child_text: EvidenceText | None = None
    parent_text: EvidenceText | None = None
    safe_citable_text: EvidenceText | None = None
    auxiliary_context: EvidenceText | None = None
    citation_scope: CitationScope
    parent_context_policy: ParentContextPolicy
    safety_level: EvidenceSafetyLevel
    safety_issues: list[EvidenceSafetyIssue] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[dict[str, Any]] = Field(default_factory=list)

    def render(self, *, include_scores: bool = True) -> str:
        """Render one packet with citable text separated from auxiliary context."""
        lines = [f"[{self.packet_id}]"]
        if include_scores:
            lines.append(f"Rank: {self.rank} | Score: {self.score:.6f}")
        lines.append(f"Safety: {self.safety_level}")
        lines.append(f"Citation scope: {self.citation_scope}")
        if self.citation:
            lines.append(f"Citation: {self.citation}")
        else:
            lines.append("Citation: MISSING")
        if self.source_url:
            lines.append(f"Source: {self.source_url}")
        if self.safe_citable_text is not None:
            lines.append("Citable text:")
            lines.append(self.safe_citable_text.text)
        else:
            lines.append("Citable text: UNSAFE OR MISSING")
        if self.auxiliary_context is not None:
            lines.append("")
            lines.append(
                "Auxiliary article context, not directly citable under this child citation:"
            )
            lines.append(self.auxiliary_context.text)
        if self.safety_issues:
            lines.append("")
            lines.append("Safety issues:")
            for issue in self.safety_issues:
                lines.append(f"- {issue.severity}: {issue.code}: {issue.message}")
        return "\n".join(lines)


class EvidenceBundle(BaseModel):
    """Ordered evidence packets and rendered context metadata."""

    model_config = ConfigDict(extra="forbid")

    query: str
    collection_name: str
    vector_name: str
    top_k: int = Field(..., gt=0)
    packets: list[EvidencePacket] = Field(default_factory=list)
    total_packets: int = Field(0, ge=0)
    safe_count: int = Field(0, ge=0)
    caution_count: int = Field(0, ge=0)
    unsafe_count: int = Field(0, ge=0)
    issue_count: int = Field(0, ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> EvidenceBundle:
        """Require summary counts to match packet contents."""
        if self.total_packets != len(self.packets):
            raise ValueError("total_packets must match packet count")
        expected_safe = sum(
            1 for packet in self.packets if packet.safety_level == EvidenceSafetyLevel.SAFE
        )
        expected_caution = sum(
            1 for packet in self.packets if packet.safety_level == EvidenceSafetyLevel.CAUTION
        )
        expected_unsafe = sum(
            1 for packet in self.packets if packet.safety_level == EvidenceSafetyLevel.UNSAFE
        )
        expected_issues = sum(len(packet.safety_issues) for packet in self.packets)
        if (
            self.safe_count != expected_safe
            or self.caution_count != expected_caution
            or self.unsafe_count != expected_unsafe
            or self.issue_count != expected_issues
        ):
            raise ValueError("bundle counts must match packet safety summaries")
        return self

    def render_context(self) -> str:
        """Render the bundle as citation-safe context for future generation."""
        return "\n\n".join(packet.render() for packet in self.packets)


def build_evidence_bundle(
    retrieval_result: RetrievalResult,
    config: ContextAssemblyConfig | None = None,
) -> EvidenceBundle:
    """Build a citation-safe evidence bundle from a retrieval result.

    Args:
        retrieval_result: Typed dense retrieval result.
        config: Optional context assembly settings.

    Returns:
        Evidence bundle ordered by retrieval rank, with duplicate chunks and
        repeated parent Article context handled conservatively.
    """
    settings = config or ContextAssemblyConfig()
    packets: list[EvidencePacket] = []
    seen_chunk_ids: set[str] = set()
    seen_parent_keys: set[str] = set()

    for chunk in retrieval_result.results:
        if len(packets) >= settings.max_packets:
            break
        if chunk.chunk_id and chunk.chunk_id in seen_chunk_ids:
            continue
        packet = build_evidence_packet(chunk, config=settings)
        if chunk.chunk_id:
            seen_chunk_ids.add(chunk.chunk_id)
        if settings.deduplicate_parent_text and packet.auxiliary_context is not None:
            parent_key = _parent_dedup_key(chunk)
            if parent_key in seen_parent_keys:
                packet = packet.model_copy(
                    update={
                        "auxiliary_context": None,
                        "parent_context_policy": ParentContextPolicy.DEDUPLICATED,
                        "safety_issues": [
                            *packet.safety_issues,
                            _issue(
                                code="parent_context_deduplicated",
                                message=(
                                    "repeated parent Article context was omitted from "
                                    "rendered auxiliary context"
                                ),
                                severity=EvidenceIssueSeverity.INFO,
                                rank=chunk.rank,
                                chunk_id=chunk.chunk_id,
                            ),
                        ],
                    }
                )
            else:
                seen_parent_keys.add(parent_key)
        if _safety_allows(packet.safety_level, settings.min_safety_level):
            packets.append(packet)

    return EvidenceBundle(
        query=retrieval_result.query,
        collection_name=retrieval_result.collection_name,
        vector_name=retrieval_result.vector_name,
        top_k=retrieval_result.top_k,
        packets=packets,
        total_packets=len(packets),
        safe_count=sum(1 for packet in packets if packet.safety_level == EvidenceSafetyLevel.SAFE),
        caution_count=sum(
            1 for packet in packets if packet.safety_level == EvidenceSafetyLevel.CAUTION
        ),
        unsafe_count=sum(
            1 for packet in packets if packet.safety_level == EvidenceSafetyLevel.UNSAFE
        ),
        issue_count=sum(len(packet.safety_issues) for packet in packets),
    )


def build_evidence_packet(
    chunk: RetrievedChunk,
    *,
    config: ContextAssemblyConfig | None = None,
) -> EvidencePacket:
    """Build one evidence packet and classify its citation safety."""
    settings = config or ContextAssemblyConfig()
    issues = _base_safety_issues(chunk)
    child_text = _evidence_text(chunk.text, max_chars=settings.max_child_chars)
    parent_text = _evidence_text(chunk.parent_text, max_chars=settings.max_parent_chars)

    if child_text is not None and child_text.truncated:
        issues.append(
            _issue(
                code="child_text_truncated",
                message="citable child text was truncated in the rendered evidence packet",
                severity=EvidenceIssueSeverity.WARNING,
                rank=chunk.rank,
                chunk_id=chunk.chunk_id,
            )
        )
    if parent_text is not None and parent_text.truncated:
        issues.append(
            _issue(
                code="parent_text_truncated",
                message="auxiliary parent context was truncated in the rendered evidence packet",
                severity=EvidenceIssueSeverity.WARNING,
                rank=chunk.rank,
                chunk_id=chunk.chunk_id,
            )
        )

    parent_policy = _parent_context_policy(chunk, child_text, parent_text, settings)
    citation_scope = _citation_scope(chunk, parent_policy, child_text)
    auxiliary_context = _auxiliary_context(parent_text, parent_policy)
    if parent_policy == ParentContextPolicy.AUXILIARY_ONLY:
        issues.append(
            _issue(
                code="parent_context_auxiliary_only",
                message=(
                    "parent_text contains broader Article context and must not be cited "
                    "as if it were the retrieved child provision"
                ),
                severity=EvidenceIssueSeverity.WARNING,
                rank=chunk.rank,
                chunk_id=chunk.chunk_id,
                details={
                    "citation_scope": citation_scope,
                    "article_number": chunk.article_number,
                    "clause_number": chunk.clause_number,
                    "point_label": chunk.point_label,
                },
            )
        )

    safety_level = _safety_level(issues, parent_policy)
    safe_citable_text = child_text if safety_level != EvidenceSafetyLevel.UNSAFE else None

    return EvidencePacket(
        packet_id=f"E{chunk.rank}",
        rank=chunk.rank,
        score=chunk.score,
        chunk_id=chunk.chunk_id,
        law_id=chunk.law_id,
        law_title=chunk.law_name,
        citation=chunk.citation,
        article_number=chunk.article_number,
        clause_number=chunk.clause_number,
        point_label=chunk.point_label,
        level=chunk.level,
        chunk_kind=chunk.chunk_kind,
        source_url=chunk.source_url,
        source_domain=chunk.source_domain,
        citation_metadata=EvidenceCitation(
            citation=chunk.citation,
            law_id=chunk.law_id,
            law_title=chunk.law_name,
            article_number=chunk.article_number,
            clause_number=chunk.clause_number,
            point_label=chunk.point_label,
            source_url=chunk.source_url,
            source_domain=chunk.source_domain,
        ),
        child_text=child_text,
        parent_text=parent_text,
        safe_citable_text=safe_citable_text,
        auxiliary_context=auxiliary_context,
        citation_scope=citation_scope,
        parent_context_policy=parent_policy,
        safety_level=safety_level,
        safety_issues=issues,
        metadata=_packet_metadata(chunk),
        warnings=chunk.warnings,
    )


def _base_safety_issues(chunk: RetrievedChunk) -> list[EvidenceSafetyIssue]:
    issues: list[EvidenceSafetyIssue] = []
    if not chunk.citation:
        issues.append(
            _issue(
                code="missing_citation",
                message="retrieved chunk is missing citation metadata",
                severity=EvidenceIssueSeverity.ERROR,
                rank=chunk.rank,
                chunk_id=chunk.chunk_id,
            )
        )
    if not chunk.law_id:
        issues.append(
            _issue(
                code="missing_law_id",
                message="retrieved chunk is missing law_id metadata",
                severity=EvidenceIssueSeverity.ERROR,
                rank=chunk.rank,
                chunk_id=chunk.chunk_id,
            )
        )
    if not chunk.source_url:
        issues.append(
            _issue(
                code="missing_source_url",
                message="retrieved chunk is missing source_url metadata",
                severity=EvidenceIssueSeverity.ERROR,
                rank=chunk.rank,
                chunk_id=chunk.chunk_id,
            )
        )
    if not chunk.text:
        issues.append(
            _issue(
                code="missing_child_text",
                message="retrieved chunk is missing child text",
                severity=EvidenceIssueSeverity.ERROR,
                rank=chunk.rank,
                chunk_id=chunk.chunk_id,
            )
        )
    if chunk.is_empty_or_repealed:
        issues.append(
            _issue(
                code="empty_or_repealed_chunk",
                message="retrieved chunk is flagged as empty or repealed",
                severity=EvidenceIssueSeverity.ERROR,
                rank=chunk.rank,
                chunk_id=chunk.chunk_id,
            )
        )
    if chunk.is_source_unit_repealed:
        issues.append(
            _issue(
                code="source_unit_repealed",
                message="retrieved source unit is flagged as repealed",
                severity=EvidenceIssueSeverity.ERROR,
                rank=chunk.rank,
                chunk_id=chunk.chunk_id,
            )
        )
    for retrieval_issue in chunk.issues:
        severity = (
            EvidenceIssueSeverity.ERROR
            if retrieval_issue.severity == RetrievalIssueSeverity.ERROR
            else EvidenceIssueSeverity.WARNING
        )
        issues.append(
            _issue(
                code=f"retrieval_issue:{retrieval_issue.code}",
                message=retrieval_issue.message,
                severity=severity,
                rank=retrieval_issue.rank or chunk.rank,
                chunk_id=retrieval_issue.chunk_id or chunk.chunk_id,
                details=retrieval_issue.details,
            )
        )
    return issues


def _packet_metadata(chunk: RetrievedChunk) -> dict[str, Any]:
    metadata = dict(chunk.metadata)
    if chunk.article_title:
        metadata.setdefault("article_title", chunk.article_title)
    if chunk.hierarchy_path:
        metadata.setdefault("hierarchy_path", chunk.hierarchy_path)
    local_context = _local_parent_context(chunk)
    if local_context:
        metadata.setdefault("local_parent_context", local_context)
    return metadata


def _local_parent_context(chunk: RetrievedChunk) -> str:
    if not chunk.text or not chunk.parent_text:
        return ""
    child_text = _normalize_whitespace(chunk.text)
    parent_text = _normalize_whitespace(chunk.parent_text)
    if not child_text or not parent_text:
        return ""
    index = parent_text.find(child_text)
    if index < 0:
        return ""
    return parent_text[max(0, index - 300) : index]


def _parent_context_policy(
    chunk: RetrievedChunk,
    child_text: EvidenceText | None,
    parent_text: EvidenceText | None,
    config: ContextAssemblyConfig,
) -> ParentContextPolicy:
    if parent_text is None:
        return ParentContextPolicy.ABSENT
    if not config.include_parent_text:
        return ParentContextPolicy.EXCLUDED
    if _is_article_level(chunk):
        return ParentContextPolicy.CITABLE_ARTICLE_CONTEXT
    if child_text is not None and _texts_equivalent(child_text.text, parent_text.text):
        return ParentContextPolicy.EQUIVALENT_TO_CHILD
    return ParentContextPolicy.AUXILIARY_ONLY


def _citation_scope(
    chunk: RetrievedChunk,
    parent_policy: ParentContextPolicy,
    child_text: EvidenceText | None,
) -> CitationScope:
    if not chunk.citation:
        return CitationScope.MISSING_CITATION
    if parent_policy == ParentContextPolicy.CITABLE_ARTICLE_CONTEXT:
        return CitationScope.ARTICLE_CONTEXT
    if parent_policy == ParentContextPolicy.AUXILIARY_ONLY and child_text is None:
        return CitationScope.UNSAFE_PARENT_CONTEXT
    return CitationScope.CHILD_EXACT


def _auxiliary_context(
    parent_text: EvidenceText | None,
    parent_policy: ParentContextPolicy,
) -> EvidenceText | None:
    if parent_policy == ParentContextPolicy.AUXILIARY_ONLY:
        return parent_text
    return None


def _safety_level(
    issues: Sequence[EvidenceSafetyIssue],
    parent_policy: ParentContextPolicy,
) -> EvidenceSafetyLevel:
    if any(issue.severity == EvidenceIssueSeverity.ERROR for issue in issues):
        return EvidenceSafetyLevel.UNSAFE
    if parent_policy == ParentContextPolicy.AUXILIARY_ONLY:
        return EvidenceSafetyLevel.CAUTION
    if any(issue.severity == EvidenceIssueSeverity.WARNING for issue in issues):
        return EvidenceSafetyLevel.CAUTION
    return EvidenceSafetyLevel.SAFE


def _evidence_text(text: str | None, *, max_chars: int) -> EvidenceText | None:
    normalized = _normalize_whitespace(text)
    if not normalized:
        return None
    if len(normalized) <= max_chars:
        return EvidenceText(
            text=normalized,
            truncated=False,
            original_chars=len(normalized),
            max_chars=max_chars,
        )
    truncated = normalized[: max_chars - len(TRUNCATION_MARKER)].rstrip() + TRUNCATION_MARKER
    return EvidenceText(
        text=truncated,
        truncated=True,
        original_chars=len(normalized),
        max_chars=max_chars,
    )


def _is_article_level(chunk: RetrievedChunk) -> bool:
    return (
        _same(chunk.level, "article")
        or _same(chunk.chunk_kind, "article")
        or (chunk.clause_number is None and chunk.point_label is None)
    )


def _texts_equivalent(first: str, second: str) -> bool:
    return _normalize_whitespace(first).casefold() == _normalize_whitespace(second).casefold()


def _normalize_whitespace(text: str | None) -> str:
    if text is None:
        return ""
    return " ".join(text.split())


def _parent_dedup_key(chunk: RetrievedChunk) -> str:
    if chunk.parent_text_hash:
        return f"hash:{chunk.parent_text_hash}"
    return "|".join(
        [
            chunk.law_id or "",
            chunk.article_number or "",
            _normalize_whitespace(chunk.parent_text),
        ]
    )


def _safety_allows(
    safety_level: EvidenceSafetyLevel,
    minimum: EvidenceSafetyLevel,
) -> bool:
    order = {
        EvidenceSafetyLevel.UNSAFE: 0,
        EvidenceSafetyLevel.CAUTION: 1,
        EvidenceSafetyLevel.SAFE: 2,
    }
    return order[safety_level] >= order[minimum]


def _issue(
    *,
    code: str,
    message: str,
    severity: EvidenceIssueSeverity,
    rank: int | None = None,
    chunk_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> EvidenceSafetyIssue:
    return EvidenceSafetyIssue(
        code=code,
        message=message,
        severity=severity,
        rank=rank,
        chunk_id=chunk_id,
        details=details or {},
    )


def _same(value: str | None, expected: str) -> bool:
    return value is not None and value.strip().casefold() == expected.casefold()
