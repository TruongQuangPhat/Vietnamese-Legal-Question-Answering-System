"""Fallback-aware Naive RAG pipeline for fallback-aware Naive RAG."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from src.retrieval.evaluation import ExpectedTarget
from src.retrieval.evidence import ContextAssemblyConfig, build_evidence_bundle
from src.retrieval.generation import (
    CitationIssueSeverity,
    RagAnswerResult,
    RagGenerationConfig,
    build_fallback_result,
    check_generated_citations,
    used_evidence_from_prompt,
)
from src.retrieval.llm_client import LLMClientError, LLMClientProtocol, LLMMessage, LLMRequest
from src.retrieval.models import RetrievalResult
from src.retrieval.prompting import build_naive_rag_prompt
from src.retrieval.selection import (
    AnswerabilityDecision,
    EvidenceSelectionConfig,
    select_evidence_for_answer,
)


class RagRetrieverProtocol(Protocol):
    """Minimal retrieval service interface required by the Naive RAG pipeline."""

    async def retrieve(
        self,
        *,
        query: str,
        top_k: int | None = None,
        collection_name: str | None = None,
    ) -> RetrievalResult:
        """Run one read-only retrieval query."""
        ...


async def run_naive_rag(
    *,
    query: str,
    retriever: RagRetrieverProtocol,
    llm_client: LLMClientProtocol,
    collection_name: str,
    top_k: int = 20,
    evidence_config: ContextAssemblyConfig | None = None,
    selection_config: EvidenceSelectionConfig | None = None,
    generation_config: RagGenerationConfig | None = None,
    expected_targets: Sequence[ExpectedTarget] | None = None,
) -> RagAnswerResult:
    """Run dense retrieval, evidence selection, and fallback-aware generation.

    Legal safety invariant:
        If evidence selection does not return ``answer_allowed``, this function
        returns deterministic fallback and does not call the LLM.
    """
    config = generation_config or RagGenerationConfig()
    retrieval_result = await retriever.retrieve(
        query=query,
        top_k=top_k,
        collection_name=collection_name,
    )
    retrieval_metadata = {
        "collection_name": retrieval_result.collection_name,
        "vector_name": retrieval_result.vector_name,
        "top_k": retrieval_result.top_k,
        "result_count": len(retrieval_result.results),
        "elapsed_ms": retrieval_result.elapsed_ms,
        "query_vector_dimension": retrieval_result.query_vector_dimension,
        "issue_count": len(retrieval_result.issues),
        "retrieval_issue_codes": list(
            dict.fromkeys(issue.code for issue in retrieval_result.issues)
        ),
    }
    evidence_bundle = build_evidence_bundle(retrieval_result, evidence_config)
    selection_result = select_evidence_for_answer(
        evidence_bundle,
        selection_config,
        expected_targets=expected_targets,
    )

    generation_allowed = {
        AnswerabilityDecision.ANSWER_ALLOWED,
        AnswerabilityDecision.ANSWER_WITH_CAUTION_ALLOWED,
    }
    if selection_result.decision not in generation_allowed:
        return build_fallback_result(
            query=query,
            decision=selection_result.decision,
            selection_result=selection_result,
            retrieval_metadata=retrieval_metadata,
            generation_config=config,
        )

    try:
        prompt = build_naive_rag_prompt(
            query=query,
            selection_result=selection_result,
            include_auxiliary_context=config.include_auxiliary_context,
        )
        llm_response = await llm_client.generate(
            LLMRequest(
                messages=[
                    LLMMessage(role="system", content=prompt.system_message),
                    LLMMessage(role="user", content=prompt.user_message),
                ],
                model=config.model,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                timeout_s=config.timeout_s,
                metadata={"pipeline": "naive_rag"},
            )
        )
    except (LLMClientError, ValueError) as exc:
        return build_fallback_result(
            query=query,
            decision=AnswerabilityDecision.FALLBACK_REQUIRED,
            selection_result=selection_result,
            retrieval_metadata=retrieval_metadata,
            generation_config=config,
            errors=[str(exc)],
        )

    citation_check = check_generated_citations(
        answer=llm_response.text,
        prompt_evidence=prompt.evidence,
    )
    invalid_citations = [
        issue for issue in citation_check.issues if issue.severity == CitationIssueSeverity.ERROR
    ]
    if invalid_citations and config.fail_on_invalid_citation:
        return build_fallback_result(
            query=query,
            decision=AnswerabilityDecision.FALLBACK_REQUIRED,
            selection_result=selection_result,
            retrieval_metadata=retrieval_metadata,
            generation_config=config,
            errors=[issue.message for issue in invalid_citations],
        )

    return RagAnswerResult(
        query=query,
        decision=selection_result.decision,
        answer=llm_response.text,
        citations=citation_check.valid_citations,
        used_evidence=used_evidence_from_prompt(prompt.evidence),
        fallback_reasons=[reason.code.value for reason in selection_result.fallback_reasons],
        selection_warnings=[warning.code.value for warning in selection_result.warnings],
        citation_issues=citation_check.issues,
        retrieval_metadata=retrieval_metadata,
        selection_metadata={
            "decision": selection_result.decision.value,
            "selected_count": selection_result.selected_count,
            "rejected_count": selection_result.rejected_count,
            "caution_selected_count": selection_result.caution_selected_count,
            "unsafe_rejected_count": selection_result.unsafe_rejected_count,
        },
        generation_metadata={
            "prompt_evidence_count": len(prompt.evidence),
            "llm_latency_ms": llm_response.latency_ms,
            "finish_reason": llm_response.finish_reason,
            "usage": llm_response.usage.model_dump(mode="json") if llm_response.usage else None,
        },
        llm_called=True,
        model=llm_response.model,
        provider=llm_response.provider,
        errors=[],
    )
