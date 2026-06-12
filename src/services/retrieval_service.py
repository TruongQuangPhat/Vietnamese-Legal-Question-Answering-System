"""Service orchestration for Phase 9A dense retrieval."""

from __future__ import annotations

from src.retrieval.dense_retriever import DenseRetriever
from src.retrieval.models import RetrievalFilters, RetrievalResult


class RetrievalService:
    """Coordinate a single dense retrieval use case.

    The service layer intentionally stays thin in Phase 9A: the domain
    retriever owns query embedding, Qdrant search, and payload mapping, while
    scripts own CLI parsing and dependency construction.
    """

    def __init__(self, *, retriever: DenseRetriever) -> None:
        self._retriever = retriever

    async def retrieve(
        self,
        *,
        query: str,
        top_k: int | None = None,
        collection_name: str | None = None,
        filters: RetrievalFilters | None = None,
    ) -> RetrievalResult:
        """Run one dense retrieval request.

        Args:
            query: Vietnamese legal query.
            top_k: Optional top-k override.
            collection_name: Optional collection override.
            filters: Optional safe payload filters.

        Returns:
            Typed dense retrieval result.
        """
        return await self._retriever.retrieve(
            query,
            top_k=top_k,
            collection_name=collection_name,
            filters=filters,
        )
