"""Runtime workflow wiring for the Legal QA API service."""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from src.retrieval.coverage_aware import CoverageAwareFusionConfig
from src.retrieval.generation import FALLBACK_ANSWER_VI, RagAnswerResult, RagGenerationConfig
from src.retrieval.llm_client import LLMClientProtocol, LLMRequest, LLMResponse
from src.retrieval.models import RetrievalResult
from src.retrieval.rag_pipeline import RagRetrieverProtocol, run_naive_rag
from src.retrieval.selection import AnswerabilityDecision, EvidenceSelectionConfig
from src.services.legal_qa_api_service import (
    FakeLegalQAWorkflow,
    LegalQAService,
    LegalQATimingLogger,
    LegalQAWorkflow,
    LegalQAWorkflowCitation,
    LegalQAWorkflowDecision,
    LegalQAWorkflowEvidence,
    LegalQAWorkflowMetadata,
    LegalQAWorkflowRequest,
    LegalQAWorkflowResult,
)

DEFAULT_CHUNKS_PATH = Path("data/processed/legal_chunks.jsonl")
DEFAULT_RETRIEVAL_CONFIG_PATH = Path("configs/retrieval/retrieval.yml")
DEFAULT_LLM_CONFIG_PATH = Path("configs/llm/openrouter.yml")
DEFAULT_FINAL_TOP_K = 10
DEFAULT_PROVIDER = "openrouter"
DEFAULT_RETRIEVAL_STRATEGY = "coverage_aware_quota"
CAUTION_ANSWER_PREFIX = (
    "Lưu ý: bằng chứng truy xuất có liên quan nhưng còn yếu hoặc cần thận trọng; "
    "câu trả lời dưới đây chỉ dựa trên các căn cứ được trích dẫn."
)


class LegalQAServiceMode(StrEnum):
    """Runtime mode for the Legal QA API service."""

    FAKE = "fake"
    REAL = "real"


@dataclass(frozen=True)
class LegalQARuntimeSettings:
    """Runtime settings used by the Legal QA API dependency factory.

    The defaults are safe for local development: fake mode does not call Qdrant,
    OpenRouter, embedding models, rerankers, or evaluation workflows.
    """

    service_mode: LegalQAServiceMode = LegalQAServiceMode.FAKE
    retrieval_config_path: Path = DEFAULT_RETRIEVAL_CONFIG_PATH
    chunks_path: Path = DEFAULT_CHUNKS_PATH
    llm_config_path: Path = DEFAULT_LLM_CONFIG_PATH
    collection_name: str | None = None
    qdrant_url: str | None = None
    qdrant_api_key: str | None = field(default=None, repr=False)
    device: str | None = None
    model: str | None = None

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> LegalQARuntimeSettings:
        """Build runtime settings from environment variables.

        Args:
            environ: Optional environment mapping for tests.

        Returns:
            Settings with fake mode as the default.
        """
        env = os.environ if environ is None else environ
        return cls(
            service_mode=_service_mode(env.get("LEGAL_QA_SERVICE_MODE")),
            retrieval_config_path=Path(
                env.get("LEGAL_QA_RETRIEVAL_CONFIG", str(DEFAULT_RETRIEVAL_CONFIG_PATH))
            ),
            chunks_path=Path(env.get("LEGAL_QA_CHUNKS_PATH", str(DEFAULT_CHUNKS_PATH))),
            llm_config_path=Path(env.get("LEGAL_QA_LLM_CONFIG", str(DEFAULT_LLM_CONFIG_PATH))),
            collection_name=_non_blank(
                env.get("LEGAL_QA_COLLECTION_NAME") or env.get("QDRANT_COLLECTION")
            ),
            qdrant_url=_non_blank(env.get("LEGAL_QA_QDRANT_URL") or env.get("QDRANT_URL")),
            qdrant_api_key=_non_blank(
                env.get("LEGAL_QA_QDRANT_API_KEY") or env.get("QDRANT_API_KEY")
            ),
            device=_non_blank(env.get("LEGAL_QA_DEVICE")),
            model=_non_blank(env.get("LEGAL_QA_MODEL") or env.get("OPENROUTER_MODEL")),
        )


