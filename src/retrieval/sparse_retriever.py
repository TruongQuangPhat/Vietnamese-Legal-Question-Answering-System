"""Deterministic BM25 sparse retrieval over local legal chunk JSONL."""

from __future__ import annotations

import json
import math
import re
import time
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from src.retrieval.models import (
    DEFAULT_COLLECTION_NAME,
    DEFAULT_TOP_K,
    RetrievalFilters,
    RetrievalIssue,
    RetrievalIssueSeverity,
    RetrievalQuery,
    RetrievalResult,
    RetrievedChunk,
)

TOKEN_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)
DEFAULT_BM25_K1 = 1.5
DEFAULT_BM25_B = 0.75


class SparseRetrieverError(RuntimeError):
    """Raised when sparse retrieval cannot safely complete."""


@dataclass(frozen=True)
class SparseDocument:
    """One indexed legal chunk and its deterministic sparse-token payload."""

    index: int
    payload: dict[str, Any]
    tokens: tuple[str, ...]
    token_counts: Counter[str]
    length: int


def normalize_sparse_text(value: str) -> str:
    """Normalize Vietnamese legal text for deterministic sparse matching.

    Args:
        value: Input query or chunk text.

    Returns:
        NFC-normalized, case-folded text. Vietnamese diacritics are preserved.
    """
    return unicodedata.normalize("NFC", value).casefold()


def tokenize_sparse_text(value: str) -> list[str]:
    """Tokenize Vietnamese legal text with a small Unicode-aware tokenizer.

    The tokenizer intentionally avoids language-specific stemming or external
    segmentation dependencies. It preserves numbers and Vietnamese diacritics,
    which are important for legal article, clause, and point references.
    """
    return TOKEN_PATTERN.findall(normalize_sparse_text(value))


def expand_legal_query_tokens(tokens: list[str]) -> list[str]:
    """Add conservative Vietnamese legal synonym tokens for sparse retrieval.

    The expansion is phrase-triggered and domain-generic. It bridges common
    user wording such as "nghỉ việc" to legal terms used in the corpus without
    changing result counts, filters, or retrieval metadata.
    """
    normalized = " ".join(tokens)
    expansions: list[str] = []

    if _contains_phrase(normalized, "nghỉ việc"):
        expansions.extend(["chấm", "dứt", "hợp", "đồng", "lao", "động"])
    if _contains_phrase(normalized, "đơn phương") or _contains_phrase(
        normalized, "chấm dứt hợp đồng"
    ):
        expansions.extend(["đơn", "phương", "chấm", "dứt", "hợp", "đồng"])
    if _contains_phrase(normalized, "báo trước"):
        expansions.extend(["thời", "hạn", "báo", "trước"])
    if _contains_phrase(normalized, "không cần báo trước") or _contains_phrase(
        normalized, "không phải báo trước"
    ):
        expansions.extend(["không", "cần", "báo", "trước", "không", "phải", "báo", "trước"])
    if _contains_phrase(normalized, "trái pháp luật") or _contains_phrase(
        normalized, "bị coi là trái"
    ):
        expansions.extend(["trái", "pháp", "luật"])

    if not expansions:
        return tokens
    return [*tokens, *expansions]


