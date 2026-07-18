"""Coverage-aware hybrid retrieval components for runtime and evaluation use."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from src.retrieval.dense_retriever import DenseRetrieverError
from src.retrieval.fusion import (
    DiversitySelectionConfig,
    QuotaSelectionConfig,
    reciprocal_rank_fusion,
)
from src.retrieval.models import RetrievalIssue, RetrievalIssueSeverity, RetrievalResult
from src.retrieval.timing import emit_retrieval_timing, safe_exception_class

FusionMode = Literal["weighted_rrf", "quota", "diversity"]


class CoverageAwareRetrievalError(RuntimeError):
    """Raised when coverage-aware retrieval cannot safely complete."""


@dataclass(frozen=True)
class CoverageAwareFusionConfig:
    """One coverage-aware fusion configuration.

    The selected product runtime uses the fixed quota variant. Evaluation code
    also uses this model for controlled retrieval comparisons.
    """

    config_id: str
    mode: FusionMode
    dense_candidate_k: int = 50
    sparse_candidate_k: int = 50
    final_top_k: int = 10
    rrf_k: int = 60
    dense_weight: float = 1.0
    sparse_weight: float = 1.0
    fused_best: int | None = None
    sparse_quota: int | None = None
    dense_quota: int | None = None
    diversity_penalty: float | None = None
    prefer_distinct_clause_point: bool = False
    simplicity_rank: int = 0

    def quota_config(self) -> QuotaSelectionConfig | None:
        """Return quota selector settings when this variant uses quotas."""
        if self.mode != "quota":
            return None
        if self.fused_best is None or self.sparse_quota is None or self.dense_quota is None:
            raise ValueError(f"quota config {self.config_id} is incomplete")
        return QuotaSelectionConfig(
            fused_best=self.fused_best,
            sparse_quota=self.sparse_quota,
            dense_quota=self.dense_quota,
        )

    def diversity_config(self) -> DiversitySelectionConfig | None:
        """Return diversity selector settings when this variant uses diversity."""
        if self.mode != "diversity":
            return None
        if self.diversity_penalty is None:
            raise ValueError(f"diversity config {self.config_id} is incomplete")
        return DiversitySelectionConfig(
            penalty=self.diversity_penalty,
            prefer_distinct_clause_point=self.prefer_distinct_clause_point,
        )

    def model_dump(self) -> dict[str, Any]:
        """Return a JSON-compatible config dictionary."""
        return {
            "config_id": self.config_id,
            "mode": self.mode,
            "dense_candidate_k": self.dense_candidate_k,
            "sparse_candidate_k": self.sparse_candidate_k,
            "final_top_k": self.final_top_k,
            "rrf_k": self.rrf_k,
            "dense_weight": self.dense_weight,
            "sparse_weight": self.sparse_weight,
            "quota": {
                "fused_best": self.fused_best,
                "sparse_quota": self.sparse_quota,
                "dense_quota": self.dense_quota,
            }
            if self.mode == "quota"
            else None,
            "diversity": {
                "diversity_penalty": self.diversity_penalty,
                "prefer_distinct_clause_point": self.prefer_distinct_clause_point,
            }
            if self.mode == "diversity"
            else None,
            "simplicity_rank": self.simplicity_rank,
        }


class CandidateRetrieverProtocol(Protocol):
    """Minimal candidate retrieval interface required by hybrid fusion."""

    async def retrieve(self, query: str, *, top_k: int) -> RetrievalResult:
        """Retrieve ranked candidates for one query."""
        ...


class CoverageAwareQuotaRetriever:
    """Fuse read-only dense and sparse candidates with a fixed quota policy."""

    def __init__(
        self,
        *,
        dense_retriever: CandidateRetrieverProtocol,
        sparse_retriever: CandidateRetrieverProtocol,
        config: CoverageAwareFusionConfig,
        collection_name: str,
        vector_name: str,
        dense_fallback_enabled: bool = False,
        dense_fallback_mode: Literal["sparse"] = "sparse",
        dense_fallback_timeout_seconds: float = 10.0,
    ) -> None:
        """Initialize the fixed retrieval strategy.

        Args:
            dense_retriever: Read-only dense candidate retriever.
            sparse_retriever: Local BM25 candidate retriever.
            config: Frozen coverage-aware quota configuration.
            collection_name: Existing Qdrant collection name.
            vector_name: Existing dense vector name.

        Raises:
            CoverageAwareRetrievalError: If the configuration is not the
                approved coverage-aware quota strategy.
        """
        if config.mode != "quota" or config.config_id != "selected_coverage_aware_quota":
            raise CoverageAwareRetrievalError(
                "retrieval config must be selected_coverage_aware_quota"
            )
        self._dense_retriever = dense_retriever
        self._sparse_retriever = sparse_retriever
        self._config = config
        self._collection_name = collection_name
        self._vector_name = vector_name
        self._dense_fallback_enabled = dense_fallback_enabled
        self._dense_fallback_mode = dense_fallback_mode
        self._dense_fallback_timeout_seconds = dense_fallback_timeout_seconds

    async def retrieve(
        self,
        *,
        query: str,
        top_k: int | None = None,
        collection_name: str | None = None,
    ) -> RetrievalResult:
        """Retrieve, fuse, and return the fixed final candidate set."""
        requested_top_k = top_k or self._config.final_top_k
        if requested_top_k != self._config.final_top_k:
            raise CoverageAwareRetrievalError(
                f"top_k must remain fixed at {self._config.final_top_k}"
            )
        if collection_name is not None and collection_name != self._collection_name:
            raise CoverageAwareRetrievalError("collection override does not match config")

        started = time.perf_counter()
        dense_result: RetrievalResult | None = None
        dense_issue: RetrievalIssue | None = None
        try:
            dense_result = await self._dense_retriever.retrieve(
                query,
                top_k=self._config.dense_candidate_k,
            )
        except DenseRetrieverError as exc:
            if not self._dense_fallback_enabled:
                raise
            dense_issue = _dense_fallback_issue(exc)
            emit_retrieval_timing(
                stage="dense_retriever_failed",
                stage_started_at=started,
                exception_class=exc.cause_class or safe_exception_class(exc),
                fallback_used=True,
                top_k=self._config.dense_candidate_k,
            )
            return await self._fallback_sparse_result(
                query=query,
                started=started,
                dense_issue=dense_issue,
            )
        sparse_result = await self._sparse_retriever.retrieve(
            query,
            top_k=self._config.sparse_candidate_k,
        )
        fused = reciprocal_rank_fusion(
            dense_results=dense_result.results,
            sparse_results=sparse_result.results,
            final_top_k=self._config.final_top_k,
            rrf_k=self._config.rrf_k,
            dense_weight=self._config.dense_weight,
            sparse_weight=self._config.sparse_weight,
            quota_config=self._config.quota_config(),
        )
        return RetrievalResult(
            query=query,
            collection_name=self._collection_name,
            vector_name=self._vector_name,
            top_k=self._config.final_top_k,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            query_vector_dimension=dense_result.query_vector_dimension,
            results=fused,
            issues=[*dense_result.issues, *sparse_result.issues],
            metadata={
                "retrieval_mode": "hybrid",
                "dense_retrieval_used": True,
                "dense_retrieval_fallback_used": False,
                "fallback_used": False,
            },
        )

    async def _fallback_sparse_result(
        self,
        *,
        query: str,
        started: float,
        dense_issue: RetrievalIssue | None,
    ) -> RetrievalResult:
        if self._dense_fallback_mode != "sparse":
            raise CoverageAwareRetrievalError("unsupported dense retrieval fallback mode")
        fallback_started = time.perf_counter()
        emit_retrieval_timing(
            stage="dense_retrieval_fallback_started",
            timeout_seconds=self._dense_fallback_timeout_seconds,
            fallback_used=True,
            top_k=self._config.final_top_k,
        )
        try:
            bounded_sparse_result = await asyncio.wait_for(
                self._sparse_retriever.retrieve(query, top_k=self._config.final_top_k),
                timeout=self._dense_fallback_timeout_seconds,
            )
        except TimeoutError:
            emit_retrieval_timing(
                stage="dense_retrieval_fallback_timeout",
                stage_started_at=fallback_started,
                exception_class="TimeoutError",
                timeout_seconds=self._dense_fallback_timeout_seconds,
                fallback_used=True,
                top_k=self._config.final_top_k,
            )
            raise CoverageAwareRetrievalError("sparse fallback timed out") from None
        except Exception as exc:
            emit_retrieval_timing(
                stage="dense_retriever_failed",
                stage_started_at=fallback_started,
                exception_class=safe_exception_class(exc),
                timeout_seconds=self._dense_fallback_timeout_seconds,
                fallback_used=True,
                top_k=self._config.final_top_k,
            )
            raise CoverageAwareRetrievalError("sparse fallback failed") from exc
        emit_retrieval_timing(
            stage="dense_retriever_completed",
            stage_started_at=started,
            fallback_used=True,
            top_k=self._config.final_top_k,
        )
        issues = list(bounded_sparse_result.issues)
        if dense_issue is not None:
            issues.insert(0, dense_issue)
        return RetrievalResult(
            query=query,
            collection_name=self._collection_name,
            vector_name="sparse_bm25_fallback",
            top_k=self._config.final_top_k,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            query_vector_dimension=0,
            results=bounded_sparse_result.results[: self._config.final_top_k],
            issues=issues,
            metadata={
                "retrieval_mode": "hybrid",
                "dense_retrieval_used": False,
                "dense_retrieval_fallback_used": True,
                "fallback_used": True,
                "retriever_stage_failed": dense_issue.details.get("failure_stage")
                if dense_issue is not None
                else "dense_retriever_error",
            },
        )

    async def warmup_embedding(self) -> None:
        """Warm only the dense embedding dependency, without retrieval or LLM calls."""
        warmup = getattr(self._dense_retriever, "warmup_embedding", None)
        if warmup is None or not callable(warmup):
            return
        await warmup()


def _dense_fallback_issue(exc: DenseRetrieverError) -> RetrievalIssue:
    return RetrievalIssue(
        code=exc.warning_code,
        severity=RetrievalIssueSeverity.WARNING,
        message="dense retrieval failed and sparse fallback was attempted",
        details={
            "failure_stage": exc.failure_stage,
            "exception_class": exc.cause_class or type(exc).__name__,
            "fallback_used": True,
        },
    )


def coverage_aware_config_from_payload(payload: dict[str, Any]) -> CoverageAwareFusionConfig:
    """Build a typed coverage-aware config from a JSON-compatible payload."""
    quota = payload.get("quota") or {}
    diversity = payload.get("diversity") or {}
    return CoverageAwareFusionConfig(
        config_id=str(payload["config_id"]),
        mode=payload["mode"],
        dense_candidate_k=payload["dense_candidate_k"],
        sparse_candidate_k=payload["sparse_candidate_k"],
        final_top_k=payload["final_top_k"],
        rrf_k=payload["rrf_k"],
        dense_weight=payload["dense_weight"],
        sparse_weight=payload["sparse_weight"],
        fused_best=quota.get("fused_best"),
        sparse_quota=quota.get("sparse_quota"),
        dense_quota=quota.get("dense_quota"),
        diversity_penalty=diversity.get("diversity_penalty"),
        prefer_distinct_clause_point=bool(diversity.get("prefer_distinct_clause_point", False)),
        simplicity_rank=payload.get("simplicity_rank", 999),
    )
