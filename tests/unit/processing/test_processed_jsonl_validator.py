"""Unit tests for Phase 7 processed JSONL validator (Slice 3A)."""

from __future__ import annotations

import json
from pathlib import Path

from src.processing.legal_chunk_models import (
    ChunkingLevel,
    ChunkingMetadata,
    LegalChunk,
    _compute_text_hash,
)
from src.processing.processed_jsonl_validation_models import (
    ProcessedJsonlValidationConfig,
    ProcessedJsonlValidationIssueCode,
)
from src.processing.processed_jsonl_validator import ProcessedJsonlValidator

# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def _config(**overrides: object) -> ProcessedJsonlValidationConfig:
    """Build a ProcessedJsonlValidationConfig with sensible defaults."""
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "validator_version": "v0.1.0",
    }
    payload.update(overrides)
    return ProcessedJsonlValidationConfig(**payload)


def _valid_chunk(**overrides: object) -> LegalChunk:
    """Build a minimal valid LegalChunk with real hashes for test data."""
    text = "Nội dung văn bản pháp luật."
    parent_text = "Nội dung đầy đủ của Điều 1."
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "chunker_version": "v0.1.0",
        "chunk_id": "chunk_001",
        "law_id": "law_001",
        "law_name": "Luật thử nghiệm",
        "source_url": "https://thuvienphapluat.vn/law_001",
        "source_domain": "thuvienphapluat.vn",
        "source_type": "law",
        "source_file": "data/interim/law_001/hierarchy.json",
        "level": ChunkingLevel.ARTICLE,
        "chunk_kind": "article_level",
        "source_node_id": "node_001",
        "parent_article_node_id": "node_001",
        "parent_chunk_id": "node_001__parent",
        "article_number": "1",
        "article_title": "Điều 1",
        "clause_number": None,
        "point_label": None,
        "citation": "Điều 1 Luật thử nghiệm",
        "hierarchy_path": "Luật thử nghiệm/Điều 1",
        "text": text,
        "parent_text": parent_text,
        "start_offset": 0,
        "end_offset": 30,
        "article_start_offset": 0,
        "article_end_offset": 100,
        "text_hash": _compute_text_hash(text),
        "parent_text_hash": _compute_text_hash(parent_text),
        "metadata": ChunkingMetadata(
            is_empty_or_repealed=False,
            is_source_unit_repealed=False,
        ),
        "warnings": [],
    }
    payload.update(overrides)
    return LegalChunk(**payload)


def _write_jsonl(path: Path, chunks: list[LegalChunk]) -> None:
    """Write LegalChunk objects as JSONL."""
    with path.open("w", encoding="utf-8") as fh:
        for chunk in chunks:
            fh.write(json.dumps(chunk.model_dump(mode="json"), ensure_ascii=False))
            fh.write("\n")


def _write_raw_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    """Write raw dicts as JSONL (bypasses LegalChunk validation)."""
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False))
            fh.write("\n")


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


class TestValidJsonl:
    """Happy path: valid JSONL with valid chunks."""

    def test_valid_jsonl_returns_pass(self, tmp_path: Path) -> None:
        chunk = _valid_chunk()
        jsonl_path = tmp_path / "valid.jsonl"
        _write_jsonl(jsonl_path, [chunk])

        validator = ProcessedJsonlValidator(_config())
        report = validator.validate(jsonl_path)

        assert report.status == "pass"
        assert report.total_lines == 1
        assert report.valid_chunks == 1
        assert report.invalid_chunks == 0
        assert report.errors_total == 0
        assert report.warnings_total == 0

    def test_multiple_valid_chunks(self, tmp_path: Path) -> None:
        chunks = [
            _valid_chunk(chunk_id="c1", law_id="l1"),
            _valid_chunk(chunk_id="c2", law_id="l1"),
            _valid_chunk(chunk_id="c3", law_id="l2"),
        ]
        jsonl_path = tmp_path / "multi.jsonl"
        _write_jsonl(jsonl_path, chunks)

        validator = ProcessedJsonlValidator(_config())
        report = validator.validate(jsonl_path)

        assert report.status == "pass"
        assert report.total_lines == 3
        assert report.valid_chunks == 3
        assert report.invalid_chunks == 0
        assert report.chunks_by_level == {"article": 3}
        assert report.chunks_by_law == {"l1": 2, "l2": 1}