class SparseBM25Retriever:
    """Rank local legal chunks with deterministic Okapi BM25 scoring.

    Args:
        documents: Pre-tokenized legal documents.
        source_path: JSONL path used to build the sparse index.
        k1: BM25 term-frequency saturation parameter.
        b: BM25 length-normalization parameter.
        default_top_k: Default number of candidates returned.

    Retrieval assumptions:
        This retriever uses lexical matching over local chunk text and selected
        citation metadata only. It does not call Qdrant, LLMs, rerankers, or
        time-aware legal validity filters.
    """

    def __init__(
        self,
        *,
        documents: list[SparseDocument],
        source_path: Path,
        k1: float = DEFAULT_BM25_K1,
        b: float = DEFAULT_BM25_B,
        default_top_k: int = DEFAULT_TOP_K,
    ) -> None:
        if not documents:
            raise SparseRetrieverError("documents must not be empty")
        if k1 <= 0:
            raise SparseRetrieverError("k1 must be positive")
        if not 0 <= b <= 1:
            raise SparseRetrieverError("b must be between 0 and 1")
        if default_top_k <= 0:
            raise SparseRetrieverError("default_top_k must be positive")

        self.documents = documents
        self.source_path = source_path
        self.k1 = k1
        self.b = b
        self.default_top_k = default_top_k
        self.document_count = len(documents)
        self.average_document_length = (
            sum(document.length for document in documents) / self.document_count
        )
        self._postings = _build_postings(documents)
        self._idf = {
            term: math.log(
                1.0 + (self.document_count - len(postings) + 0.5) / (len(postings) + 0.5)
            )
            for term, postings in self._postings.items()
        }

    @classmethod
    def from_jsonl(
        cls,
        path: Path | str,
        *,
        k1: float = DEFAULT_BM25_K1,
        b: float = DEFAULT_BM25_B,
        default_top_k: int = DEFAULT_TOP_K,
    ) -> SparseBM25Retriever:
        """Build a BM25 index from a processed legal chunk JSONL file.

        Args:
            path: UTF-8 JSONL file containing processed legal chunks.
            k1: BM25 term-frequency saturation parameter.
            b: BM25 length-normalization parameter.
            default_top_k: Default number of candidates returned.

        Returns:
            Ready-to-query sparse BM25 retriever.

        Raises:
            SparseRetrieverError: If the file cannot be read or contains no
                indexable chunks.
        """
        source_path = Path(path)
        documents: list[SparseDocument] = []
        try:
            with source_path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        payload = json.loads(stripped)
                    except json.JSONDecodeError as exc:
                        raise SparseRetrieverError(
                            f"invalid JSON at {source_path}:{line_number}: {exc.msg}"
                        ) from exc
                    if not isinstance(payload, dict):
                        raise SparseRetrieverError(
                            f"record must be a JSON object at {source_path}:{line_number}"
                        )
                    tokens = tuple(tokenize_sparse_text(_indexable_text(payload)))
                    if not tokens:
                        continue
                    documents.append(
                        SparseDocument(
                            index=len(documents),
                            payload=payload,
                            tokens=tokens,
                            token_counts=Counter(tokens),
                            length=len(tokens),
                        )
                    )
        except OSError as exc:
            raise SparseRetrieverError(
                f"failed to read sparse corpus {source_path}: {exc}"
            ) from exc
        return cls(
            documents=documents,
            source_path=source_path,
            k1=k1,
            b=b,
            default_top_k=default_top_k,
        )

    async def retrieve(
        self,
        query: RetrievalQuery | str,
        *,
        top_k: int | None = None,
        collection_name: str | None = None,
        filters: RetrievalFilters | None = None,
    ) -> RetrievalResult:
        """Run one sparse retrieval request.

        Args:
            query: Query text or a prevalidated retrieval query.
            top_k: Optional top-k override for string queries.
            collection_name: Optional logical collection label.
            filters: Unsupported for the sparse BM25 baseline.

        Returns:
            Typed retrieval result with ranked legal chunks.

        Raises:
            SparseRetrieverError: If query validation or result mapping fails.
        """
        retrieval_query = self._coerce_query(
            query,
            top_k=top_k,
            collection_name=collection_name,
            filters=filters,
        )
        if retrieval_query.filters.has_conditions():
            raise SparseRetrieverError("sparse BM25 baseline does not support filters")

        started = time.perf_counter()
        query_tokens = expand_legal_query_tokens(tokenize_sparse_text(retrieval_query.query))
        if not query_tokens:
            return RetrievalResult(
                query=retrieval_query.query,
                collection_name=retrieval_query.collection_name,
                vector_name="sparse_bm25",
                top_k=retrieval_query.top_k,
                elapsed_ms=(time.perf_counter() - started) * 1000,
                query_vector_dimension=0,
                filters=retrieval_query.filters,
                results=[],
                issues=[],
            )

        scored = self._score(query_tokens)
        top_documents = sorted(
            scored.items(),
            key=lambda item: (
                -item[1],
                self.documents[item[0]].payload.get("chunk_id", ""),
                item[0],
            ),
        )[: retrieval_query.top_k]
        chunks = [
            _payload_to_retrieved_chunk(
                self.documents[document_index].payload,
                rank=rank,
                score=score,
            )
            for rank, (document_index, score) in enumerate(top_documents, start=1)
        ]
        issues = [issue for chunk in chunks for issue in chunk.issues]
        return RetrievalResult(
            query=retrieval_query.query,
            collection_name=retrieval_query.collection_name,
            vector_name="sparse_bm25",
            top_k=retrieval_query.top_k,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            query_vector_dimension=0,
            filters=retrieval_query.filters,
            results=chunks,
            issues=issues,
        )

    def _score(self, query_tokens: Iterable[str]) -> dict[int, float]:
        scores: dict[int, float] = defaultdict(float)
        for term, query_frequency in Counter(query_tokens).items():
            postings = self._postings.get(term)
            if not postings:
                continue
            idf = self._idf[term]
            for document_index, term_frequency in postings:
                document = self.documents[document_index]
                denominator = term_frequency + self.k1 * (
                    1.0 - self.b + self.b * document.length / max(self.average_document_length, 1.0)
                )
                scores[document_index] += (
                    idf * (term_frequency * (self.k1 + 1.0) / denominator) * float(query_frequency)
                )
        return dict(scores)

    def _coerce_query(
        self,
        query: RetrievalQuery | str,
        *,
        top_k: int | None,
        collection_name: str | None,
        filters: RetrievalFilters | None,
    ) -> RetrievalQuery:
        if isinstance(query, RetrievalQuery):
            if top_k is not None or collection_name is not None or filters is not None:
                raise SparseRetrieverError(
                    "top_k, collection_name, and filters overrides require a string query"
                )
            return query
        try:
            return RetrievalQuery(
                query=query,
                top_k=top_k or self.default_top_k,
                collection_name=collection_name or DEFAULT_COLLECTION_NAME,
                filters=filters or RetrievalFilters(),
            )
        except ValidationError as exc:
            raise SparseRetrieverError(f"invalid sparse retrieval query: {exc}") from exc


