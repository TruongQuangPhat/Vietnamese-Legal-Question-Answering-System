"""Deterministic query-document reranking utilities."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Protocol

from src.retrieval.models import RetrievedChunk


class RerankerError(RuntimeError):
    """Raised when reranker loading or scoring cannot complete safely."""


class RerankerProtocol(Protocol):
    """Score query-document pairs without using benchmark gold annotations."""

    @property
    def model_name(self) -> str:
        """Return the stable reranker model identifier."""
        ...

    def score(self, query: str, candidates: Sequence[RetrievedChunk]) -> list[float]:
        """Return one finite score per candidate in input order."""
        ...


class FlagEmbeddingReranker:
    """Local-only FlagEmbedding cross-encoder reranker.

    The model source must already exist locally. Resolving a Hugging Face model
    identifier uses ``local_files_only=True`` so benchmark execution cannot
    silently download model files.
    """

    def __init__(
        self,
        *,
        model_name: str,
        model_path: Path,
        device: str = "cpu",
        batch_size: int = 16,
        max_length: int = 512,
        factory: Callable[..., Any] | None = None,
    ) -> None:
        """Initialize a local cross-encoder model.

        Args:
            model_name: Stable model identifier recorded in manifests.
            model_path: Existing local model directory.
            device: FlagEmbedding inference device.
            batch_size: Pair-scoring batch size.
            max_length: Maximum query-document token length.
            factory: Optional injected FlagEmbedding-compatible factory.

        Raises:
            RerankerError: If the dependency or local model cannot be loaded.
        """
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if max_length <= 0:
            raise ValueError("max_length must be positive")
        if not model_path.exists():
            raise RerankerError(f"local reranker model path does not exist: {model_path}")

        reranker_factory = factory or _load_flag_reranker_factory()
        try:
            self._model = reranker_factory(
                str(model_path),
                use_fp16=device != "cpu",
                devices=device,
                batch_size=batch_size,
                max_length=max_length,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            raise RerankerError(f"failed to load local reranker model: {exc}") from exc
        self._model_name = model_name
        self._batch_size = batch_size

    @property
    def model_name(self) -> str:
        """Return the stable reranker model identifier."""
        return self._model_name

    def score(self, query: str, candidates: Sequence[RetrievedChunk]) -> list[float]:
        """Score query-document pairs using direct child chunk text.

        Parent text is intentionally excluded to keep the reranker focused on
        directly citable child evidence.
        """
        normalized_query = query.strip()
        if not normalized_query:
            raise RerankerError("reranker query must not be blank")
        if not candidates:
            return []
        pairs = [(normalized_query, candidate.text or "") for candidate in candidates]
        try:
            raw_scores = self._model.compute_score(pairs, batch_size=self._batch_size)
        except (OSError, RuntimeError, ValueError) as exc:
            raise RerankerError(f"reranker scoring failed: {exc}") from exc
        if hasattr(raw_scores, "tolist"):
            raw_scores = raw_scores.tolist()
        if isinstance(raw_scores, (int, float)):
            raw_scores = [raw_scores]
        scores = [float(score) for score in raw_scores]
        _validate_scores(scores, expected_count=len(candidates))
        return scores


def resolve_local_model_path(model_name_or_path: str) -> Path:
    """Resolve a local path without downloading a model.

    Args:
        model_name_or_path: Existing directory or Hugging Face model ID.

    Returns:
        Resolved local model snapshot path.

    Raises:
        RerankerError: If the model is absent from the local cache.
    """
    direct_path = Path(model_name_or_path).expanduser()
    if direct_path.exists():
        return direct_path.resolve()
    try:
        from huggingface_hub import snapshot_download

        cached_path = snapshot_download(repo_id=model_name_or_path, local_files_only=True)
    except (ImportError, OSError, ValueError) as exc:
        raise RerankerError(
            f"reranker model is not available locally: {model_name_or_path}. "
            "Download it explicitly before running the real-model ablation."
        ) from exc
    return Path(cached_path).resolve()


def deduplicate_candidates(candidates: Sequence[RetrievedChunk]) -> list[RetrievedChunk]:
    """Keep the first ranked occurrence of each traceable chunk ID."""
    deduplicated: list[RetrievedChunk] = []
    seen: set[str] = set()
    for candidate in candidates:
        chunk_id = candidate.chunk_id
        if chunk_id is None or chunk_id in seen:
            continue
        seen.add(chunk_id)
        deduplicated.append(candidate)
    return deduplicated


def min_max_normalize(scores: Sequence[float | None]) -> list[float]:
    """Normalize finite scores per query while handling missing/equal values."""
    finite_scores = [
        float(score) for score in scores if score is not None and math.isfinite(float(score))
    ]
    if not finite_scores:
        return [0.0] * len(scores)
    minimum = min(finite_scores)
    maximum = max(finite_scores)
    if math.isclose(minimum, maximum):
        return [
            1.0 if score is not None and math.isfinite(float(score)) else 0.0 for score in scores
        ]
    scale = maximum - minimum
    return [
        (float(score) - minimum) / scale
        if score is not None and math.isfinite(float(score))
        else 0.0
        for score in scores
    ]


def rerank_candidates(
    *,
    candidates: Sequence[RetrievedChunk],
    reranker_scores: Sequence[float],
    final_top_k: int,
    reranker_weight: float,
    g3_weight: float,
    preserve_source_quota: bool = False,
    sparse_quota: int = 4,
    dense_quota: int = 1,
    model_name: str,
) -> list[RetrievedChunk]:
    """Combine reranker and G3 scores, then select a deterministic final rank.

    Ranking uses only retrieval candidates, retrieval metadata, and reranker
    scores. Benchmark qrels and evidence-group annotations are never read.
    """
    if final_top_k <= 0:
        raise ValueError("final_top_k must be positive")
    if reranker_weight < 0 or g3_weight < 0:
        raise ValueError("score weights must be non-negative")
    if reranker_weight == 0 and g3_weight == 0:
        raise ValueError("at least one score weight must be positive")
    if sparse_quota < 0 or dense_quota < 0:
        raise ValueError("source quotas must be non-negative")

    unique = deduplicate_candidates(candidates)
    if len(reranker_scores) != len(candidates):
        raise RerankerError(
            f"reranker score count {len(reranker_scores)} does not match "
            f"candidate count {len(candidates)}"
        )
    score_by_id: dict[str, float] = {}
    for candidate, score in zip(candidates, reranker_scores, strict=True):
        if candidate.chunk_id is not None:
            score_by_id.setdefault(candidate.chunk_id, float(score))
    raw_reranker_scores = [score_by_id[candidate.chunk_id] for candidate in unique]
    _validate_scores(raw_reranker_scores, expected_count=len(unique))
    g3_scores = [_g3_score(candidate) for candidate in unique]
    normalized_reranker = min_max_normalize(raw_reranker_scores)
    normalized_g3 = min_max_normalize(g3_scores)

    ranked: list[RetrievedChunk] = []
    for candidate, raw_score, normalized_score, g3_score, normalized_base in zip(
        unique,
        raw_reranker_scores,
        normalized_reranker,
        g3_scores,
        normalized_g3,
        strict=True,
    ):
        final_score = (
            raw_score
            if g3_weight == 0
            else reranker_weight * normalized_score + g3_weight * normalized_base
        )
        metadata = dict(candidate.metadata)
        metadata["reranking"] = {
            "reranker_model": model_name,
            "reranker_score": raw_score,
            "normalized_reranker_score": normalized_score,
            "g3_score": g3_score,
            "normalized_g3_score": normalized_base,
            "final_score": final_score,
            "reranker_weight": reranker_weight,
            "g3_weight": g3_weight,
        }
        ranked.append(
            candidate.model_copy(
                update={"score": final_score, "metadata": metadata},
                deep=True,
            )
        )
    ranked.sort(key=_reranking_sort_key)
    selected = (
        _select_with_source_quotas(
            ranked,
            final_top_k=final_top_k,
            sparse_quota=sparse_quota,
            dense_quota=dense_quota,
        )
        if preserve_source_quota
        else ranked[:final_top_k]
    )
    selected.sort(key=_reranking_sort_key)
    return [
        candidate.model_copy(update={"rank": rank}, deep=True)
        for rank, candidate in enumerate(selected, start=1)
    ]


def _select_with_source_quotas(
    ranked: Sequence[RetrievedChunk],
    *,
    final_top_k: int,
    sparse_quota: int,
    dense_quota: int,
) -> list[RetrievedChunk]:
    selected: list[RetrievedChunk] = []
    seen: set[str] = set()

    def append_matching(source: str, minimum: int) -> None:
        current = sum(1 for item in selected if _source_rank(item, source) is not None)
        for candidate in ranked:
            if current >= minimum or len(selected) >= final_top_k:
                return
            chunk_id = candidate.chunk_id
            if chunk_id is None or chunk_id in seen or _source_rank(candidate, source) is None:
                continue
            selected.append(candidate)
            seen.add(chunk_id)
            current += 1

    append_matching("sparse", sparse_quota)
    append_matching("dense", dense_quota)
    for candidate in ranked:
        if len(selected) >= final_top_k:
            break
        chunk_id = candidate.chunk_id
        if chunk_id is None or chunk_id in seen:
            continue
        selected.append(candidate)
        seen.add(chunk_id)
    return selected


def _reranking_sort_key(candidate: RetrievedChunk) -> tuple[float, float, float, float, float, str]:
    reranking = candidate.metadata.get("reranking")
    if not isinstance(reranking, dict):
        raise RerankerError("candidate is missing reranking metadata")
    return (
        -float(reranking["final_score"]),
        -float(reranking["reranker_score"]),
        -float(reranking["g3_score"]),
        _source_rank(candidate, "dense") or math.inf,
        _source_rank(candidate, "sparse") or math.inf,
        candidate.chunk_id or "",
    )


def _g3_score(candidate: RetrievedChunk) -> float:
    fusion = candidate.metadata.get("fusion")
    if isinstance(fusion, dict) and fusion.get("fused_score") is not None:
        return float(fusion["fused_score"])
    return float(candidate.score)


def _source_rank(candidate: RetrievedChunk, source: str) -> int | None:
    fusion = candidate.metadata.get("fusion")
    if not isinstance(fusion, dict):
        return None
    rank = fusion.get(f"{source}_rank")
    return int(rank) if rank is not None else None


def _validate_scores(scores: Sequence[float], *, expected_count: int) -> None:
    if len(scores) != expected_count:
        raise RerankerError(
            f"reranker returned {len(scores)} scores for {expected_count} candidates"
        )
    if any(not math.isfinite(score) for score in scores):
        raise RerankerError("reranker returned a non-finite score")


def _load_flag_reranker_factory() -> Callable[..., Any]:
    try:
        from FlagEmbedding import FlagReranker
    except ImportError as exc:
        raise RerankerError(
            "FlagEmbedding reranker dependency is unavailable; run with --extra embedding"
        ) from exc
    return FlagReranker