class RealLegalQAWorkflow:
    """Adapter from the API workflow protocol to the evaluated RAG workflow.

    The adapter owns no infrastructure construction. Callers inject a retriever
    and LLM client, allowing unit tests to use fakes while production wiring can
    provide the coverage-aware retriever and OpenRouter client.
    """

    def __init__(
        self,
        *,
        retriever: RagRetrieverProtocol,
        llm_client: LLMClientProtocol,
        collection_name: str,
        final_top_k: int = DEFAULT_FINAL_TOP_K,
        generation_config: RagGenerationConfig | None = None,
        selection_config: EvidenceSelectionConfig | None = None,
        runner: Callable[..., Awaitable[RagAnswerResult]] = run_naive_rag,
    ) -> None:
        """Initialize the real workflow adapter with injected dependencies."""
        self._retriever = retriever
        self._llm_client = llm_client
        self._collection_name = collection_name
        self._final_top_k = final_top_k
        self._generation_config = generation_config or RagGenerationConfig(
            fail_on_invalid_citation=True
        )
        self._selection_config = selection_config or EvidenceSelectionConfig()
        self._runner = runner

    def run(self, request: LegalQAWorkflowRequest) -> LegalQAWorkflowResult:
        """Run RAG with an enriched retrieval query and original answer question.

        Conversation context may override only the query received by the
        retriever. The RAG runner and generation prompt still receive the
        original current question, and only retrieved legal chunks can become
        selected evidence or citations.
        """
        started_at = time.perf_counter()
        retrieval_question = (
            request.context.retrieval_question if request.context is not None else request.question
        )
        rag_result = _run_async(
            self._runner(
                query=request.question,
                retriever=_RetrievalQuestionOverride(
                    retriever=self._retriever,
                    retrieval_question=retrieval_question,
                    request_id=request.request_id,
                    timing_logger=request.timing_logger,
                    timing_started_at=request.timing_started_at,
                ),
                llm_client=_TimedLLMClient(
                    llm_client=self._llm_client,
                    request_id=request.request_id,
                    timing_logger=request.timing_logger,
                    timing_started_at=request.timing_started_at,
                ),
                collection_name=self._collection_name,
                top_k=self._final_top_k,
                generation_config=self._generation_config,
                selection_config=self._selection_config,
                expected_targets=None,
            )
        )
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        return map_rag_answer_to_workflow_result(
            rag_result,
            fallback_model=self._generation_config.model,
            latency_ms=latency_ms,
        )


class _RetrievalQuestionOverride:
    """Use a prepared query only at the retriever boundary."""

    def __init__(
        self,
        *,
        retriever: RagRetrieverProtocol,
        retrieval_question: str,
        request_id: str,
        timing_logger: LegalQATimingLogger | None,
        timing_started_at: float | None,
    ) -> None:
        self._retriever = retriever
        self._retrieval_question = retrieval_question
        self._request_id = request_id
        self._timing_logger = timing_logger
        self._timing_started_at = timing_started_at

    async def retrieve(
        self,
        *,
        query: str,
        top_k: int | None = None,
        collection_name: str | None = None,
    ) -> RetrievalResult:
        _emit_workflow_timing(
            timing_logger=self._timing_logger,
            stage="embedding_model_initialization_or_loading",
            request_id=self._request_id,
            stage_started_at=None,
            timing_started_at=self._timing_started_at,
        )
        _emit_workflow_timing(
            timing_logger=self._timing_logger,
            stage="query_embedding",
            request_id=self._request_id,
            stage_started_at=None,
            timing_started_at=self._timing_started_at,
        )
        stage_started_at = time.perf_counter()
        try:
            result = await self._retriever.retrieve(
                query=self._retrieval_question,
                top_k=top_k,
                collection_name=collection_name,
            )
        except Exception as exc:
            _emit_workflow_timing(
                timing_logger=self._timing_logger,
                stage="qdrant_retrieval",
                request_id=self._request_id,
                stage_started_at=stage_started_at,
                timing_started_at=self._timing_started_at,
                exception_class=type(exc).__name__,
            )
            raise
        _emit_workflow_timing(
            timing_logger=self._timing_logger,
            stage="qdrant_retrieval",
            request_id=self._request_id,
            stage_started_at=stage_started_at,
            timing_started_at=self._timing_started_at,
        )
        return result