def _build_postings(documents: list[SparseDocument]) -> dict[str, list[tuple[int, int]]]:
    postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for document in documents:
        for term, frequency in document.token_counts.items():
            postings[term].append((document.index, frequency))
    return dict(postings)


def _contains_phrase(normalized_tokens: str, phrase: str) -> bool:
    return f" {normalize_sparse_text(phrase)} " in f" {normalized_tokens} "


def _indexable_text(payload: Mapping[str, Any]) -> str:
    parts = [
        payload.get("law_id"),
        payload.get("law_name"),
        payload.get("citation"),
        payload.get("hierarchy_path"),
        payload.get("article_title"),
        _local_parent_context(payload),
        payload.get("text"),
    ]
    return "\n".join(part for part in parts if isinstance(part, str))


def _local_parent_context(payload: Mapping[str, Any]) -> str | None:
    text = payload.get("text")
    parent_text = payload.get("parent_text")
    if not isinstance(text, str) or not isinstance(parent_text, str):
        return None
    normalized_text = " ".join(text.split())
    normalized_parent = " ".join(parent_text.split())
    if not normalized_text or not normalized_parent:
        return None
    index = normalized_parent.find(normalized_text)
    if index < 0:
        return None
    return normalized_parent[max(0, index - 300) : index]


def _payload_to_retrieved_chunk(
    payload: Mapping[str, Any], *, rank: int, score: float
) -> RetrievedChunk:
    issues: list[RetrievalIssue] = []
    chunk_id = _optional_string(payload.get("chunk_id"))
    for field_name in ("chunk_id", "law_id", "citation", "text"):
        value = payload.get(field_name)
        if not isinstance(value, str) or not value.strip():
            issues.append(
                RetrievalIssue(
                    code="critical_payload_field_missing",
                    severity=RetrievalIssueSeverity.WARNING,
                    message=f"critical payload field {field_name!r} is missing or invalid",
                    rank=rank,
                    chunk_id=chunk_id,
                    details={"field_name": field_name},
                )
            )
    return RetrievedChunk(
        rank=rank,
        score=score,
        point_id=chunk_id,
        chunk_id=chunk_id,
        law_id=_optional_string(payload.get("law_id")),
        law_name=_optional_string(payload.get("law_name")),
        level=_optional_string(payload.get("level")),
        chunk_kind=_optional_string(payload.get("chunk_kind")),
        article_number=_optional_string(payload.get("article_number")),
        article_title=_optional_string(payload.get("article_title")),
        clause_number=_optional_string(payload.get("clause_number")),
        point_label=_optional_string(payload.get("point_label")),
        citation=_optional_string(payload.get("citation")),
        hierarchy_path=_optional_string(payload.get("hierarchy_path")),
        source_node_id=_optional_string(payload.get("source_node_id")),
        parent_article_node_id=_optional_string(payload.get("parent_article_node_id")),
        parent_chunk_id=_optional_string(payload.get("parent_chunk_id")),
        text=_optional_string(payload.get("text")),
        parent_text=_optional_string(payload.get("parent_text")),
        text_hash=_optional_string(payload.get("text_hash")),
        parent_text_hash=_optional_string(payload.get("parent_text_hash")),
        source_url=_optional_string(payload.get("source_url")),
        source_domain=_optional_string(payload.get("source_domain")),
        source_type=_optional_string(payload.get("source_type")),
        source_file=_optional_string(payload.get("source_file")),
        metadata=dict(payload.get("metadata"))
        if isinstance(payload.get("metadata"), Mapping)
        else {},
        warnings=list(payload.get("warnings")) if isinstance(payload.get("warnings"), list) else [],
        is_empty_or_repealed=_optional_bool(
            _metadata_value(payload, "is_empty_or_repealed"),
        ),
        is_source_unit_repealed=_optional_bool(
            _metadata_value(payload, "is_source_unit_repealed"),
        ),
        payload_schema_version=_optional_string(payload.get("schema_version")),
        effective_date=_optional_string(payload.get("effective_date")),
        expiry_date=_optional_string(payload.get("expiry_date")),
        status=_optional_string(payload.get("status")),
        domain_tags=_string_list(payload.get("domain_tags")),
        issues=issues,
    )


def _metadata_value(payload: Mapping[str, Any], key: str) -> Any:
    metadata = payload.get("metadata")
    if isinstance(metadata, Mapping):
        return metadata.get(key)
    return None


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value)


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]