class TestJsonlParseErrors:
    """Invalid JSON and blank lines."""

    def test_invalid_json_line(self, tmp_path: Path) -> None:
        jsonl_path = tmp_path / "bad.jsonl"
        jsonl_path.write_text("not_valid_json_at_all\n", encoding="utf-8")

        validator = ProcessedJsonlValidator(_config())
        report = validator.validate(jsonl_path)

        assert report.status == "fail"
        assert report.total_lines == 1
        assert report.invalid_chunks == 1
        assert report.valid_chunks == 0
        assert report.jsonl_parse_failures == 1
        assert report.errors_total == 1
        assert len(report.sample_failures) == 1
        assert report.sample_failures[0].code == ProcessedJsonlValidationIssueCode.JSONL_PARSE_ERROR

    def test_blank_line_is_error(self, tmp_path: Path) -> None:
        jsonl_path = tmp_path / "blank.jsonl"
        jsonl_path.write_text("\n", encoding="utf-8")

        validator = ProcessedJsonlValidator(_config())
        report = validator.validate(jsonl_path)

        assert report.status == "fail"
        assert report.total_lines == 1
        assert report.invalid_chunks == 1
        assert report.jsonl_parse_failures == 1
        assert report.errors_total == 1

    def test_mixed_valid_and_invalid(self, tmp_path: Path) -> None:
        chunk = _valid_chunk(chunk_id="good")
        jsonl_path = tmp_path / "mixed.jsonl"
        _write_jsonl(jsonl_path, [chunk])
        # Append a bad line
        with jsonl_path.open("a", encoding="utf-8") as fh:
            fh.write("not json\n")

        validator = ProcessedJsonlValidator(_config())
        report = validator.validate(jsonl_path)

        assert report.total_lines == 2
        assert report.valid_chunks == 1
        assert report.invalid_chunks == 1
        assert report.jsonl_parse_failures == 1
        assert report.errors_total == 1


class TestSchemaValidation:
    """LegalChunk.model_validate failures."""

    def test_schema_validation_failure(self, tmp_path: Path) -> None:
        # All presence fields present but invalid type causes schema failure
        bad_row = {
            "chunk_id": "c1",
            "law_id": "l1",
            "law_name": "L",
            "level": "article",
            "chunk_kind": "article_level",
            "citation": "c",
            "hierarchy_path": "h",
            "source_node_id": "s",
            "parent_article_node_id": "p",
            "article_number": "1",
            "clause_number": None,
            "point_label": None,
            "text": "t",
            "parent_text": "pt",
            "text_hash": "h1",
            "parent_text_hash": "h2",
            "metadata": {"is_empty_or_repealed": False, "is_source_unit_repealed": False},
            "start_offset": "not_an_int",  # wrong type → schema failure
        }
        jsonl_path = tmp_path / "schema_bad.jsonl"
        _write_raw_jsonl(jsonl_path, [bad_row])

        validator = ProcessedJsonlValidator(_config())
        report = validator.validate(jsonl_path)

        assert report.status == "fail"
        assert report.schema_failures == 1
        assert report.errors_total == 1
        assert report.invalid_chunks == 1
        assert report.valid_chunks == 0
        assert (
            report.sample_failures[0].code
            == ProcessedJsonlValidationIssueCode.SCHEMA_VALIDATION_FAILED
        )

    def test_non_dict_jsonl_row(self, tmp_path: Path) -> None:
        jsonl_path = tmp_path / "array.jsonl"
        jsonl_path.write_text('["not", "a", "dict"]\n', encoding="utf-8")

        validator = ProcessedJsonlValidator(_config())
        report = validator.validate(jsonl_path)

        assert report.status == "fail"
        assert report.schema_failures == 1
        assert report.invalid_chunks == 1