class _TimedLLMClient:
    """Emit sanitized timing around the provider generation boundary."""

    def __init__(
        self,
        *,
        llm_client: LLMClientProtocol,
        request_id: str,
        timing_logger: LegalQATimingLogger | None,
        timing_started_at: float | None,
    ) -> None:
        self._llm_client = llm_client
        self._request_id = request_id
        self._timing_logger = timing_logger
        self._timing_started_at = timing_started_at

    async def generate(self, request: LLMRequest) -> LLMResponse:
        _emit_workflow_timing(
            timing_logger=self._timing_logger,
            stage="llm_generation_provider_call",
            request_id=self._request_id,
            stage_started_at=None,
            timing_started_at=self._timing_started_at,
        )
        stage_started_at = time.perf_counter()
        try:
            response = await self._llm_client.generate(request)
        except Exception as exc:
            _emit_workflow_timing(
                timing_logger=self._timing_logger,
                stage="llm_generation_provider_call",
                request_id=self._request_id,
                stage_started_at=stage_started_at,
                timing_started_at=self._timing_started_at,
                exception_class=type(exc).__name__,
            )
            raise
        _emit_workflow_timing(
            timing_logger=self._timing_logger,
            stage="llm_generation_provider_call",
            request_id=self._request_id,
            stage_started_at=stage_started_at,
            timing_started_at=self._timing_started_at,
        )
        return response


def _emit_workflow_timing(
    *,
    timing_logger: LegalQATimingLogger | None,
    stage: str,
    request_id: str,
    stage_started_at: float | None,
    timing_started_at: float | None,
    exception_class: str | None = None,
) -> None:
    if timing_logger is None or timing_started_at is None:
        return
    now = time.perf_counter()
    elapsed_ms = int((now - stage_started_at) * 1000) if stage_started_at is not None else 0
    total_elapsed_ms = int((now - timing_started_at) * 1000)
    timing_logger(stage, request_id, elapsed_ms, total_elapsed_ms, exception_class)


def build_legal_qa_service(
    *,
    settings: LegalQARuntimeSettings | None = None,
    real_workflow_builder: Callable[[LegalQARuntimeSettings], LegalQAWorkflow] | None = None,
) -> LegalQAService:
    """Build the API service for the configured runtime mode.

    Args:
        settings: Optional explicit settings. Environment variables are used when
            omitted.
        real_workflow_builder: Optional real-workflow builder for tests or app
            bootstrap customization.

    Returns:
        Legal QA API service backed by either the fake or real workflow.
    """
    runtime_settings = settings or LegalQARuntimeSettings.from_env()
    if runtime_settings.service_mode == LegalQAServiceMode.FAKE:
        return LegalQAService(workflow=FakeLegalQAWorkflow())
    builder = real_workflow_builder or build_real_legal_qa_workflow
    return LegalQAService(workflow=builder(runtime_settings))


