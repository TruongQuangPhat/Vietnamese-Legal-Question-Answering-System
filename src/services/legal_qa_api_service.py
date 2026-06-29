"""Deterministic legal QA API service stub."""

from __future__ import annotations

from time import perf_counter
from uuid import uuid4

from src.api.schemas import (
    CitationDTO,
    EvidenceDTO,
    LegalQADecision,
    LegalQARequest,
    LegalQAResponse,
    ResponseMetadataDTO,
)


class LegalQAService:
    """Stub service for the product API legal QA boundary.

    The service returns deterministic, citation-shaped data without calling Qdrant,
    OpenRouter, embedding models, rerankers, or evaluation workflows. It exists to
    stabilize the public API contract before the evaluated RAG workflow is wired in.
    """

    @staticmethod
    def create_request_id() -> str:
        """Create an opaque request identifier.

        Returns:
            Request identifier suitable for client correlation.
        """
        return str(uuid4())

    def answer(self, request: LegalQARequest) -> LegalQAResponse:
        """Return a deterministic legal QA response for API contract testing.

        Args:
            request: Validated legal QA request.

        Returns:
            Stub answer with one citation and optional evidence.
        """
        started_at = perf_counter()
        citation = CitationDTO(
            evidence_id="E1",
            chunk_id="stub-child-chunk-001",
            law_id="stub-law-001",
            law_name="Bộ luật Lao động",
            citation="Điều 35 Bộ luật Lao động",
            source_url="https://thuvienphapluat.vn/van-ban/Lao-dong-Tien-luong/",
            hierarchy_path="Điều 35",
        )
        evidence = EvidenceDTO(
            evidence_id=citation.evidence_id,
            chunk_id=citation.chunk_id,
            law_id=citation.law_id,
            law_name=citation.law_name,
            citation=citation.citation,
            text=(
                "Người lao động có quyền đơn phương chấm dứt hợp đồng lao động "
                "theo các trường hợp được pháp luật lao động quy định."
            ),
            source_url=citation.source_url,
            score=1.0,
        )
        latency_ms = int((perf_counter() - started_at) * 1000)
        return LegalQAResponse(
            request_id=self.create_request_id(),
            decision=LegalQADecision.ANSWERED,
            answer=(
                "Đây là phản hồi mẫu từ API stub. Khi tích hợp RAG thật, câu trả lời "
                "sẽ chỉ dựa trên bằng chứng pháp lý được chọn và có thể trích dẫn."
            ),
            citations=[citation],
            evidence=[evidence] if request.include_evidence else [],
            warnings=[],
            metadata=ResponseMetadataDTO(
                retrieval_strategy="coverage_aware_quota",
                model="stub",
                reranking_used=False,
                latency_ms=latency_ms,
            ),
        )