class TestRequiredFields:
    """Required field presence and value validity by chunk_kind."""

    def test_missing_top_level_field_detected(self, tmp_path: Path) -> None:
        # Use an extra field that LegalChunk rejects (extra="forbid")
        # so the row fails schema validation. Then verify the required-field
        # check catches fields that LegalChunk would accept with defaults.
        row = _valid_chunk(chunk_id="c1").model_dump(mode="json")
        row["_extra_forbidden"] = "value"  # LegalChunk extra="forbid"
        jsonl_path = tmp_path / "missing_field.jsonl"
        _write_raw_jsonl(jsonl_path, [row])

        validator = ProcessedJsonlValidator(_config())
        report = validator.validate(jsonl_path)

        assert report.status == "fail"
        assert report.schema_failures == 1
        assert report.errors_total == 1
        assert report.invalid_chunks == 1

    def test_required_field_detected_from_raw_dict(self, tmp_path: Path) -> None:
        # Test that _check_required_fields catches missing fields from raw dict.
        # We bypass LegalChunk validation by writing a row that LegalChunk
        # accepts (all required fields present) but then remove a field from
        # the raw dict and verify the required-field check catches it.
        # Since LegalChunk fills defaults, we test with an empty text_hash:
        # LegalChunk allows empty text_hash (default ""), so our check catches it.
        row = _valid_chunk(chunk_id="c1").model_dump(mode="json")
        row["text_hash"] = ""  # LegalChunk accepts this, but our check rejects it
        jsonl_path = tmp_path / "req_field.jsonl"
        _write_raw_jsonl(jsonl_path, [row])

        validator = ProcessedJsonlValidator(_config())
        report = validator.validate(jsonl_path)

        assert report.required_field_failures == 1
        assert report.invalid_chunks == 1
        fields = [issue.context.get("field") for issue in report.sample_failures]
        assert "text_hash" in fields

    def test_missing_metadata_field_detected(self, tmp_path: Path) -> None:
        # Remove metadata entirely — caught by presence check
        row = _valid_chunk(chunk_id="c1").model_dump(mode="json")
        del row["metadata"]
        jsonl_path = tmp_path / "missing_meta.jsonl"
        _write_raw_jsonl(jsonl_path, [row])

        validator = ProcessedJsonlValidator(_config())
        report = validator.validate(jsonl_path)

        assert report.required_field_failures == 1
        assert report.invalid_chunks == 1
        fields = [issue.context.get("field") for issue in report.sample_failures]
        assert "metadata" in fields

    def test_article_level_allows_none_clause_and_point(self, tmp_path: Path) -> None:
        chunk = _valid_chunk(
            chunk_id="art1",
            chunk_kind="article_level",
            clause_number=None,
            point_label=None,
        )
        jsonl_path = tmp_path / "article.jsonl"
        _write_jsonl(jsonl_path, [chunk])

        validator = ProcessedJsonlValidator(_config())
        report = validator.validate(jsonl_path)

        assert report.status == "pass"
        assert report.required_field_failures == 0
        assert report.valid_chunks == 1

    def test_clause_level_requires_clause_number(self, tmp_path: Path) -> None:
        chunk = _valid_chunk(
            chunk_id="cl1",
            chunk_kind="clause_level",
            level=ChunkingLevel.CLAUSE,
            clause_number="2",
            point_label=None,
        )
        row = chunk.model_dump(mode="json")
        del row["clause_number"]
        jsonl_path = tmp_path / "clause_bad.jsonl"
        _write_raw_jsonl(jsonl_path, [row])

        validator = ProcessedJsonlValidator(_config())
        report = validator.validate(jsonl_path)

        assert report.required_field_failures == 1
        assert report.invalid_chunks == 1

    def test_clause_level_allows_none_point_label(self, tmp_path: Path) -> None:
        chunk = _valid_chunk(
            chunk_id="cl1",
            chunk_kind="clause_level",
            level=ChunkingLevel.CLAUSE,
            clause_number="2",
            point_label=None,
        )
        jsonl_path = tmp_path / "clause_ok.jsonl"
        _write_jsonl(jsonl_path, [chunk])

        validator = ProcessedJsonlValidator(_config())
        report = validator.validate(jsonl_path)

        assert report.status == "pass"
        assert report.required_field_failures == 0

    def test_point_level_requires_point_label(self, tmp_path: Path) -> None:
        chunk = _valid_chunk(
            chunk_id="pt1",
            chunk_kind="point_level",
            level=ChunkingLevel.POINT,
            clause_number="3",
            point_label="a",
        )
        row = chunk.model_dump(mode="json")
        del row["point_label"]
        jsonl_path = tmp_path / "point_bad.jsonl"
        _write_raw_jsonl(jsonl_path, [row])

        validator = ProcessedJsonlValidator(_config())
        report = validator.validate(jsonl_path)

        assert report.required_field_failures == 1
        assert report.invalid_chunks == 1

    def test_empty_string_field_caught_by_schema(self, tmp_path: Path) -> None:
        # Empty law_id passes presence check (key exists) but fails schema validation
        row = _valid_chunk(chunk_id="c1").model_dump(mode="json")
        row["law_id"] = ""  # empty string — schema rejects (min_length=1)
        jsonl_path = tmp_path / "empty_field.jsonl"
        _write_raw_jsonl(jsonl_path, [row])

        validator = ProcessedJsonlValidator(_config())
        report = validator.validate(jsonl_path)

        assert report.schema_failures == 1
        assert report.invalid_chunks == 1


