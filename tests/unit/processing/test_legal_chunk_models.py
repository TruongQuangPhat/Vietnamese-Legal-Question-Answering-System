"""Tests for Phase 6 parent-child legal chunking schemas."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.processing.legal_chunk_models import (
    ChunkingIssue,
    ChunkingIssueCode,
    ChunkingLevel,
    ChunkingMetadata,
    ChunkingReport,
    ChunkingStatus,
    ChunkingSummary,
    ChunkValidationSummary,
    LegalChunk,
)

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "legal_chunking"


def _metadata() -> LegalChunk:
    """Create a minimal valid LegalChunk for use in test helpers."""
    text = "Khoản 1. Nội dung điều chỉnh.\n"
    parent_text = "Điều 1. Phạm vi điều chỉnh\nKhoản 1. Nội dung điều chỉnh.\n"
    chunk = LegalChunk(
        schema_version="1.0",
        chunker_version="v0.1.0",
        chunk_id="TEST_LAW__root__article_1__clause_1__chunk",
        law_id="TEST_LAW",
        law_name="Luật Kiểm thử",
        source_url="https://thuvienphapluat.vn/test.aspx",
        source_domain="thuvienphapluat.vn",
        source_type="html",
        source_file="data/interim/TEST_LAW/hierarchy.json",
        level=ChunkingLevel.CLAUSE,
        chunk_kind="clause_level",
        source_node_id="TEST_LAW__root__article_1__clause_1",
        parent_article_node_id="TEST_LAW__root__article_1",
        parent_chunk_id="TEST_LAW__root__article_1__parent",
        article_number="1",
        article_title="Phạm vi điều chỉnh",
        clause_number="1",
        point_label=None,
        citation="Luật Kiểm thử, Khoản 1, Điều 1",
        hierarchy_path="Luật Kiểm thử / Điều 1 / Khoản 1",
        text=text,
        parent_text=parent_text,
        start_offset=38,
        end_offset=64,
        article_start_offset=14,
        article_end_offset=64,
        text_hash="",
        parent_text_hash="",
        metadata=ChunkingMetadata(),
        warnings=[],
    )
    return chunk.compute_hashes()


def _issue(**overrides: object) -> ChunkingIssue:
    """Create a minimal valid ChunkingIssue."""
    defaults: dict[str, object] = {
        "code": ChunkingIssueCode.TEXT_MISMATCH,
        "message": "Chunk text does not match source node text.",
        "law_id": "TEST_LAW",
        "chunk_id": "TEST_LAW__root__article_1__clause_1__chunk",
        "source_node_id": "TEST_LAW__root__article_1__clause_1",
        "start_offset": 38,
        "end_offset": 64,
        "context": {},
    }
    defaults.update(overrides)
    return ChunkingIssue(**defaults)


def _summary(**overrides: object) -> ChunkingSummary:
    """Create a minimal valid ChunkingSummary."""
    defaults: dict[str, object] = {
        "law_id": "TEST_LAW",
        "status": ChunkingStatus.SUCCESS,
        "input_path": "data/interim/TEST_LAW/hierarchy.json",
        "total_chunks": 1,
        "chunks_by_level": {"clause": 1},
        "article_level_chunks": 0,
        "clause_level_chunks": 1,
        "point_level_chunks": 0,
        "empty_or_repealed_chunks": 0,
        "long_parent_text_chunks": 0,
        "warning_count": 0,
        "error_count": 0,
    }
    defaults.update(overrides)
    return ChunkingSummary(**defaults)


def _report(**overrides: object) -> ChunkingReport:
    """Create a minimal valid ChunkingReport."""
    defaults: dict[str, object] = {
        "schema_version": "1.0",
        "chunker_version": "v0.1.0",
        "started_at": "2026-06-07T10:00:00Z",
        "finished_at": "2026-06-07T10:00:01Z",
        "duration_seconds": 1.0,
        "input_dir": "data/interim",
        "output_path": "data/processed/legal_chunks.jsonl",
        "total_laws": 1,
        "successful": 1,
        "success_with_warnings": 0,
        "failed": 0,
        "total_chunks": 1,
        "chunks_by_level": {"clause": 1},
        "chunks_by_law": {"TEST_LAW": 1},
        "empty_or_repealed_article_chunks": 0,
        "warnings": [],
        "errors": [],
        "validation_summary": ChunkValidationSummary(total_chunks_checked=1),
        "law_summaries": [_summary()],
    }
    defaults.update(overrides)
    return ChunkingReport(**defaults)


class TestChunkingLevelEnum:
    """ChunkingLevel enum accepts valid values and rejects invalid ones."""

    def test_article_level_accepted(self) -> None:
        assert ChunkingLevel.ARTICLE == "article"

    def test_clause_level_accepted(self) -> None:
        assert ChunkingLevel.CLAUSE == "clause"

    def test_point_level_accepted(self) -> None:
        assert ChunkingLevel.POINT == "point"

    def test_invalid_value_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LegalChunk(
                schema_version="1.0",
                chunker_version="v0.1.0",
                chunk_id="x",
                law_id="TEST",
                law_name="Test",
                source_url="https://example.com",
                source_domain="example.com",
                source_type="html",
                source_file="data/interim/TEST/hierarchy.json",
                level="section",  # invalid
                chunk_kind="article_level",
                source_node_id="TEST__root__article_1",
                parent_article_node_id="TEST__root__article_1",
                parent_chunk_id="TEST__root__article_1__parent",
                text="text",
                parent_text="text",
                start_offset=0,
                end_offset=4,
                article_start_offset=0,
                article_end_offset=4,
                text_hash="abc",
                parent_text_hash="def",
            )


class TestChunkingStatusEnum:
    """ChunkingStatus enum accepts expected per-law status values."""

    def test_status_values(self) -> None:
        assert ChunkingStatus.SUCCESS == "success"
        assert ChunkingStatus.SUCCESS_WITH_WARNINGS == "success_with_warnings"
        assert ChunkingStatus.FAILED == "failed"


class TestChunkingMetadata:
    """ChunkingMetadata model validation and defaults."""

    def test_default_metadata(self) -> None:
        meta = ChunkingMetadata()
        assert meta.is_empty_or_repealed is False
        assert meta.is_source_unit_repealed is False
        assert meta.source_warnings == []
        assert meta.caveat_references == []

    def test_empty_article_flag(self) -> None:
        meta = ChunkingMetadata(is_empty_or_repealed=True, is_source_unit_repealed=True)
        assert meta.is_empty_or_repealed is True
        assert meta.is_source_unit_repealed is True

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            ChunkingMetadata(unexpected_field="value")

    def test_serialization(self) -> None:
        meta = ChunkingMetadata(is_empty_or_repealed=True, source_warnings=["EMPTY_ARTICLE_NODE"])
        dumped = meta.model_dump(mode="json")
        assert dumped["is_empty_or_repealed"] is True
        assert dumped["source_warnings"] == ["EMPTY_ARTICLE_NODE"]


class TestLegalChunkModel:
    """LegalChunk model validation, constraints, and behavior."""

    def test_chunk_model_validation(self) -> None:
        """A fully populated LegalChunk validates and serializes."""
        chunk = _metadata()
        dumped = chunk.model_dump(mode="json")
        assert dumped["chunk_id"] == "TEST_LAW__root__article_1__clause_1__chunk"
        assert dumped["law_id"] == "TEST_LAW"
        assert dumped["level"] == "clause"
        assert dumped["citation"] == "Luật Kiểm thử, Khoản 1, Điều 1"
        assert dumped["metadata"] == {
            "is_empty_or_repealed": False,
            "is_source_unit_repealed": False,
            "source_warnings": [],
            "caveat_references": [],
        }

    def test_required_fields_enforced(self) -> None:
        """Missing required fields raise ValidationError."""
        with pytest.raises(ValidationError, match="chunk_id"):
            LegalChunk(
                schema_version="1.0",
                chunker_version="v0.1.0",
                # chunk_id missing
                law_id="TEST",
                law_name="Test",
                source_url="https://example.com",
                source_domain="example.com",
                source_type="html",
                source_file="data/interim/TEST/hierarchy.json",
                level=ChunkingLevel.ARTICLE,
                chunk_kind="article_level",
                source_node_id="TEST__root__article_1",
                parent_article_node_id="TEST__root__article_1",
                parent_chunk_id="TEST__root__article_1__parent",
                text="text",
                parent_text="text",
                start_offset=0,
                end_offset=4,
                article_start_offset=0,
                article_end_offset=4,
                text_hash="abc",
                parent_text_hash="def",
            )

    def test_extra_fields_forbidden(self) -> None:
        """Extra fields are rejected by ConfigDict(extra='forbid')."""
        with pytest.raises(ValidationError, match="extra"):
            LegalChunk(
                schema_version="1.0",
                chunker_version="v0.1.0",
                chunk_id="x",
                law_id="TEST",
                law_name="Test",
                source_url="https://example.com",
                source_domain="example.com",
                source_type="html",
                source_file="data/interim/TEST/hierarchy.json",
                level=ChunkingLevel.ARTICLE,
                chunk_kind="article_level",
                source_node_id="TEST__root__article_1",
                parent_article_node_id="TEST__root__article_1",
                parent_chunk_id="TEST__root__article_1__parent",
                text="text",
                parent_text="text",
                start_offset=0,
                end_offset=4,
                article_start_offset=0,
                article_end_offset=4,
                text_hash="abc",
                parent_text_hash="def",
                extra_field="not_allowed",
            )

    def test_offset_order_validated(self) -> None:
        """end_offset must be greater than start_offset."""
        with pytest.raises(ValidationError, match="end_offset"):
            LegalChunk(
                schema_version="1.0",
                chunker_version="v0.1.0",
                chunk_id="x",
                law_id="TEST",
                law_name="Test",
                source_url="https://example.com",
                source_domain="example.com",
                source_type="html",
                source_file="data/interim/TEST/hierarchy.json",
                level=ChunkingLevel.ARTICLE,
                chunk_kind="article_level",
                source_node_id="TEST__root__article_1",
                parent_article_node_id="TEST__root__article_1",
                parent_chunk_id="TEST__root__article_1__parent",
                text="text",
                parent_text="text",
                start_offset=10,
                end_offset=5,  # invalid: end < start
                article_start_offset=0,
                article_end_offset=15,
                text_hash="abc",
                parent_text_hash="def",
                citation="Test, Điều 1",
            )

    def test_article_offset_containment(self) -> None:
        """Chunk offsets must be within parent Article offsets."""
        with pytest.raises(ValidationError, match="start_offset"):
            LegalChunk(
                schema_version="1.0",
                chunker_version="v0.1.0",
                chunk_id="x",
                law_id="TEST",
                law_name="Test",
                source_url="https://example.com",
                source_domain="example.com",
                source_type="html",
                source_file="data/interim/TEST/hierarchy.json",
                level=ChunkingLevel.CLAUSE,
                chunk_kind="clause_level",
                source_node_id="TEST__root__article_1__clause_1",
                parent_article_node_id="TEST__root__article_1",
                parent_chunk_id="TEST__root__article_1__parent",
                text="text",
                parent_text="parent text",
                start_offset=5,
                end_offset=9,
                article_start_offset=10,  # invalid: start < article_start
                article_end_offset=20,
                text_hash="abc",
                parent_text_hash="def",
                citation="Test, Khoản 1, Điều 1",
            )

    def test_compute_hashes(self) -> None:
        """compute_hashes populates text_hash and parent_text_hash."""
        chunk = _metadata()
        assert chunk.text_hash == hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()
        assert (
            chunk.parent_text_hash
            == hashlib.sha256(chunk.parent_text.encode("utf-8")).hexdigest()
        )

    def test_metadata_dict_is_validated_to_typed_model(self) -> None:
        """Dict input is accepted but normalized to ChunkingMetadata."""
        payload = _metadata().model_dump(mode="json")
        payload["metadata"] = {"is_empty_or_repealed": True}

        validated = LegalChunk.model_validate(payload)
        assert isinstance(validated.metadata, ChunkingMetadata)
        assert validated.metadata.is_empty_or_repealed is True

    def test_invalid_metadata_rejected(self) -> None:
        """Unknown metadata keys are rejected at the chunk boundary."""
        payload = _metadata().model_dump(mode="json")
        payload["metadata"] = {"unknown": "value"}

        with pytest.raises(ValidationError, match="unknown"):
            LegalChunk.model_validate(payload)

    def test_hash_stable_across_calls(self) -> None:
        """compute_hashes produces the same hash for identical text."""
        chunk = _metadata()
        hash1 = chunk.text_hash
        hash2 = chunk.compute_hashes().text_hash
        assert hash1 == hash2

    def test_chunk_kind_strings(self) -> None:
        """Accepted chunk_kind values are valid."""
        for kind in ("article_level", "article_level_empty", "clause_level", "point_level"):
            chunk = _metadata().model_copy(update={"chunk_kind": kind})
            assert chunk.chunk_kind == kind

    def test_vietnamese_text_preserved(self) -> None:
        """Vietnamese characters survive serialization with ensure_ascii=False."""
        chunk = _metadata()
        dumped = json.dumps(chunk.model_dump(mode="json"), ensure_ascii=False)
        assert "Phạm" in dumped
        assert "Điều" in dumped


class TestChunkingIssue:
    """ChunkingIssue model validation and serialization."""

    def test_issue_serialization(self) -> None:
        issue = _issue(
            code=ChunkingIssueCode.OFFSET_MISMATCH,
            message="Offset mismatch detected.",
        )
        dumped = issue.model_dump(mode="json")
        assert dumped["code"] == "OFFSET_MISMATCH"
        assert dumped["law_id"] == "TEST_LAW"
        assert dumped["message"] == "Offset mismatch detected."

    def test_issue_without_optional_fields(self) -> None:
        issue = ChunkingIssue(
            code=ChunkingIssueCode.EMPTY_CHUNK_TEXT,
            message="Chunk text is empty.",
            law_id="TEST_LAW",
        )
        dumped = issue.model_dump(mode="json")
        assert dumped["chunk_id"] is None
        assert dumped["source_node_id"] is None
        assert dumped["start_offset"] is None
        assert dumped["end_offset"] is None
        assert dumped["context"] == {}

    def test_issue_context_roundtrip(self) -> None:
        issue = _issue(
            context={"expected": 10, "actual": 5, "node_id": "TEST__article_1"}
        )
        dumped = issue.model_dump(mode="json")
        assert dumped["context"]["expected"] == 10
        assert dumped["context"]["actual"] == 5

    def test_issue_offset_order_validated(self) -> None:
        with pytest.raises(ValidationError, match="end_offset"):
            _issue(start_offset=20, end_offset=10)

    def test_issue_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            _issue(bad_field="x")


class TestChunkingSummary:
    """ChunkingSummary defaults and aggregation."""

    def test_defaults_are_zero_or_empty(self) -> None:
        summary = ChunkingSummary(law_id="TEST_LAW")
        assert summary.status == ChunkingStatus.SUCCESS
        assert summary.input_path is None
        assert summary.total_chunks == 0
        assert summary.chunks_by_level == {}
        assert summary.article_level_chunks == 0
        assert summary.clause_level_chunks == 0
        assert summary.point_level_chunks == 0
        assert summary.empty_or_repealed_chunks == 0
        assert summary.long_parent_text_chunks == 0
        assert summary.warning_count == 0
        assert summary.error_count == 0

    def test_populated_summary(self) -> None:
        summary = _summary(
            total_chunks=5,
            chunks_by_level={"article": 1, "clause": 2, "point": 2},
            article_level_chunks=1,
            clause_level_chunks=2,
            point_level_chunks=2,
            empty_or_repealed_chunks=1,
            long_parent_text_chunks=2,
        )
        assert summary.total_chunks == 5
        assert summary.point_level_chunks == 2
        assert summary.empty_or_repealed_chunks == 1
        assert summary.long_parent_text_chunks == 2


class TestChunkValidationSummary:
    """ChunkValidationSummary validation and serialization."""

    def test_defaults_are_zero(self) -> None:
        summary = ChunkValidationSummary()
        assert summary.total_chunks_checked == 0
        assert summary.duplicate_chunk_ids == 0
        assert summary.report_count_mismatches == 0

    def test_populated_summary_serializes(self) -> None:
        summary = ChunkValidationSummary(
            total_chunks_checked=5,
            duplicate_chunk_ids=1,
            jsonl_lines_checked=5,
        )
        dumped = summary.model_dump(mode="json")
        assert dumped["total_chunks_checked"] == 5
        assert dumped["duplicate_chunk_ids"] == 1
        assert dumped["jsonl_lines_checked"] == 5

    def test_negative_counters_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate_chunk_ids"):
            ChunkValidationSummary(duplicate_chunk_ids=-1)


class TestChunkingReport:
    """ChunkingReport aggregation and serialization."""

    def test_report_aggregates_summaries(self) -> None:
        s1 = _summary(law_id="LAW_A", total_chunks=3, article_level_chunks=1, clause_level_chunks=2)
        s2 = _summary(law_id="LAW_B", total_chunks=2, clause_level_chunks=1, point_level_chunks=1)
        report = _report(
            total_laws=2,
            total_chunks=5,
            chunks_by_level={"article": 1, "clause": 3, "point": 1},
            chunks_by_law={"LAW_A": 3, "LAW_B": 2},
            law_summaries=[s1, s2],
        )
        assert report.total_chunks == 5
        assert report.total_laws == 2
        assert len(report.law_summaries) == 2
        assert report.law_summaries[0].law_id == "LAW_A"
        assert report.law_summaries[1].law_id == "LAW_B"

    def test_report_serialization(self) -> None:
        report = _report()
        dumped = report.model_dump(mode="json")
        assert dumped["schema_version"] == "1.0"
        assert dumped["total_laws"] == 1
        assert dumped["failed"] == 0

    def test_report_with_warnings_and_errors(self) -> None:
        issue = _issue()
        report = _report(
            warnings=[issue],
            errors=[_issue(code=ChunkingIssueCode.TREE_VALIDATION_FAILED)],
        )
        assert len(report.warnings) == 1
        assert len(report.errors) == 1

    def test_report_validation_summary(self) -> None:
        report = _report(
            validation_summary=ChunkValidationSummary(
                total_chunks_checked=5,
                duplicate_chunk_ids=0,
            )
        )
        assert report.validation_summary.total_chunks_checked == 5
        assert report.validation_summary.duplicate_chunk_ids == 0

    def test_report_duration_non_negative(self) -> None:
        with pytest.raises(ValidationError, match="duration_seconds"):
            _report(duration_seconds=-1.0)


class TestMutableDefaultsIndependence:
    """Ensure list and dict defaults do not leak across model instances."""

    def test_chunk_warnings_independent(self) -> None:
        c1 = LegalChunk(
            schema_version="1.0",
            chunker_version="v0.1.0",
            chunk_id="a",
            law_id="T",
            law_name="T",
            source_url="u",
            source_domain="d",
            source_type="t",
            source_file="f",
            level=ChunkingLevel.ARTICLE,
            chunk_kind="article_level",
            source_node_id="T__root__article_1",
            parent_article_node_id="T__root__article_1",
            parent_chunk_id="T__root__article_1__parent",
            text="text",
            parent_text="text",
            start_offset=0,
            end_offset=4,
            article_start_offset=0,
            article_end_offset=4,
            text_hash="abc",
            parent_text_hash="def",
            citation="T, Điều 1",
        )
        c2 = LegalChunk(
            schema_version="1.0",
            chunker_version="v0.1.0",
            chunk_id="b",
            law_id="T",
            law_name="T",
            source_url="u",
            source_domain="d",
            source_type="t",
            source_file="f",
            level=ChunkingLevel.ARTICLE,
            chunk_kind="article_level",
            source_node_id="T__root__article_1",
            parent_article_node_id="T__root__article_1",
            parent_chunk_id="T__root__article_1__parent",
            text="text",
            parent_text="text",
            start_offset=0,
            end_offset=4,
            article_start_offset=0,
            article_end_offset=4,
            text_hash="abc",
            parent_text_hash="def",
            citation="T, Điều 1",
        )
        c1.warnings.append(_issue())
        assert len(c2.warnings) == 0

    def test_issue_context_independent(self) -> None:
        i1 = _issue()
        i1.context["key"] = "value"
        i2 = _issue()
        assert "key" not in i2.context

    def test_summary_defaults_independent(self) -> None:
        s1 = ChunkingSummary(law_id="A")
        s2 = ChunkingSummary(law_id="B")
        s1.chunks_by_level["article"] = 1
        assert "article" not in s2.chunks_by_level
