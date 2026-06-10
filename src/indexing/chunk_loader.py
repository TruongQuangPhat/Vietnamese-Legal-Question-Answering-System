"""Read-only streaming loader for Phase 8 embedding inputs.

The loader validates each JSONL row against the canonical ``LegalChunk``
schema and maps it deterministically to an ``EmbeddingInput``. It does not
load embedding models, generate vectors, connect to Qdrant, or mutate input
files or chunk objects.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from pydantic import ValidationError

from src.indexing.indexing_models import EmbeddingInput, EmbeddingTextTemplate
from src.processing.legal_chunk_models import LegalChunk


class ChunkLoaderError(ValueError):
    """Failure while reading or mapping a processed legal chunk.

    Attributes:
        path: Input JSONL path, when the failure is file-related.
        line_number: One-based JSONL line number, when available.
        reason: Human-readable failure reason.
    """

    def __init__(
        self,
        reason: str,
        *,
        path: Path | None = None,
        line_number: int | None = None,
    ) -> None:
        self.path = path
        self.line_number = line_number
        self.reason = reason

        location = str(path) if path is not None else "<embedding-input>"
        if line_number is not None:
            location = f"{location}:{line_number}"
        super().__init__(f"{location}: {reason}")


def iter_legal_chunks(path: Path | str) -> Iterator[LegalChunk]:
    """Stream and validate legal chunks from a UTF-8 JSONL file.

    Args:
        path: Processed legal chunk JSONL path.

    Yields:
        Validated ``LegalChunk`` records in source order.

    Raises:
        ChunkLoaderError: If the file cannot be read, a line is invalid JSON,
            or a decoded row fails ``LegalChunk`` validation. Invalid records
            are never skipped.
    """
    input_path = Path(path)

    try:
        with input_path.open("r", encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ChunkLoaderError(
                        f"invalid JSON: {exc.msg}",
                        path=input_path,
                        line_number=line_number,
                    ) from exc

                try:
                    yield LegalChunk.model_validate(payload)
                except ValidationError as exc:
                    raise ChunkLoaderError(
                        f"invalid LegalChunk: {exc}",
                        path=input_path,
                        line_number=line_number,
                    ) from exc
    except ChunkLoaderError:
        raise
    except OSError as exc:
        raise ChunkLoaderError(
            f"unable to read input file: {exc}",
            path=input_path,
        ) from exc
    except UnicodeError as exc:
        raise ChunkLoaderError(
            f"input file is not valid UTF-8: {exc}",
            path=input_path,
        ) from exc


def build_embedding_input(
    chunk: LegalChunk,
    *,
    text_template: EmbeddingTextTemplate | str = EmbeddingTextTemplate.TEXT_ONLY,
) -> EmbeddingInput:
    """Map one legal chunk to a deterministic, immutable embedding input.

    Args:
        chunk: Validated source chunk. The chunk and its text fields are not
            modified.
        text_template: Deterministic template used to assemble embedding text.

    Returns:
        Typed embedding input preserving chunk traceability and warnings.

    Raises:
        ChunkLoaderError: If the template is unsupported or a required
            template field is blank.
    """
    template = _parse_text_template(text_template)
    text = _require_non_blank(chunk.text, field_name="text", chunk_id=chunk.chunk_id)

    if template == EmbeddingTextTemplate.TEXT_ONLY:
        embedding_text = text
    elif template == EmbeddingTextTemplate.CITATION_PLUS_TEXT:
        citation = _require_non_blank(
            chunk.citation,
            field_name="citation",
            chunk_id=chunk.chunk_id,
        )
        embedding_text = f"{citation}\n{text}"
    else:
        law_name = _require_non_blank(
            chunk.law_name,
            field_name="law_name",
            chunk_id=chunk.chunk_id,
        )
        citation = _require_non_blank(
            chunk.citation,
            field_name="citation",
            chunk_id=chunk.chunk_id,
        )
        embedding_text = f"{law_name}\n{citation}\n{text}"

    if not embedding_text.strip():
        raise ChunkLoaderError(f"blank embedding text for chunk {chunk.chunk_id!r}")

    try:
        return EmbeddingInput(
            chunk_id=chunk.chunk_id,
            law_id=chunk.law_id,
            chunk_kind=chunk.chunk_kind,
            level=chunk.level,
            embedding_text=embedding_text,
            text_hash=chunk.text_hash,
            parent_text_hash=chunk.parent_text_hash,
            citation=chunk.citation,
            hierarchy_path=chunk.hierarchy_path,
            metadata=chunk.metadata.model_copy(deep=True),
            warnings=[warning.model_copy(deep=True) for warning in chunk.warnings],
        )
    except ValidationError as exc:
        raise ChunkLoaderError(
            f"invalid EmbeddingInput for chunk {chunk.chunk_id!r}: {exc}"
        ) from exc


def iter_embedding_inputs(
    path: Path | str,
    *,
    text_template: EmbeddingTextTemplate | str = EmbeddingTextTemplate.TEXT_ONLY,
    law_id: str | None = None,
    limit: int | None = None,
) -> Iterator[EmbeddingInput]:
    """Stream deterministic embedding inputs from processed legal chunks.

    Args:
        path: Processed legal chunk JSONL path.
        text_template: Template used to assemble each embedding text.
        law_id: Optional exact law identifier filter.
        limit: Optional maximum number of matching inputs to yield. Zero
            yields no records.

    Yields:
        Embedding inputs in source order.

    Raises:
        ChunkLoaderError: If ``limit`` is negative, ``law_id`` is blank, the
            template is unsupported, or any source row cannot be loaded or
            mapped.
    """
    if limit is not None and limit < 0:
        raise ChunkLoaderError("limit must be greater than or equal to zero", path=Path(path))
    if law_id is not None and not law_id.strip():
        raise ChunkLoaderError("law_id filter must be null or non-blank", path=Path(path))

    template = _parse_text_template(text_template, path=Path(path))
    yielded = 0

    if limit == 0:
        return

    input_path = Path(path)
    for line_number, chunk in enumerate(iter_legal_chunks(input_path), start=1):
        if law_id is not None and chunk.law_id != law_id:
            continue

        try:
            yield build_embedding_input(chunk, text_template=template)
        except ChunkLoaderError as exc:
            raise ChunkLoaderError(
                exc.reason,
                path=input_path,
                line_number=line_number,
            ) from exc
        yielded += 1
        if limit is not None and yielded >= limit:
            return


def _parse_text_template(
    value: EmbeddingTextTemplate | str,
    *,
    path: Path | None = None,
) -> EmbeddingTextTemplate:
    """Return a supported text template or raise a loader-specific error."""
    try:
        return EmbeddingTextTemplate(value)
    except ValueError as exc:
        supported = ", ".join(template.value for template in EmbeddingTextTemplate)
        raise ChunkLoaderError(
            f"unsupported text template {value!r}; expected one of: {supported}",
            path=path,
        ) from exc


def _require_non_blank(value: str, *, field_name: str, chunk_id: str) -> str:
    """Return an original legal field unchanged after a non-blank check."""
    if not value.strip():
        raise ChunkLoaderError(f"blank {field_name} for chunk {chunk_id!r}")
    return value