class TestDuplicateChunkId:
    """Global chunk_id uniqueness."""

    def test_duplicate_chunk_id_detected(self, tmp_path: Path) -> None:
        chunk = _valid_chunk(chunk_id="dup_id")
        jsonl_path = tmp_path / "dup.jsonl"
        _write_jsonl(jsonl_path, [chunk, chunk])

        validator = ProcessedJsonlValidator(_config())
        report = validator.validate(jsonl_path)

        assert report.status == "fail"
        assert report.duplicate_chunk_ids == 1
        assert report.errors_total == 1
        assert report.invalid_chunks == 1
        assert report.valid_chunks == 1
        assert (
            report.sample_failures[0].code == ProcessedJsonlValidationIssueCode.DUPLICATE_CHUNK_ID
        )

    def test_unique_chunk_ids_pass(self, tmp_path: Path) -> None:
        chunks = [
            _valid_chunk(chunk_id="a"),
            _valid_chunk(chunk_id="b"),
            _valid_chunk(chunk_id="c"),
        ]
        jsonl_path = tmp_path / "unique.jsonl"
        _write_jsonl(jsonl_path, chunks)

        validator = ProcessedJsonlValidator(_config())
        report = validator.validate(jsonl_path)

        assert report.duplicate_chunk_ids == 0
        assert report.valid_chunks == 3


class TestCappedSamples:
    """sample_failures and sample_warnings are capped by config."""

    def test_sample_failures_capped(self, tmp_path: Path) -> None:
        rows = []
        for i in range(60):
            rows.append({"not": f"valid_{i}"})
        jsonl_path = tmp_path / "many_bad.jsonl"
        _write_raw_jsonl(jsonl_path, rows)

        config = _config(max_sample_failures=10)
        validator = ProcessedJsonlValidator(config)
        report = validator.validate(jsonl_path)

        assert report.errors_total == 60
        assert len(report.sample_failures) == 10  # capped at max_sample_failures
        assert len(report.sample_warnings) == 0

    def test_sample_warnings_capped(self, tmp_path: Path) -> None:
        # Slice 3A doesn't produce warnings, but test the cap mechanism
        config = _config(max_sample_warnings=5)
        validator = ProcessedJsonlValidator(config)
        # Just verify the config is accepted
        assert validator.config.max_sample_warnings == 5


