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

__all__ = [
    "CitationScope",
    "ContextAssemblyConfig",
    "DenseRetrievalEvaluationReport",
    "DenseRetriever",
    "DenseRetrieverError",
    "EvidenceBundle",
    "EvidenceCitation",
    "EvidencePacket",
    "EvidenceSafetyIssue",
    "EvidenceSafetyLevel",
    "EvidenceText",
    "ExpectedTarget",
    "ManualRetrievalQuery",
    "ParentContextPolicy",
    "PerQueryEvaluationResult",
    "RetrievedChunk",
    "RetrievalFilters",
    "RetrievalQuery",
    "RetrievalResult",
    "build_evidence_bundle",
    "build_evidence_packet",
    "evaluate_dense_retrieval",
    "load_manual_retrieval_queries",
]