def build_real_legal_qa_workflow(settings: LegalQARuntimeSettings) -> LegalQAWorkflow:
    """Construct the real evaluated workflow from runtime settings.

    This function is intentionally called only when real mode is selected. It
    constructs read-only retrieval and provider clients but does not execute a
    query, call OpenRouter, run embedding inference, mutate Qdrant, or write
    evaluation artifacts at import time.
    """
    from src.indexing.embedding_model import BgeM3EmbeddingModel
    from src.indexing.qdrant_collection import build_qdrant_client
    from src.retrieval.coverage_aware import CoverageAwareQuotaRetriever
    from src.retrieval.dense_retriever import DenseRetriever
    from src.retrieval.llm_client import OpenRouterLLMClient
    from src.retrieval.openrouter_config import load_project_dotenv, resolve_openrouter_settings
    from src.retrieval.sparse_retriever import SparseBM25Retriever
    from src.retrieval.workflows.common import load_retrieval_config

    load_project_dotenv()
    retrieval_config = load_retrieval_config(settings.retrieval_config_path)
    fusion_config = _coverage_aware_config()
    collection_name = settings.collection_name or retrieval_config.qdrant.collection_name
    qdrant_url = settings.qdrant_url or retrieval_config.qdrant.url
    device = settings.device or retrieval_config.embedding.device

    qdrant_client = build_qdrant_client(
        url=qdrant_url,
        timeout_seconds=retrieval_config.qdrant.timeout_seconds,
        api_key=settings.qdrant_api_key,
    )
    embedding_model = BgeM3EmbeddingModel(
        model_name=retrieval_config.embedding.model_name,
        model_revision=retrieval_config.embedding.model_revision,
        device=device,
        normalize_embeddings=retrieval_config.embedding.normalize_embeddings,
        max_length=retrieval_config.embedding.max_length,
        dense_vector_name=retrieval_config.dense_retrieval.vector_name,
    )
    dense_retriever = DenseRetriever(
        qdrant_client=qdrant_client,
        embedding_model=embedding_model,
        collection_name=collection_name,
        dense_vector_name=retrieval_config.dense_retrieval.vector_name,
        expected_vector_dim=retrieval_config.dense_retrieval.expected_vector_dim,
        default_top_k=fusion_config.dense_candidate_k,
        embedding_batch_size=retrieval_config.embedding.batch_size,
    )
    sparse_retriever = SparseBM25Retriever.from_jsonl(
        settings.chunks_path,
        default_top_k=fusion_config.sparse_candidate_k,
    )
    coverage_retriever = CoverageAwareQuotaRetriever(
        dense_retriever=dense_retriever,
        sparse_retriever=sparse_retriever,
        config=fusion_config,
        collection_name=collection_name,
        vector_name=retrieval_config.dense_retrieval.vector_name,
    )
    provider_settings = resolve_openrouter_settings(
        cli_model=settings.model,
        config_path=settings.llm_config_path,
    )
    llm_client = OpenRouterLLMClient(
        base_url=provider_settings.base_url,
        default_model=provider_settings.model,
    )
    generation_config = RagGenerationConfig(
        provider=DEFAULT_PROVIDER,
        model=provider_settings.model,
        temperature=0.0,
        max_tokens=1024,
        timeout_s=30.0,
        include_auxiliary_context=True,
        fail_on_invalid_citation=True,
    )
    selection_config = EvidenceSelectionConfig()
    return RealLegalQAWorkflow(
        retriever=coverage_retriever,
        llm_client=llm_client,
        collection_name=collection_name,
        final_top_k=fusion_config.final_top_k,
        generation_config=generation_config,
        selection_config=selection_config,
    )