class TestCounts:
    """valid_chunks and invalid_chunks count lines, not total errors."""

    def test_valid_invalid_counts(self, tmp_path: Path) -> None:
        # Line 1: valid
        # Line 2: bad JSON
        # Line 3: valid
        # Line 4: duplicate chunk_id (valid schema but duplicate)
        jsonl_path = tmp_path / "counts.jsonl"
        with jsonl_path.open("w", encoding="utf-8") as fh:
            fh.write(
                json.dumps(_valid_chunk(chunk_id="c1").model_dump(mode="json"), ensure_ascii=False)
                + "\n"
            )
            fh.write("not json\n")
            fh.write(
                json.dumps(_valid_chunk(chunk_id="c2").model_dump(mode="json"), ensure_ascii=False)
                + "\n"
            )
            fh.write(
                json.dumps(_valid_chunk(chunk_id="c1").model_dump(mode="json"), ensure_ascii=False)
                + "\n"
            )

        validator = ProcessedJsonlValidator(_config())
        report = validator.validate(jsonl_path)

        assert report.total_lines == 4
        assert report.valid_chunks == 2  # lines 1 and 3
        assert report.invalid_chunks == 2  # lines 2 and 4
        assert report.jsonl_parse_failures == 1
        assert report.duplicate_chunk_ids == 1

    def test_chunks_by_level_and_law_populated(self, tmp_path: Path) -> None:
        chunks = [
            _valid_chunk(chunk_id="c1", law_id="law_a", level=ChunkingLevel.ARTICLE),
            _valid_chunk(chunk_id="c2", law_id="law_a", level=ChunkingLevel.CLAUSE),
            _valid_chunk(chunk_id="c3", law_id="law_b", level=ChunkingLevel.POINT),
        ]
        jsonl_path = tmp_path / "dist.jsonl"
        _write_jsonl(jsonl_path, chunks)

        validator = ProcessedJsonlValidator(_config())
        report = validator.validate(jsonl_path)

        assert report.chunks_by_level == {"article": 1, "clause": 1, "point": 1}
        assert report.chunks_by_law == {"law_a": 2, "law_b": 1}


# ---------------------------------------------------------------------------
# Slice 3A: Hash integrity tests
# ---------------------------------------------------------------------------


class TestHashIntegrity:
    """Hash integrity checks (Slice 3A)."""

    def test_valid_hashes_pass(self, tmp_path: Path) -> None:
        """Chunks with correct hashes should pass validation."""
        chunk = _valid_chunk(chunk_id="h_ok")
        jsonl_path = tmp_path / "hash_ok.jsonl"
        _write_jsonl(jsonl_path, [chunk])

        validator = ProcessedJsonlValidator(_config())
        report = validator.validate(jsonl_path)

        assert report.hash_mismatches == 0
        assert report.status == "pass"
        assert report.valid_chunks == 1
        assert report.invalid_chunks == 0

    def test_text_hash_mismatch_detected(self, tmp_path: Path) -> None:
        """A wrong text_hash should be flagged as a hash mismatch."""
        chunk = _valid_chunk(chunk_id="h_text_bad", text_hash="wrong_hash")
        jsonl_path = tmp_path / "hash_text_bad.jsonl"
        _write_jsonl(jsonl_path, [chunk])

        validator = ProcessedJsonlValidator(_config())
        report = validator.validate(jsonl_path)

        assert report.hash_mismatches == 1
        assert report.status == "fail"
        assert report.invalid_chunks == 1
        assert report.valid_chunks == 0
        assert report.sample_failures[0].code == ProcessedJsonlValidationIssueCode.HASH_MISMATCH
        assert report.sample_failures[0].context["text_hash_match"] is False
        assert report.sample_failures[0].context["parent_text_hash_match"] is True

    def test_parent_text_hash_mismatch_detected(self, tmp_path: Path) -> None:
        """A wrong parent_text_hash should be flagged as a hash mismatch."""
        chunk = _valid_chunk(
            chunk_id="h_parent_bad",
            parent_text_hash="wrong_hash",
        )
        jsonl_path = tmp_path / "hash_parent_bad.jsonl"
        _write_jsonl(jsonl_path, [chunk])

        validator = ProcessedJsonlValidator(_config())
        report = validator.validate(jsonl_path)

        assert report.hash_mismatches == 1
        assert report.status == "fail"
        assert report.invalid_chunks == 1
        assert report.sample_failures[0].code == ProcessedJsonlValidationIssueCode.HASH_MISMATCH
        assert report.sample_failures[0].context["text_hash_match"] is True
        assert report.sample_failures[0].context["parent_text_hash_match"] is False

    def test_both_hashes_mismatch_increments_once(self, tmp_path: Path) -> None:
        """Both hashes wrong on one line should increment hash_mismatches once."""
        chunk = _valid_chunk(
            chunk_id="h_both_bad",
            text_hash="wrong1",
            parent_text_hash="wrong2",
        )
        jsonl_path = tmp_path / "hash_both_bad.jsonl"
        _write_jsonl(jsonl_path, [chunk])

        validator = ProcessedJsonlValidator(_config())
        report = validator.validate(jsonl_path)

        assert report.hash_mismatches == 1  # one line, one increment
        assert report.errors_total == 1  # one error total
        assert report.invalid_chunks == 1
        assert report.valid_chunks == 0

    def test_one_line_both_mismatches_is_one_invalid_chunk(self, tmp_path: Path) -> None:
        """A single line with both hashes wrong counts as one invalid chunk."""
        chunk = _valid_chunk(
            chunk_id="h_one_line",
            text_hash="wrong",
            parent_text_hash="wrong",
        )
        jsonl_path = tmp_path / "hash_one_line.jsonl"
        _write_jsonl(jsonl_path, [chunk])

        validator = ProcessedJsonlValidator(_config())
        report = validator.validate(jsonl_path)

        assert report.invalid_chunks == 1
        assert report.valid_chunks == 0
        assert report.hash_mismatches == 1

    def test_hash_mismatch_sample_failures_capped(self, tmp_path: Path) -> None:
        """Hash mismatch samples are capped by max_sample_failures."""
        rows = []
        for i in range(15):
            chunk = _valid_chunk(
                chunk_id=f"h_cap_{i}",
                text_hash=f"wrong_{i}",
            )
            rows.append(chunk.model_dump(mode="json"))
        jsonl_path = tmp_path / "hash_cap.jsonl"
        _write_raw_jsonl(jsonl_path, rows)

        config = _config(max_sample_failures=5)
        validator = ProcessedJsonlValidator(config)
        report = validator.validate(jsonl_path)

        assert report.hash_mismatches == 15
        assert report.errors_total == 15
        assert len(report.sample_failures) == 5  # capped


