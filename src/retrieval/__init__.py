"""Phase 9 retrieval domain components."""

from __future__ import annotations

from src.retrieval.dense_retriever import DenseRetriever, DenseRetrieverError
from src.retrieval.evaluation import (
    DenseRetrievalEvaluationReport,
    ExpectedTarget,
    ManualRetrievalQuery,
    PerQueryEvaluationResult,
    evaluate_dense_retrieval,
    load_manual_retrieval_queries,
)
from src.retrieval.evidence import (
    CitationScope,
    ContextAssemblyConfig,
    EvidenceBundle,
    EvidenceCitation,
    EvidencePacket,
    EvidenceSafetyIssue,
    EvidenceSafetyLevel,
    EvidenceText,
    ParentContextPolicy,
    build_evidence_bundle,
    build_evidence_packet,
)
from src.retrieval.models import RetrievalFilters, RetrievalQuery, RetrievalResult, RetrievedChunk
from src.retrieval.selection import (
    AnswerabilityDecision,
    EvidenceRejectionReason,
    EvidenceSelectionConfig,
    EvidenceSelectionResult,
    FallbackReason,
    FallbackReasonCode,
    RejectedEvidence,
    SelectedEvidence,
    SelectionWarning,
    select_evidence_for_answer,
)

__all__ = [
    "AnswerabilityDecision",
    "CitationScope",
    "ContextAssemblyConfig",
    "DenseRetrievalEvaluationReport",
    "DenseRetriever",
    "DenseRetrieverError",
    "EvidenceBundle",
    "EvidenceCitation",
    "EvidencePacket",
    "EvidenceRejectionReason",
    "EvidenceSafetyIssue",
    "EvidenceSafetyLevel",
    "EvidenceSelectionConfig",
    "EvidenceSelectionResult",
    "EvidenceText",
    "ExpectedTarget",
    "FallbackReason",
    "FallbackReasonCode",
    "ManualRetrievalQuery",
    "ParentContextPolicy",
    "PerQueryEvaluationResult",
    "RejectedEvidence",
    "RetrievedChunk",
    "RetrievalFilters",
    "RetrievalQuery",
    "RetrievalResult",
    "SelectedEvidence",
    "SelectionWarning",
    "build_evidence_bundle",
    "build_evidence_packet",
    "evaluate_dense_retrieval",
    "load_manual_retrieval_queries",
    "select_evidence_for_answer",
]