def map_rag_answer_to_workflow_result(
    result: RagAnswerResult,
    *,
    fallback_model: str | None,
    latency_ms: int,
) -> LegalQAWorkflowResult:
    """Map the existing RAG result model into the API workflow result model."""
    metadata = LegalQAWorkflowMetadata(
        retrieval_strategy=DEFAULT_RETRIEVAL_STRATEGY,
        model=result.model or fallback_model,
        reranking_used=False,
        latency_ms=latency_ms,
    )
    warnings = [
        *result.fallback_reasons,
        *result.selection_warnings,
        *[issue.code for issue in result.citation_issues],
        *result.errors,
    ]
    answer_decisions = {
        AnswerabilityDecision.ANSWER_ALLOWED,
        AnswerabilityDecision.ANSWER_WITH_CAUTION_ALLOWED,
    }
    if result.decision not in answer_decisions:
        return LegalQAWorkflowResult(
            decision=LegalQAWorkflowDecision.FALLBACK,
            answer=result.answer,
            warnings=[*result.fallback_reasons, *warnings],
            metadata=metadata,
        )

    missing = _missing_answer_metadata(result)
    if missing:
        return LegalQAWorkflowResult(
            decision=LegalQAWorkflowDecision.FALLBACK,
            answer=FALLBACK_ANSWER_VI,
            warnings=[*warnings, *missing],
            metadata=metadata,
        )

    return LegalQAWorkflowResult(
        decision=(
            LegalQAWorkflowDecision.ANSWERED_WITH_CAUTION
            if result.decision == AnswerabilityDecision.ANSWER_WITH_CAUTION_ALLOWED
            else LegalQAWorkflowDecision.ANSWERED
        ),
        answer=_answer_with_optional_caution(result),
        citations=[
            LegalQAWorkflowCitation(
                evidence_id=citation.evidence_id,
                chunk_id=citation.chunk_id or "",
                law_id=citation.law_id or "",
                law_name=citation.law_title or "",
                citation=citation.citation or "",
                source_url=citation.source_url or "",
                hierarchy_path=_hierarchy_path(
                    article_number=citation.article_number,
                    clause_number=citation.clause_number,
                    point_label=citation.point_label,
                ),
            )
            for citation in result.citations
        ],
        evidence=[
            LegalQAWorkflowEvidence(
                evidence_id=evidence.evidence_id,
                chunk_id=evidence.chunk_id or "",
                law_id=evidence.law_id or "",
                law_name=evidence.law_title or "",
                citation=evidence.citation or "",
                text=evidence.safe_citable_text or "",
                source_url=evidence.source_url or "",
                score=evidence.score,
            )
            for evidence in result.used_evidence
        ],
        warnings=warnings,
        metadata=metadata,
    )


def _coverage_aware_config() -> CoverageAwareFusionConfig:
    return CoverageAwareFusionConfig(
        config_id="selected_coverage_aware_quota",
        mode="quota",
        dense_candidate_k=50,
        sparse_candidate_k=50,
        final_top_k=DEFAULT_FINAL_TOP_K,
        rrf_k=60,
        dense_weight=1.0,
        sparse_weight=1.5,
        fused_best=5,
        sparse_quota=4,
        dense_quota=1,
    )


def _missing_answer_metadata(result: RagAnswerResult) -> list[str]:
    if not result.citations:
        return ["missing_citations"]
    missing: list[str] = []
    for citation in result.citations:
        if not citation.chunk_id:
            missing.append("missing_citation_chunk_id")
        if not citation.law_id:
            missing.append("missing_citation_law_id")
        if not citation.citation:
            missing.append("missing_citation_label")
        if not citation.source_url:
            missing.append("missing_citation_source_url")
    for evidence in result.used_evidence:
        if not evidence.safe_citable_text:
            missing.append("missing_evidence_text")
        if not evidence.source_url:
            missing.append("missing_evidence_source_url")
    return list(dict.fromkeys(missing))


def _answer_with_optional_caution(result: RagAnswerResult) -> str:
    if result.decision != AnswerabilityDecision.ANSWER_WITH_CAUTION_ALLOWED:
        return result.answer
    if result.answer.startswith(CAUTION_ANSWER_PREFIX):
        return result.answer
    return f"{CAUTION_ANSWER_PREFIX}\n\n{result.answer}"


def _hierarchy_path(
    *,
    article_number: str | None,
    clause_number: str | None,
    point_label: str | None,
) -> str:
    parts: list[str] = []
    if article_number:
        parts.append(f"Điều {article_number}")
    if clause_number:
        parts.append(f"Khoản {clause_number}")
    if point_label:
        parts.append(f"Điểm {point_label}")
    return " > ".join(parts)


def _run_async(awaitable: Awaitable[RagAnswerResult]) -> RagAnswerResult:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    if hasattr(awaitable, "close"):
        awaitable.close()
    raise RuntimeError(
        "real legal QA workflow must be called from a worker thread or async adapter"
    )


def _service_mode(raw_value: str | None) -> LegalQAServiceMode:
    value = _non_blank(raw_value)
    if value is None:
        return LegalQAServiceMode.FAKE
    try:
        return LegalQAServiceMode(value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in LegalQAServiceMode)
        raise ValueError(f"LEGAL_QA_SERVICE_MODE must be one of: {allowed}") from exc


def _non_blank(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