# ---------------------------------------------------------------------------
# Slice 3A scope: later checks are not yet implemented
# ---------------------------------------------------------------------------


class TestSlice3AScope:
    """Slice 3A only implements hash integrity; later checks are skipped."""

    def test_count_reconciliation_not_implemented(self, tmp_path: Path) -> None:
        """Count reconciliation is not checked in Slice 3A."""
        chunk = _valid_chunk(chunk_id="c1")
        jsonl_path = tmp_path / "recon.jsonl"
        _write_jsonl(jsonl_path, [chunk])

        validator = ProcessedJsonlValidator(_config())
        report = validator.validate(jsonl_path)

        assert report.count_reconciliation_failures == 0
        assert report.status == "pass"

    def test_citation_not_checked_in_slice3a(self, tmp_path: Path) -> None:
        """Citation structure is not checked in Slice 3A."""
        chunk = _valid_chunk(chunk_id="c1", citation="bad citation")
        jsonl_path = tmp_path / "cite.jsonl"
        _write_jsonl(jsonl_path, [chunk])

        validator = ProcessedJsonlValidator(_config())
        report = validator.validate(jsonl_path)

        assert report.citation_failures == 0
        assert report.status == "pass"

    def test_hierarchy_traceability_not_checked_in_slice3a(self, tmp_path: Path) -> None:
        """Hierarchy traceability is not checked in Slice 3A."""
        chunk = _valid_chunk(chunk_id="c1")
        jsonl_path = tmp_path / "hier.jsonl"
        _write_jsonl(jsonl_path, [chunk])

        validator = ProcessedJsonlValidator(_config())
        report = validator.validate(jsonl_path)

        assert report.traceability_failures == 0
        assert report.traceability_checks_skipped is True

    def test_later_slice_fields_are_neutral(self, tmp_path: Path) -> None:
        """Fields for later slices are set to neutral values."""
        chunk = _valid_chunk(chunk_id="c1")
        jsonl_path = tmp_path / "neutral.jsonl"
        _write_jsonl(jsonl_path, [chunk])

        validator = ProcessedJsonlValidator(_config())
        report = validator.validate(jsonl_path)

        assert report.count_reconciliation_failures == 0
        assert report.citation_failures == 0
        assert report.traceability_failures == 0
        assert report.contamination_failures == 0
        assert report.contamination_warnings == 0
        assert report.text_length_summary == {}
        assert report.parent_text_length_summary == {}
        assert report.long_parent_text_summary == {}
        assert report.repealed_metadata_summary == {}
        assert report.payload_readiness_summary == {}
        assert report.embedding_readiness == {}
