"""Unit tests for Phase 7 processed JSONL validator through Slice 3E."""

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
    ProcessedJsonlValidationReport,
)
from src.processing.processed_jsonl_validator import ProcessedJsonlValidator

# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def _config(
    jsonl_path: Path | None = None,
    **overrides: object,
) -> ProcessedJsonlValidationConfig:
    """Build a ProcessedJsonlValidationConfig with sensible defaults."""
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "validator_version": "v0.1.0",
    }
    if jsonl_path is not None and "chunking_report_path" not in overrides:
        report_path = jsonl_path.with_name(f"{jsonl_path.stem}_chunking_report.json")
        total_lines = len(jsonl_path.read_text(encoding="utf-8").splitlines())
        report_path.write_text(
            json.dumps({"total_chunks": total_lines}),
            encoding="utf-8",
        )
        payload["chunking_report_path"] = str(report_path)
    if jsonl_path is not None and "hierarchy_dir" not in overrides:
        hierarchy_root = jsonl_path.with_name(f"{jsonl_path.stem}_hierarchies")
        _write_matching_hierarchies(jsonl_path, hierarchy_root)
        payload["hierarchy_dir"] = str(hierarchy_root)
    payload.update(overrides)
    return ProcessedJsonlValidationConfig(**payload)


def _valid_chunk(**overrides: object) -> LegalChunk:
    """Build a minimal valid LegalChunk with real hashes for test data."""
    text = "Nội dung văn bản pháp luật dùng để kiểm tra một đoạn dữ liệu hợp lệ."
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
    chunk_kind = payload["chunk_kind"]
    if chunk_kind == "clause_level" and "source_node_id" not in overrides:
        payload["source_node_id"] = "node_001__clause"
    if chunk_kind == "point_level" and "source_node_id" not in overrides:
        payload["source_node_id"] = "node_001__clause__point"
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


def _write_hierarchy(
    root: Path,
    law_id: str,
    nodes: list[dict[str, object]],
) -> Path:
    """Write a minimal flat hierarchy fixture matching the production schema."""
    path = root / law_id / "hierarchy.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"law_id": law_id, "nodes": nodes}, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def _write_matching_hierarchies(jsonl_path: Path, hierarchy_root: Path) -> None:
    """Write minimal hierarchy fixtures for schema-valid-looking JSONL rows."""
    nodes_by_law: dict[str, dict[str, dict[str, object]]] = {}
    for raw_line in jsonl_path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue

        law_id = row.get("law_id")
        source_node_id = row.get("source_node_id")
        parent_article_node_id = row.get("parent_article_node_id")
        if not all(
            isinstance(value, str) and value
            for value in (law_id, source_node_id, parent_article_node_id)
        ):
            continue

        article_number = row.get("article_number")
        clause_number = row.get("clause_number")
        point_label = row.get("point_label")
        level = row.get("level")
        chunk_kind = row.get("chunk_kind")
        source_level = {
            "article_level": "article",
            "article_level_empty": "article",
            "clause_level": "clause",
            "point_level": "point",
        }.get(chunk_kind, level)
        law_nodes = nodes_by_law.setdefault(law_id, {})
        law_nodes[parent_article_node_id] = {
            "node_id": parent_article_node_id,
            "level": "article",
            "number": article_number,
            "parent_id": f"{law_id}__root",
            "children": [],
        }

        source_parent_id = parent_article_node_id
        if source_level == "point":
            source_parent_id = f"{source_node_id}__test_parent_clause"
            law_nodes[source_parent_id] = {
                "node_id": source_parent_id,
                "level": "clause",
                "number": clause_number,
                "parent_id": parent_article_node_id,
                "children": [source_node_id],
            }

        source_number = {
            "article": article_number,
            "clause": clause_number,
            "point": point_label,
        }.get(source_level)
        law_nodes[source_node_id] = {
            "node_id": source_node_id,
            "level": source_level,
            "number": source_number,
            "parent_id": source_parent_id,
            "children": [],
        }

    for law_id, nodes in nodes_by_law.items():
        _write_hierarchy(hierarchy_root, law_id, list(nodes.values()))


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


class TestValidJsonl:
    """Happy path: valid JSONL with valid chunks."""

    def test_valid_jsonl_returns_pass(self, tmp_path: Path) -> None:
        chunk = _valid_chunk()
        jsonl_path = tmp_path / "valid.jsonl"
        _write_jsonl(jsonl_path, [chunk])

        validator = ProcessedJsonlValidator(_config(jsonl_path))
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

        validator = ProcessedJsonlValidator(_config(jsonl_path))
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

        validator = ProcessedJsonlValidator(_config(jsonl_path))
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

        validator = ProcessedJsonlValidator(_config(jsonl_path))
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

        validator = ProcessedJsonlValidator(_config(jsonl_path))
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

        validator = ProcessedJsonlValidator(_config(jsonl_path))
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

        validator = ProcessedJsonlValidator(_config(jsonl_path))
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

        validator = ProcessedJsonlValidator(_config(jsonl_path))
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

        validator = ProcessedJsonlValidator(_config(jsonl_path))
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

        validator = ProcessedJsonlValidator(_config(jsonl_path))
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

        validator = ProcessedJsonlValidator(_config(jsonl_path))
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
            citation="Luật thử nghiệm, Khoản 2, Điều 1",
        )
        row = chunk.model_dump(mode="json")
        del row["clause_number"]
        jsonl_path = tmp_path / "clause_bad.jsonl"
        _write_raw_jsonl(jsonl_path, [row])

        validator = ProcessedJsonlValidator(_config(jsonl_path))
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
            citation="Luật thử nghiệm, Khoản 2, Điều 1",
        )
        jsonl_path = tmp_path / "clause_ok.jsonl"
        _write_jsonl(jsonl_path, [chunk])

        validator = ProcessedJsonlValidator(_config(jsonl_path))
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

        validator = ProcessedJsonlValidator(_config(jsonl_path))
        report = validator.validate(jsonl_path)

        assert report.required_field_failures == 1
        assert report.invalid_chunks == 1

    def test_empty_string_field_caught_by_schema(self, tmp_path: Path) -> None:
        # Empty law_id passes presence check (key exists) but fails schema validation
        row = _valid_chunk(chunk_id="c1").model_dump(mode="json")
        row["law_id"] = ""  # empty string — schema rejects (min_length=1)
        jsonl_path = tmp_path / "empty_field.jsonl"
        _write_raw_jsonl(jsonl_path, [row])

        validator = ProcessedJsonlValidator(_config(jsonl_path))
        report = validator.validate(jsonl_path)

        assert report.schema_failures == 1
        assert report.invalid_chunks == 1


class TestDuplicateChunkId:
    """Global chunk_id uniqueness."""

    def test_duplicate_chunk_id_detected(self, tmp_path: Path) -> None:
        chunk = _valid_chunk(chunk_id="dup_id")
        jsonl_path = tmp_path / "dup.jsonl"
        _write_jsonl(jsonl_path, [chunk, chunk])

        validator = ProcessedJsonlValidator(_config(jsonl_path))
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

        validator = ProcessedJsonlValidator(_config(jsonl_path))
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

        config = _config(jsonl_path, max_sample_failures=10)
        validator = ProcessedJsonlValidator(config)
        report = validator.validate(jsonl_path)

        assert report.errors_total == 60
        assert len(report.sample_failures) == 10  # capped at max_sample_failures
        assert len(report.sample_warnings) == 0

    def test_sample_warnings_capped(self, tmp_path: Path) -> None:
        # Verify the warning sample cap is accepted by the config.
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

        validator = ProcessedJsonlValidator(_config(jsonl_path))
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

        validator = ProcessedJsonlValidator(_config(jsonl_path))
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

        validator = ProcessedJsonlValidator(_config(jsonl_path))
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

        validator = ProcessedJsonlValidator(_config(jsonl_path))
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

        validator = ProcessedJsonlValidator(_config(jsonl_path))
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

        validator = ProcessedJsonlValidator(_config(jsonl_path))
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

        validator = ProcessedJsonlValidator(_config(jsonl_path))
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

        config = _config(jsonl_path, max_sample_failures=5)
        validator = ProcessedJsonlValidator(config)
        report = validator.validate(jsonl_path)

        assert report.hash_mismatches == 15
        assert report.errors_total == 15
        assert len(report.sample_failures) == 5  # capped


# ---------------------------------------------------------------------------
# Slice 3B: Count reconciliation tests
# ---------------------------------------------------------------------------


class TestCountReconciliation:
    """Count reconciliation against the Phase 6 chunking report."""

    def _write_chunking_report(self, path: Path, data: object) -> None:
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_missing_chunking_report_warns_without_failure(self, tmp_path: Path) -> None:
        jsonl_path = tmp_path / "missing_report.jsonl"
        _write_jsonl(jsonl_path, [_valid_chunk()])
        report_path = tmp_path / "does_not_exist.json"

        validator = ProcessedJsonlValidator(
            _config(jsonl_path, chunking_report_path=str(report_path))
        )
        report = validator.validate(jsonl_path)

        assert report.count_reconciliation_failures == 0
        assert report.warnings_total >= 1
        assert report.status == "pass_with_warnings"
        assert (
            report.sample_warnings[0].code
            == ProcessedJsonlValidationIssueCode.COUNT_RECONCILIATION_FAILED
        )
        assert report.sample_warnings[0].context["reason"] == "report_missing"

    def test_invalid_chunking_report_json_warns_without_failure(self, tmp_path: Path) -> None:
        jsonl_path = tmp_path / "invalid_report_json.jsonl"
        report_path = tmp_path / "invalid_report.json"
        _write_jsonl(jsonl_path, [_valid_chunk()])
        report_path.write_text("{invalid json", encoding="utf-8")

        report = ProcessedJsonlValidator(
            _config(jsonl_path, chunking_report_path=str(report_path))
        ).validate(jsonl_path)

        assert report.count_reconciliation_failures == 0
        assert report.warnings_total == 1
        assert report.status == "pass_with_warnings"
        assert report.sample_warnings[0].context["reason"] == "invalid_json"
        assert "error" in report.sample_warnings[0].context

    def test_non_object_chunking_report_warns_without_failure(self, tmp_path: Path) -> None:
        jsonl_path = tmp_path / "non_object_report.jsonl"
        report_path = tmp_path / "non_object_report.json"
        _write_jsonl(jsonl_path, [_valid_chunk()])
        self._write_chunking_report(report_path, ["not", "an", "object"])

        report = ProcessedJsonlValidator(
            _config(jsonl_path, chunking_report_path=str(report_path))
        ).validate(jsonl_path)

        assert report.count_reconciliation_failures == 0
        assert report.warnings_total == 1
        assert report.status == "pass_with_warnings"
        assert report.sample_warnings[0].context["reason"] == "report_root_not_object"

    def test_missing_total_chunks_warns_without_failure(self, tmp_path: Path) -> None:
        jsonl_path = tmp_path / "missing_total.jsonl"
        report_path = tmp_path / "missing_total_report.json"
        _write_jsonl(jsonl_path, [_valid_chunk()])
        self._write_chunking_report(report_path, {"successful": 1})

        report = ProcessedJsonlValidator(
            _config(jsonl_path, chunking_report_path=str(report_path))
        ).validate(jsonl_path)

        assert report.count_reconciliation_failures == 0
        assert report.warnings_total == 1
        assert report.status == "pass_with_warnings"
        assert report.sample_warnings[0].context["reason"] == "total_chunks_missing"

    def test_invalid_total_chunks_warns_without_failure(self, tmp_path: Path) -> None:
        jsonl_path = tmp_path / "invalid_total.jsonl"
        report_path = tmp_path / "invalid_total_report.json"
        _write_jsonl(jsonl_path, [_valid_chunk()])
        self._write_chunking_report(report_path, {"total_chunks": "1"})

        report = ProcessedJsonlValidator(
            _config(jsonl_path, chunking_report_path=str(report_path))
        ).validate(jsonl_path)

        assert report.count_reconciliation_failures == 0
        assert report.warnings_total == 1
        assert report.status == "pass_with_warnings"
        assert report.sample_warnings[0].context["reason"] == "total_chunks_invalid"
        assert report.sample_warnings[0].context["raw_total_chunks"] == "1"

    def test_negative_total_chunks_warns_without_failure(self, tmp_path: Path) -> None:
        jsonl_path = tmp_path / "negative_total.jsonl"
        report_path = tmp_path / "negative_total_report.json"
        _write_jsonl(jsonl_path, [_valid_chunk()])
        self._write_chunking_report(report_path, {"total_chunks": -1})

        report = ProcessedJsonlValidator(
            _config(jsonl_path, chunking_report_path=str(report_path))
        ).validate(jsonl_path)

        assert report.count_reconciliation_failures == 0
        assert report.warnings_total == 1
        assert report.status == "pass_with_warnings"
        assert report.sample_warnings[0].context["reason"] == "total_chunks_invalid"
        assert report.sample_warnings[0].context["raw_total_chunks"] == -1

    def test_matching_total_chunks_passes(self, tmp_path: Path) -> None:
        jsonl_path = tmp_path / "matching_total.jsonl"
        report_path = tmp_path / "matching_total_report.json"
        _write_jsonl(jsonl_path, [_valid_chunk()])
        self._write_chunking_report(report_path, {"total_chunks": 1})

        report = ProcessedJsonlValidator(
            _config(jsonl_path, chunking_report_path=str(report_path))
        ).validate(jsonl_path)

        assert report.count_reconciliation_failures == 0
        assert report.status == "pass"

    def test_mismatched_total_chunks_fails(self, tmp_path: Path) -> None:
        jsonl_path = tmp_path / "mismatched_total.jsonl"
        report_path = tmp_path / "mismatched_total_report.json"
        _write_jsonl(jsonl_path, [_valid_chunk()])
        self._write_chunking_report(report_path, {"total_chunks": 3})

        report = ProcessedJsonlValidator(
            _config(jsonl_path, chunking_report_path=str(report_path))
        ).validate(jsonl_path)

        assert report.count_reconciliation_failures == 1
        assert report.errors_total >= 1
        assert report.status == "fail"
        issue = report.sample_failures[0]
        assert issue.code == ProcessedJsonlValidationIssueCode.COUNT_RECONCILIATION_FAILED
        assert issue.context["expected_total"] == 3
        assert issue.context["observed_total"] == 1
        assert issue.context["delta"] == -2

    def test_matching_chunks_by_level_passes(self, tmp_path: Path) -> None:
        jsonl_path = tmp_path / "matching_levels.jsonl"
        report_path = tmp_path / "matching_levels_report.json"
        chunks = [
            _valid_chunk(chunk_id="article", level=ChunkingLevel.ARTICLE),
            _valid_chunk(chunk_id="clause", level=ChunkingLevel.CLAUSE),
        ]
        _write_jsonl(jsonl_path, chunks)
        self._write_chunking_report(
            report_path,
            {"total_chunks": 2, "chunks_by_level": {"article": 1, "clause": 1}},
        )

        report = ProcessedJsonlValidator(
            _config(jsonl_path, chunking_report_path=str(report_path))
        ).validate(jsonl_path)

        assert report.count_reconciliation_failures == 0
        assert report.status == "pass"

    def test_mismatched_chunks_by_level_fails(self, tmp_path: Path) -> None:
        jsonl_path = tmp_path / "mismatched_levels.jsonl"
        report_path = tmp_path / "mismatched_levels_report.json"
        _write_jsonl(jsonl_path, [_valid_chunk()])
        self._write_chunking_report(
            report_path,
            {"total_chunks": 1, "chunks_by_level": {"article": 2}},
        )

        report = ProcessedJsonlValidator(
            _config(jsonl_path, chunking_report_path=str(report_path))
        ).validate(jsonl_path)

        assert report.count_reconciliation_failures == 1
        assert report.status == "fail"
        issue = report.sample_failures[0]
        assert issue.context["level"] == "article"
        assert issue.context["expected"] == 2
        assert issue.context["observed"] == 1

    def test_malformed_chunks_by_level_warns(self, tmp_path: Path) -> None:
        jsonl_path = tmp_path / "malformed_levels.jsonl"
        report_path = tmp_path / "malformed_levels_report.json"
        _write_jsonl(jsonl_path, [_valid_chunk()])
        self._write_chunking_report(
            report_path,
            {"total_chunks": 1, "chunks_by_level": ["article"]},
        )

        report = ProcessedJsonlValidator(
            _config(jsonl_path, chunking_report_path=str(report_path))
        ).validate(jsonl_path)

        assert report.count_reconciliation_failures == 0
        assert report.status == "pass_with_warnings"
        assert report.sample_warnings[0].context["reason"] == "chunks_by_level_malformed"

    def test_law_count_mismatch_warns_not_fails(self, tmp_path: Path) -> None:
        jsonl_path = tmp_path / "law_count_mismatch.jsonl"
        report_path = tmp_path / "law_count_mismatch_report.json"
        _write_jsonl(jsonl_path, [_valid_chunk(law_id="law_001")])
        self._write_chunking_report(
            report_path,
            {"total_chunks": 1, "chunks_by_law": {"law_001": 1, "law_002": 0}},
        )

        report = ProcessedJsonlValidator(
            _config(jsonl_path, chunking_report_path=str(report_path))
        ).validate(jsonl_path)

        assert report.count_reconciliation_failures == 0
        assert report.status == "pass_with_warnings"
        issue = report.sample_warnings[0]
        assert issue.context["expected_law_count"] == 2
        assert issue.context["observed_law_count"] == 1

    def test_malformed_chunks_by_law_warns(self, tmp_path: Path) -> None:
        jsonl_path = tmp_path / "malformed_laws.jsonl"
        report_path = tmp_path / "malformed_laws_report.json"
        _write_jsonl(jsonl_path, [_valid_chunk()])
        self._write_chunking_report(
            report_path,
            {"total_chunks": 1, "chunks_by_law": ["law_001"]},
        )

        report = ProcessedJsonlValidator(
            _config(jsonl_path, chunking_report_path=str(report_path))
        ).validate(jsonl_path)

        assert report.count_reconciliation_failures == 0
        assert report.status == "pass_with_warnings"
        assert report.sample_warnings[0].context["reason"] == "chunks_by_law_malformed"


# ---------------------------------------------------------------------------
# Slice 3C: Citation structural validation tests
# ---------------------------------------------------------------------------


class TestCitationStructure:
    """Citation structure checks against chunk hierarchy metadata."""

    def _validate_chunk(
        self,
        tmp_path: Path,
        filename: str,
        chunk: LegalChunk,
    ) -> ProcessedJsonlValidationReport:
        jsonl_path = tmp_path / filename
        _write_jsonl(jsonl_path, [chunk])
        return ProcessedJsonlValidator(_config(jsonl_path)).validate(jsonl_path)

    def test_article_level_citation_with_article_passes(self, tmp_path: Path) -> None:
        report = self._validate_chunk(
            tmp_path,
            "article_valid.jsonl",
            _valid_chunk(citation="Luật thử nghiệm, Điều 1"),
        )

        assert report.citation_failures == 0
        assert report.status == "pass"

    def test_article_level_empty_citation_with_article_passes(self, tmp_path: Path) -> None:
        text = "Điều 1. (được bãi bỏ)"
        report = self._validate_chunk(
            tmp_path,
            "article_empty_valid.jsonl",
            _valid_chunk(
                chunk_kind="article_level_empty",
                citation="Luật thử nghiệm (VBHN), Điều 1",
                text=text,
                text_hash=_compute_text_hash(text),
                metadata=ChunkingMetadata(
                    is_empty_or_repealed=True,
                    is_source_unit_repealed=True,
                ),
            ),
        )

        assert report.citation_failures == 0
        assert report.status == "pass"

    def test_article_level_missing_article_in_citation_fails(self, tmp_path: Path) -> None:
        report = self._validate_chunk(
            tmp_path,
            "article_missing.jsonl",
            _valid_chunk(citation="Luật thử nghiệm"),
        )

        assert report.citation_failures == 1
        assert report.status == "fail"
        issue = report.sample_failures[0]
        assert issue.code == ProcessedJsonlValidationIssueCode.CITATION_STRUCTURE_MISMATCH
        assert issue.context["missing_components"] == [{"label": "Điều", "value": "1"}]

    def test_clause_level_requires_clause_and_article(self, tmp_path: Path) -> None:
        report = self._validate_chunk(
            tmp_path,
            "clause_valid.jsonl",
            _valid_chunk(
                level=ChunkingLevel.CLAUSE,
                chunk_kind="clause_level",
                article_number="5",
                clause_number="2",
                citation="Luật thử nghiệm, Điều 5; Khoản 2",
            ),
        )

        assert report.citation_failures == 0
        assert report.status == "pass"

    def test_clause_level_missing_clause_fails(self, tmp_path: Path) -> None:
        report = self._validate_chunk(
            tmp_path,
            "clause_missing_clause.jsonl",
            _valid_chunk(
                level=ChunkingLevel.CLAUSE,
                chunk_kind="clause_level",
                article_number="5",
                clause_number="2",
                citation="Luật thử nghiệm, Điều 5",
            ),
        )

        assert report.citation_failures == 1
        assert report.sample_failures[0].context["missing_components"] == [
            {"label": "Khoản", "value": "2"}
        ]

    def test_clause_level_missing_article_fails(self, tmp_path: Path) -> None:
        report = self._validate_chunk(
            tmp_path,
            "clause_missing_article.jsonl",
            _valid_chunk(
                level=ChunkingLevel.CLAUSE,
                chunk_kind="clause_level",
                article_number="5",
                clause_number="2",
                citation="Luật thử nghiệm, Khoản 2",
            ),
        )

        assert report.citation_failures == 1
        assert report.sample_failures[0].context["missing_components"] == [
            {"label": "Điều", "value": "5"}
        ]

    def test_point_level_requires_point_clause_article(self, tmp_path: Path) -> None:
        report = self._validate_chunk(
            tmp_path,
            "point_valid.jsonl",
            _valid_chunk(
                level=ChunkingLevel.POINT,
                chunk_kind="point_level",
                article_number="5",
                clause_number="2",
                point_label="a",
                citation="Luật thử nghiệm: Điều 5, Điểm a, Khoản 2.",
            ),
        )

        assert report.citation_failures == 0
        assert report.status == "pass"

    def test_point_level_missing_point_fails(self, tmp_path: Path) -> None:
        report = self._validate_chunk(
            tmp_path,
            "point_missing_point.jsonl",
            _valid_chunk(
                level=ChunkingLevel.POINT,
                chunk_kind="point_level",
                article_number="5",
                clause_number="2",
                point_label="a",
                citation="Luật thử nghiệm, Khoản 2, Điều 5",
            ),
        )

        assert report.citation_failures == 1
        assert report.sample_failures[0].context["missing_components"] == [
            {"label": "Điểm", "value": "a"}
        ]

    def test_point_level_missing_clause_fails(self, tmp_path: Path) -> None:
        report = self._validate_chunk(
            tmp_path,
            "point_missing_clause.jsonl",
            _valid_chunk(
                level=ChunkingLevel.POINT,
                chunk_kind="point_level",
                article_number="5",
                clause_number="2",
                point_label="a",
                citation="Luật thử nghiệm, Điểm a, Điều 5",
            ),
        )

        assert report.citation_failures == 1
        assert report.sample_failures[0].context["missing_components"] == [
            {"label": "Khoản", "value": "2"}
        ]

    def test_point_level_missing_article_fails(self, tmp_path: Path) -> None:
        report = self._validate_chunk(
            tmp_path,
            "point_missing_article.jsonl",
            _valid_chunk(
                level=ChunkingLevel.POINT,
                chunk_kind="point_level",
                article_number="5",
                clause_number="2",
                point_label="a",
                citation="Luật thử nghiệm, Điểm a, Khoản 2",
            ),
        )

        assert report.citation_failures == 1
        assert report.sample_failures[0].context["missing_components"] == [
            {"label": "Điều", "value": "5"}
        ]

    def test_citation_matching_is_case_insensitive(self, tmp_path: Path) -> None:
        report = self._validate_chunk(
            tmp_path,
            "case_insensitive.jsonl",
            _valid_chunk(citation="Luật thử nghiệm, đIềU 1"),
        )

        assert report.citation_failures == 0
        assert report.status == "pass"

    def test_citation_matching_allows_extra_whitespace(self, tmp_path: Path) -> None:
        report = self._validate_chunk(
            tmp_path,
            "extra_whitespace.jsonl",
            _valid_chunk(citation="Luật thử nghiệm, Điều \n\t  1"),
        )

        assert report.citation_failures == 0
        assert report.status == "pass"

    def test_article_boundary_does_not_match_prefix(self, tmp_path: Path) -> None:
        report = self._validate_chunk(
            tmp_path,
            "article_prefix.jsonl",
            _valid_chunk(article_number="1", citation="Luật thử nghiệm, Điều 10"),
        )

        assert report.citation_failures == 1
        assert report.status == "fail"

    def test_clause_boundary_does_not_match_prefix(self, tmp_path: Path) -> None:
        report = self._validate_chunk(
            tmp_path,
            "clause_prefix.jsonl",
            _valid_chunk(
                level=ChunkingLevel.CLAUSE,
                chunk_kind="clause_level",
                article_number="5",
                clause_number="2",
                citation="Luật thử nghiệm, Khoản 20, Điều 5",
            ),
        )

        assert report.citation_failures == 1
        assert report.status == "fail"

    def test_point_boundary_does_not_match_prefix(self, tmp_path: Path) -> None:
        report = self._validate_chunk(
            tmp_path,
            "point_prefix.jsonl",
            _valid_chunk(
                level=ChunkingLevel.POINT,
                chunk_kind="point_level",
                article_number="5",
                clause_number="2",
                point_label="a",
                citation="Luật thử nghiệm, Điểm aa, Khoản 2, Điều 5",
            ),
        )

        assert report.citation_failures == 1
        assert report.status == "fail"

    def test_one_chunk_with_multiple_missing_components_counts_once(
        self,
        tmp_path: Path,
    ) -> None:
        report = self._validate_chunk(
            tmp_path,
            "point_all_missing.jsonl",
            _valid_chunk(
                level=ChunkingLevel.POINT,
                chunk_kind="point_level",
                article_number="5",
                clause_number="2",
                point_label="a",
                citation="Luật thử nghiệm",
            ),
        )

        assert report.citation_failures == 1
        assert report.errors_total == 1
        assert report.invalid_chunks == 1
        assert report.valid_chunks == 0
        assert report.sample_failures[0].context["missing_components"] == [
            {"label": "Điểm", "value": "a"},
            {"label": "Khoản", "value": "2"},
            {"label": "Điều", "value": "5"},
        ]


# ---------------------------------------------------------------------------
# Slice 3D: Hierarchy traceability validation tests
# ---------------------------------------------------------------------------


class TestHierarchyTraceability:
    """Hierarchy node existence and metadata traceability checks."""

    def _validate_chunk(
        self,
        tmp_path: Path,
        filename: str,
        chunk: LegalChunk,
        nodes: list[dict[str, object]] | None,
    ) -> ProcessedJsonlValidationReport:
        jsonl_path = tmp_path / filename
        hierarchy_root = tmp_path / f"{jsonl_path.stem}_hierarchies"
        _write_jsonl(jsonl_path, [chunk])
        if nodes is not None:
            _write_hierarchy(hierarchy_root, chunk.law_id, nodes)
        return ProcessedJsonlValidator(
            _config(jsonl_path, hierarchy_dir=str(hierarchy_root))
        ).validate(jsonl_path)

    def test_article_level_traceability_passes(self, tmp_path: Path) -> None:
        chunk = _valid_chunk()
        report = self._validate_chunk(
            tmp_path,
            "article_trace.jsonl",
            chunk,
            [
                {
                    "node_id": chunk.source_node_id,
                    "level": "article",
                    "number": "1",
                    "parent_id": "law_001__root",
                    "children": [],
                }
            ],
        )

        assert report.traceability_failures == 0
        assert report.traceability_checks_skipped is False
        assert report.status == "pass"

    def test_clause_level_traceability_passes(self, tmp_path: Path) -> None:
        chunk = _valid_chunk(
            source_node_id="clause_2",
            parent_article_node_id="article_5",
            level=ChunkingLevel.CLAUSE,
            chunk_kind="clause_level",
            article_number="5",
            clause_number="2",
            citation="Luật thử nghiệm, Khoản 2, Điều 5",
        )
        report = self._validate_chunk(
            tmp_path,
            "clause_trace.jsonl",
            chunk,
            [
                {
                    "node_id": "article_5",
                    "level": "article",
                    "number": "5",
                    "parent_id": "law_001__root",
                },
                {
                    "node_id": "clause_2",
                    "level": "clause",
                    "number": "2",
                    "parent_id": "article_5",
                },
            ],
        )

        assert report.traceability_failures == 0
        assert report.status == "pass"

    def test_point_level_traceability_passes(self, tmp_path: Path) -> None:
        chunk = _valid_chunk(
            source_node_id="point_a",
            parent_article_node_id="article_5",
            level=ChunkingLevel.POINT,
            chunk_kind="point_level",
            article_number="5",
            clause_number="2",
            point_label="a",
            citation="Luật thử nghiệm, Điểm a, Khoản 2, Điều 5",
        )
        report = self._validate_chunk(
            tmp_path,
            "point_trace.jsonl",
            chunk,
            [
                {
                    "node_id": "article_5",
                    "level": "article",
                    "number": "5",
                    "parent_id": "law_001__root",
                },
                {
                    "node_id": "clause_2",
                    "level": "clause",
                    "number": "2",
                    "parent_id": "article_5",
                },
                {
                    "node_id": "point_a",
                    "level": "point",
                    "number": "a",
                    "parent_id": "clause_2",
                },
            ],
        )

        assert report.traceability_failures == 0
        assert report.status == "pass"

    def test_missing_hierarchy_file_fails(self, tmp_path: Path) -> None:
        report = self._validate_chunk(
            tmp_path,
            "missing_hierarchy.jsonl",
            _valid_chunk(),
            None,
        )

        assert report.traceability_failures == 1
        assert report.status == "fail"
        assert (
            report.sample_failures[0].code
            == ProcessedJsonlValidationIssueCode.HIERARCHY_TRACEABILITY_FAILED
        )
        assert report.sample_failures[0].context["failures"][0]["field"] == "hierarchy_file"

    def test_invalid_hierarchy_json_fails(self, tmp_path: Path) -> None:
        chunk = _valid_chunk()
        jsonl_path = tmp_path / "invalid_hierarchy.jsonl"
        hierarchy_root = tmp_path / "invalid_hierarchies"
        hierarchy_path = hierarchy_root / chunk.law_id / "hierarchy.json"
        hierarchy_path.parent.mkdir(parents=True, exist_ok=True)
        hierarchy_path.write_text("{invalid json", encoding="utf-8")
        _write_jsonl(jsonl_path, [chunk])

        report = ProcessedJsonlValidator(
            _config(jsonl_path, hierarchy_dir=str(hierarchy_root))
        ).validate(jsonl_path)

        assert report.traceability_failures == 1
        assert report.status == "fail"
        reason = report.sample_failures[0].context["failures"][0]["reason"]
        assert "invalid JSON" in reason

    def test_source_node_missing_fails(self, tmp_path: Path) -> None:
        chunk = _valid_chunk(
            source_node_id="missing_article",
            parent_article_node_id="article_1",
        )
        report = self._validate_chunk(
            tmp_path,
            "source_missing.jsonl",
            chunk,
            [
                {
                    "node_id": "article_1",
                    "level": "article",
                    "number": "1",
                }
            ],
        )

        assert report.traceability_failures == 1
        assert report.status == "fail"
        fields = {failure["field"] for failure in report.sample_failures[0].context["failures"]}
        assert "source_node_id" in fields

    def test_parent_article_node_missing_fails(self, tmp_path: Path) -> None:
        chunk = _valid_chunk(
            source_node_id="clause_2",
            parent_article_node_id="missing_article",
            level=ChunkingLevel.CLAUSE,
            chunk_kind="clause_level",
            article_number="5",
            clause_number="2",
            citation="Luật thử nghiệm, Khoản 2, Điều 5",
        )
        report = self._validate_chunk(
            tmp_path,
            "parent_missing.jsonl",
            chunk,
            [
                {
                    "node_id": "clause_2",
                    "level": "clause",
                    "number": "2",
                    "parent_id": "missing_article",
                }
            ],
        )

        assert report.traceability_failures == 1
        assert report.status == "fail"
        fields = {failure["field"] for failure in report.sample_failures[0].context["failures"]}
        assert "parent_article_node_id" in fields

    def test_article_number_mismatch_fails_when_node_field_exists(
        self,
        tmp_path: Path,
    ) -> None:
        chunk = _valid_chunk(article_number="1", citation="Luật thử nghiệm, Điều 1")
        report = self._validate_chunk(
            tmp_path,
            "article_number_mismatch.jsonl",
            chunk,
            [
                {
                    "node_id": chunk.source_node_id,
                    "level": "article",
                    "number": "9",
                }
            ],
        )

        assert report.traceability_failures == 1
        assert report.status == "fail"

    def test_clause_number_mismatch_fails_when_node_field_exists(
        self,
        tmp_path: Path,
    ) -> None:
        chunk = _valid_chunk(
            source_node_id="clause_2",
            parent_article_node_id="article_5",
            level=ChunkingLevel.CLAUSE,
            chunk_kind="clause_level",
            article_number="5",
            clause_number="2",
            citation="Luật thử nghiệm, Khoản 2, Điều 5",
        )
        report = self._validate_chunk(
            tmp_path,
            "clause_number_mismatch.jsonl",
            chunk,
            [
                {
                    "node_id": "article_5",
                    "level": "article",
                    "number": "5",
                },
                {
                    "node_id": "clause_2",
                    "level": "clause",
                    "number": "9",
                    "parent_id": "article_5",
                },
            ],
        )

        assert report.traceability_failures == 1
        assert report.status == "fail"

    def test_point_label_mismatch_fails_when_node_field_exists(
        self,
        tmp_path: Path,
    ) -> None:
        chunk = _valid_chunk(
            source_node_id="point_a",
            parent_article_node_id="article_5",
            level=ChunkingLevel.POINT,
            chunk_kind="point_level",
            article_number="5",
            clause_number="2",
            point_label="a",
            citation="Luật thử nghiệm, Điểm a, Khoản 2, Điều 5",
        )
        report = self._validate_chunk(
            tmp_path,
            "point_label_mismatch.jsonl",
            chunk,
            [
                {
                    "node_id": "article_5",
                    "level": "article",
                    "number": "5",
                },
                {
                    "node_id": "clause_2",
                    "level": "clause",
                    "number": "2",
                    "parent_id": "article_5",
                },
                {
                    "node_id": "point_a",
                    "level": "point",
                    "number": "b",
                    "parent_id": "clause_2",
                },
            ],
        )

        assert report.traceability_failures == 1
        assert report.status == "fail"

    def test_multiple_traceability_errors_count_once_per_chunk(
        self,
        tmp_path: Path,
    ) -> None:
        chunk = _valid_chunk(
            source_node_id="missing_source",
            parent_article_node_id="missing_article",
        )
        report = self._validate_chunk(
            tmp_path,
            "multiple_trace_errors.jsonl",
            chunk,
            [
                {
                    "node_id": "unrelated_node",
                    "level": "article",
                    "number": "99",
                }
            ],
        )

        assert report.traceability_failures == 1
        assert report.errors_total == 1
        assert report.invalid_chunks == 1
        assert report.valid_chunks == 0
        assert len(report.sample_failures[0].context["failures"]) >= 2

    def test_unknown_chunk_kind_does_not_fail_traceability_if_nodes_exist(
        self,
        tmp_path: Path,
    ) -> None:
        chunk = _valid_chunk(chunk_kind="future_article_variant")
        report = self._validate_chunk(
            tmp_path,
            "unknown_kind.jsonl",
            chunk,
            [
                {
                    "node_id": chunk.source_node_id,
                    "level": "article",
                    "number": "1",
                }
            ],
        )

        assert report.traceability_failures == 0
        assert report.status == "pass"


# ---------------------------------------------------------------------------
# Slice 3E: Contamination audit tests
# ---------------------------------------------------------------------------


class TestContaminationAudit:
    """Hard and warning contamination checks for child and parent text."""

    def _validate_text(
        self,
        tmp_path: Path,
        filename: str,
        *,
        text: str = "Nội dung văn bản pháp luật dùng để kiểm tra một đoạn dữ liệu hợp lệ.",
        parent_text: str = "Nội dung đầy đủ của Điều 1.",
    ) -> ProcessedJsonlValidationReport:
        chunk = _valid_chunk(
            text=text,
            parent_text=parent_text,
            text_hash=_compute_text_hash(text),
            parent_text_hash=_compute_text_hash(parent_text),
        )
        jsonl_path = tmp_path / filename
        _write_jsonl(jsonl_path, [chunk])
        return ProcessedJsonlValidator(_config(jsonl_path)).validate(jsonl_path)

    def test_no_contamination_passes(self, tmp_path: Path) -> None:
        report = self._validate_text(tmp_path, "clean.jsonl")

        assert report.contamination_failures == 0
        assert report.contamination_warnings == 0
        assert report.status == "pass"

    def test_hard_marker_in_text_fails(self, tmp_path: Path) -> None:
        report = self._validate_text(
            tmp_path,
            "hard_text.jsonl",
            text="XÁC THỰC VĂN BẢN HỢP NHẤT\nNội dung.",
        )

        assert report.contamination_failures == 1
        assert report.status == "fail"
        assert report.invalid_chunks == 1
        assert (
            report.sample_failures[0].code
            == ProcessedJsonlValidationIssueCode.HARD_CONTAMINATION_FOUND
        )

    def test_hard_marker_in_parent_text_fails(self, tmp_path: Path) -> None:
        report = self._validate_text(
            tmp_path,
            "hard_parent.jsonl",
            parent_text="Nội dung Điều 1.\nNơi nhận: Cơ quan liên quan.",
        )

        assert report.contamination_failures == 1
        assert report.status == "fail"

    def test_luu_colon_hard_marker_fails(self, tmp_path: Path) -> None:
        report = self._validate_text(
            tmp_path,
            "luu_colon.jsonl",
            text="Nội dung.\nLưu: Văn thư.",
        )

        assert report.contamination_failures == 1
        assert report.status == "fail"

    def test_luu_y_does_not_trigger_luu_colon(self, tmp_path: Path) -> None:
        report = self._validate_text(
            tmp_path,
            "luu_y.jsonl",
            text="Lưu ý việc áp dụng quy định này trong toàn bộ quá trình thử nghiệm.",
        )

        assert report.contamination_failures == 0
        assert report.status == "pass"

    def test_warning_marker_in_text_warns_only(self, tmp_path: Path) -> None:
        report = self._validate_text(
            tmp_path,
            "warning_text.jsonl",
            text="BỘ TRƯỞNG\nNội dung ký xác nhận.",
        )

        assert report.contamination_warnings == 1
        assert report.contamination_failures == 0
        assert report.status == "pass_with_warnings"
        assert report.invalid_chunks == 0

    def test_warning_marker_in_parent_text_warns_only(self, tmp_path: Path) -> None:
        report = self._validate_text(
            tmp_path,
            "warning_parent.jsonl",
            parent_text="Nội dung Điều 1.\nCHỦ TỊCH QUỐC HỘI",
        )

        assert report.contamination_warnings == 1
        assert report.contamination_failures == 0
        assert report.invalid_chunks == 0

    def test_hard_and_warning_markers_count_separately(self, tmp_path: Path) -> None:
        report = self._validate_text(
            tmp_path,
            "hard_warning.jsonl",
            text="Văn bản này được hợp nhất.\nBỘ TRƯỞNG",
        )

        assert report.contamination_failures == 1
        assert report.contamination_warnings == 1
        assert report.invalid_chunks == 1
        assert report.status == "fail"

    def test_multiple_hard_markers_count_once_per_chunk(self, tmp_path: Path) -> None:
        report = self._validate_text(
            tmp_path,
            "multiple_hard.jsonl",
            text="XÁC THỰC VĂN BẢN HỢP NHẤT\nLưu: Văn thư.",
            parent_text="Nơi nhận: Cơ quan liên quan.",
        )

        assert report.contamination_failures == 1
        hard_samples = [
            issue
            for issue in report.sample_failures
            if issue.code == ProcessedJsonlValidationIssueCode.HARD_CONTAMINATION_FOUND
        ]
        assert len(hard_samples) == 1
        assert len(hard_samples[0].context["matches"]) == 3

    def test_multiple_warning_markers_count_once_per_chunk(self, tmp_path: Path) -> None:
        report = self._validate_text(
            tmp_path,
            "multiple_warning.jsonl",
            text="BỘ TRƯỞNG\nCHỦ NHIỆM",
            parent_text="TM. QUỐC HỘI",
        )

        assert report.contamination_warnings == 1
        contamination_samples = [
            issue
            for issue in report.sample_warnings
            if issue.code == ProcessedJsonlValidationIssueCode.WARNING_CONTAMINATION_FOUND
        ]
        assert len(contamination_samples) == 1
        assert len(contamination_samples[0].context["matches"]) == 3

    def test_matching_is_case_insensitive(self, tmp_path: Path) -> None:
        report = self._validate_text(
            tmp_path,
            "case_insensitive_contamination.jsonl",
            text="xác thực văn bản hợp nhất",
        )

        assert report.contamination_failures == 1

    def test_matches_context_includes_field_and_marker(self, tmp_path: Path) -> None:
        report = self._validate_text(
            tmp_path,
            "match_context.jsonl",
            parent_text="Nội dung.\nNơi nhận: Cơ quan liên quan.",
        )

        contamination_issue = next(
            issue
            for issue in report.sample_failures
            if issue.code == ProcessedJsonlValidationIssueCode.HARD_CONTAMINATION_FOUND
        )
        assert contamination_issue.context["matches"] == [
            {"field": "parent_text", "marker": "Nơi nhận:"}
        ]


# ---------------------------------------------------------------------------
# Slice 3F: Repealed/empty metadata audit tests
# ---------------------------------------------------------------------------


class TestRepealedMetadataAudit:
    """Repealed text patterns and metadata consistency checks."""

    def _chunk(
        self,
        *,
        text: str = "Nội dung văn bản pháp luật dùng để kiểm tra một đoạn dữ liệu hợp lệ.",
        parent_text: str = "Nội dung đầy đủ của Điều 1.",
        metadata: ChunkingMetadata | None = None,
        **overrides: object,
    ) -> LegalChunk:
        return _valid_chunk(
            text=text,
            parent_text=parent_text,
            text_hash=_compute_text_hash(text),
            parent_text_hash=_compute_text_hash(parent_text),
            metadata=metadata or ChunkingMetadata(),
            **overrides,
        )

    def _validate_chunk(
        self,
        tmp_path: Path,
        filename: str,
        chunk: LegalChunk,
    ) -> ProcessedJsonlValidationReport:
        jsonl_path = tmp_path / filename
        _write_jsonl(jsonl_path, [chunk])
        return ProcessedJsonlValidator(_config(jsonl_path)).validate(jsonl_path)

    def test_clean_non_repealed_chunk_summary_counts_zero(self, tmp_path: Path) -> None:
        report = self._validate_chunk(
            tmp_path,
            "repealed_clean.jsonl",
            self._chunk(),
        )

        assert report.repealed_metadata_summary == {
            "metadata_empty_or_repealed_count": 0,
            "metadata_source_unit_repealed_count": 0,
            "text_repealed_pattern_count": 0,
            "parent_text_repealed_pattern_count": 0,
            "text_or_parent_repealed_pattern_count": 0,
            "text_repealed_but_metadata_not_marked_count": 0,
            "article_parent_repealed_but_metadata_not_marked_count": 0,
            "metadata_marked_but_no_text_pattern_count": 0,
            "metadata_mismatch_failure_count": 0,
            "metadata_mismatch_warning_count": 0,
        }

    def test_metadata_empty_or_repealed_counted(self, tmp_path: Path) -> None:
        report = self._validate_chunk(
            tmp_path,
            "metadata_empty.jsonl",
            self._chunk(
                text="Điều 1. (được bãi bỏ)",
                metadata=ChunkingMetadata(is_empty_or_repealed=True),
            ),
        )

        summary = report.repealed_metadata_summary
        assert summary["metadata_empty_or_repealed_count"] == 1
        assert summary["text_repealed_pattern_count"] == 1
        assert summary["metadata_mismatch_failure_count"] == 0

    def test_metadata_source_unit_repealed_counted(self, tmp_path: Path) -> None:
        report = self._validate_chunk(
            tmp_path,
            "metadata_source.jsonl",
            self._chunk(
                text="Điều này được bãi bỏ",
                metadata=ChunkingMetadata(is_source_unit_repealed=True),
            ),
        )

        assert report.repealed_metadata_summary["metadata_source_unit_repealed_count"] == 1
        assert report.status == "pass"

    def test_text_repealed_pattern_counted(self, tmp_path: Path) -> None:
        report = self._validate_chunk(
            tmp_path,
            "repealed_text.jsonl",
            self._chunk(
                text="Khoản này được bãi bỏ",
                metadata=ChunkingMetadata(is_source_unit_repealed=True),
                level=ChunkingLevel.CLAUSE,
                chunk_kind="clause_level",
                clause_number="2",
                citation="Luật thử nghiệm, Khoản 2, Điều 1",
            ),
        )

        assert report.repealed_metadata_summary["text_repealed_pattern_count"] == 1
        assert report.repealed_metadata_summary["text_or_parent_repealed_pattern_count"] == 1

    def test_parent_text_repealed_pattern_counted(self, tmp_path: Path) -> None:
        report = self._validate_chunk(
            tmp_path,
            "repealed_parent.jsonl",
            self._chunk(
                parent_text="Điểm này được bãi bỏ",
                metadata=ChunkingMetadata(is_empty_or_repealed=True),
            ),
        )

        assert report.repealed_metadata_summary["parent_text_repealed_pattern_count"] == 1
        assert report.repealed_metadata_summary["text_or_parent_repealed_pattern_count"] == 1

    def test_repealed_text_without_metadata_fails(self, tmp_path: Path) -> None:
        report = self._validate_chunk(
            tmp_path,
            "repealed_text_mismatch.jsonl",
            self._chunk(text="Khoản này được bãi bỏ"),
        )

        assert report.status == "fail"
        assert report.errors_total == 1
        assert report.invalid_chunks == 1
        assert (
            report.sample_failures[0].code
            == ProcessedJsonlValidationIssueCode.REPEALED_METADATA_MISMATCH
        )
        assert report.repealed_metadata_summary["text_repealed_but_metadata_not_marked_count"] == 1

    def test_repealed_parent_text_without_metadata_fails(self, tmp_path: Path) -> None:
        report = self._validate_chunk(
            tmp_path,
            "repealed_parent_mismatch.jsonl",
            self._chunk(parent_text="Điều này được bãi bỏ"),
        )

        assert report.status == "fail"
        assert report.invalid_chunks == 1
        assert (
            report.repealed_metadata_summary[
                "article_parent_repealed_but_metadata_not_marked_count"
            ]
            == 1
        )

    def test_metadata_marked_without_text_pattern_warns(self, tmp_path: Path) -> None:
        report = self._validate_chunk(
            tmp_path,
            "repealed_metadata_warning.jsonl",
            self._chunk(
                metadata=ChunkingMetadata(is_empty_or_repealed=True),
            ),
        )

        assert report.status == "pass_with_warnings"
        assert report.invalid_chunks == 0
        assert report.warnings_total == 1
        assert (
            report.sample_warnings[0].code
            == ProcessedJsonlValidationIssueCode.REPEALED_METADATA_MISMATCH
        )
        assert report.repealed_metadata_summary["metadata_marked_but_no_text_pattern_count"] == 1

    def test_multiple_repealed_patterns_count_once_per_chunk_for_mismatch(
        self,
        tmp_path: Path,
    ) -> None:
        report = self._validate_chunk(
            tmp_path,
            "multiple_repealed_patterns.jsonl",
            self._chunk(
                text="Điều này được bãi bỏ.\nKhoản này được bãi bỏ.",
            ),
        )

        assert report.errors_total == 1
        assert report.invalid_chunks == 1
        assert report.repealed_metadata_summary["metadata_mismatch_failure_count"] == 1
        assert len(report.sample_failures[0].context["matched_patterns"]) == 2

    def test_summary_counts_multiple_chunks(self, tmp_path: Path) -> None:
        chunks = [
            self._chunk(chunk_id="clean"),
            self._chunk(
                chunk_id="marked",
                text="Điều 1. (được bãi bỏ)",
                metadata=ChunkingMetadata(
                    is_empty_or_repealed=True,
                    is_source_unit_repealed=True,
                ),
            ),
            self._chunk(
                chunk_id="parent_context",
                level=ChunkingLevel.CLAUSE,
                chunk_kind="clause_level",
                clause_number="2",
                citation="Luật thử nghiệm, Khoản 2, Điều 1",
                parent_text="Điều 1.\nĐiểm này được bãi bỏ",
            ),
            self._chunk(
                chunk_id="metadata_warning",
                metadata=ChunkingMetadata(is_empty_or_repealed=True),
            ),
        ]
        jsonl_path = tmp_path / "repealed_summary.jsonl"
        _write_jsonl(jsonl_path, chunks)

        report = ProcessedJsonlValidator(_config(jsonl_path)).validate(jsonl_path)

        assert report.repealed_metadata_summary == {
            "metadata_empty_or_repealed_count": 2,
            "metadata_source_unit_repealed_count": 1,
            "text_repealed_pattern_count": 1,
            "parent_text_repealed_pattern_count": 1,
            "text_or_parent_repealed_pattern_count": 2,
            "text_repealed_but_metadata_not_marked_count": 0,
            "article_parent_repealed_but_metadata_not_marked_count": 0,
            "metadata_marked_but_no_text_pattern_count": 1,
            "metadata_mismatch_failure_count": 0,
            "metadata_mismatch_warning_count": 1,
        }
        assert report.status == "pass_with_warnings"


# ---------------------------------------------------------------------------
# Slice 3G: Text length readiness tests
# ---------------------------------------------------------------------------


class TestTextLengthReadiness:
    """Character-length summaries and readiness warnings."""

    def _chunk(
        self,
        *,
        text: str = "Nội dung văn bản pháp luật dùng để kiểm tra một đoạn dữ liệu hợp lệ.",
        parent_text: str = "Nội dung đầy đủ của Điều 1.",
        metadata: ChunkingMetadata | None = None,
        **overrides: object,
    ) -> LegalChunk:
        return _valid_chunk(
            text=text,
            parent_text=parent_text,
            text_hash=_compute_text_hash(text),
            parent_text_hash=_compute_text_hash(parent_text),
            metadata=metadata or ChunkingMetadata(),
            **overrides,
        )

    def _validate(
        self,
        tmp_path: Path,
        filename: str,
        chunks: list[LegalChunk],
        **config_overrides: object,
    ) -> ProcessedJsonlValidationReport:
        jsonl_path = tmp_path / filename
        _write_jsonl(jsonl_path, chunks)
        return ProcessedJsonlValidator(_config(jsonl_path, **config_overrides)).validate(jsonl_path)

    def test_text_length_summary_populated_for_clean_chunk(self, tmp_path: Path) -> None:
        chunk = self._chunk()
        report = self._validate(tmp_path, "length_text.jsonl", [chunk])

        summary = report.text_length_summary
        assert summary["count"] == 1
        assert summary["min_chars"] == len(chunk.text)
        assert summary["max_chars"] == len(chunk.text)
        assert summary["mean_chars"] == len(chunk.text)

    def test_parent_text_length_summary_populated(self, tmp_path: Path) -> None:
        chunk = self._chunk(parent_text="P" * 120)
        report = self._validate(tmp_path, "length_parent.jsonl", [chunk])

        summary = report.parent_text_length_summary
        assert summary["count"] == 1
        assert summary["min_chars"] == 120
        assert summary["max_chars"] == 120

    def test_multiple_chunks_percentiles_are_stable(self, tmp_path: Path) -> None:
        lengths = [60, 70, 80, 90, 100]
        chunks = [self._chunk(chunk_id=f"length_{length}", text="x" * length) for length in lengths]
        report = self._validate(tmp_path, "length_percentiles.jsonl", chunks)

        summary = report.text_length_summary
        assert summary["count"] == 5
        assert summary["min_chars"] == 60
        assert summary["max_chars"] == 100
        assert summary["p90_chars"] == 100
        assert summary["p95_chars"] == 100
        assert summary["p99_chars"] == 100

    def test_empty_text_non_repealed_fails_or_is_counted_once(self, tmp_path: Path) -> None:
        report = self._validate(
            tmp_path,
            "length_empty_text.jsonl",
            [self._chunk(text="   ")],
        )

        assert report.text_length_summary["empty_text_count"] == 1
        assert report.errors_total == 1
        assert report.invalid_chunks == 1
        empty_issues = [
            issue
            for issue in report.sample_failures
            if issue.code == ProcessedJsonlValidationIssueCode.EMPTY_TEXT_FOUND
        ]
        assert len(empty_issues) == 1

    def test_empty_text_repealed_chunk_does_not_fail_length_readiness(
        self,
        tmp_path: Path,
    ) -> None:
        report = self._validate(
            tmp_path,
            "length_empty_repealed.jsonl",
            [
                self._chunk(
                    text="   ",
                    metadata=ChunkingMetadata(
                        is_empty_or_repealed=True,
                        is_source_unit_repealed=True,
                    ),
                )
            ],
        )

        assert report.text_length_summary["empty_text_count"] == 1
        assert report.errors_total == 0
        assert all(
            issue.code != ProcessedJsonlValidationIssueCode.EMPTY_TEXT_FOUND
            for issue in report.sample_failures
        )

    def test_short_text_warns_only(self, tmp_path: Path) -> None:
        report = self._validate(
            tmp_path,
            "length_short.jsonl",
            [self._chunk(text="Nội dung ngắn nhưng hợp lệ.")],
        )

        assert report.text_length_summary["short_text_warning_count"] == 1
        assert report.status == "pass_with_warnings"
        assert report.invalid_chunks == 0

    def test_long_text_warns_only(self, tmp_path: Path) -> None:
        report = self._validate(
            tmp_path,
            "length_long_text.jsonl",
            [self._chunk(text="x" * 4001)],
        )

        assert report.text_length_summary["long_text_warning_count"] == 1
        assert report.status == "pass_with_warnings"
        assert report.invalid_chunks == 0

    def test_empty_parent_text_warns_only(self, tmp_path: Path) -> None:
        report = self._validate(
            tmp_path,
            "length_empty_parent.jsonl",
            [self._chunk(parent_text="   ")],
        )

        assert report.parent_text_length_summary["empty_parent_text_count"] == 1
        assert report.status == "pass_with_warnings"
        assert report.invalid_chunks == 0

    def test_long_parent_text_warns_only(self, tmp_path: Path) -> None:
        report = self._validate(
            tmp_path,
            "length_long_parent.jsonl",
            [self._chunk(parent_text="p" * 151)],
            parent_text_long_chars=100,
            parent_text_very_long_chars=200,
        )

        assert report.parent_text_length_summary["long_parent_text_warning_count"] == 1
        assert report.status == "pass_with_warnings"
        assert report.invalid_chunks == 0
        assert (
            report.sample_warnings[0].code
            == ProcessedJsonlValidationIssueCode.VERY_LONG_PARENT_TEXT
        )

    def test_extreme_parent_text_counted(self, tmp_path: Path) -> None:
        report = self._validate(
            tmp_path,
            "length_extreme_parent.jsonl",
            [self._chunk(parent_text="p" * 251)],
            parent_text_long_chars=100,
            parent_text_very_long_chars=200,
        )

        summary = report.parent_text_length_summary
        assert summary["long_parent_text_warning_count"] == 1
        assert summary["extreme_parent_text_warning_count"] == 1
        assert report.long_parent_text_summary["extreme_count"] == 1

    def test_long_parent_text_summary_top_examples_limited(self, tmp_path: Path) -> None:
        chunks = [
            self._chunk(
                chunk_id=f"long_parent_{index}",
                parent_text="p" * (200 + index),
            )
            for index in range(8)
        ]
        report = self._validate(
            tmp_path,
            "length_parent_examples.jsonl",
            chunks,
            parent_text_long_chars=100,
            parent_text_very_long_chars=500,
        )

        examples = report.long_parent_text_summary["top_examples"]
        assert len(examples) == 5
        assert examples[0]["parent_text_chars"] == 207

    def test_length_warnings_do_not_mutate_validity_when_no_errors(
        self,
        tmp_path: Path,
    ) -> None:
        report = self._validate(
            tmp_path,
            "length_warning_validity.jsonl",
            [self._chunk(text="Nội dung ngắn.")],
        )

        assert report.warnings_total == 1
        assert report.status == "pass_with_warnings"
        assert report.valid_chunks == 1
        assert report.invalid_chunks == 0


# ---------------------------------------------------------------------------
# Slice 3H: Payload readiness tests
# ---------------------------------------------------------------------------


class TestPayloadReadiness:
    """Vector payload completeness for filtering, citation, and traceability."""

    def _validate_rows(
        self,
        tmp_path: Path,
        filename: str,
        rows: list[dict[str, object]],
    ) -> ProcessedJsonlValidationReport:
        jsonl_path = tmp_path / filename
        _write_raw_jsonl(jsonl_path, rows)
        return ProcessedJsonlValidator(_config(jsonl_path)).validate(jsonl_path)

    def test_payload_summary_populated_for_ready_chunk(self, tmp_path: Path) -> None:
        row = _valid_chunk().model_dump(mode="json")
        report = self._validate_rows(tmp_path, "payload_ready.jsonl", [row])

        summary = report.payload_readiness_summary
        assert summary["checked_chunks"] == 1
        assert summary["ready_chunks"] == 1
        assert summary["not_ready_chunks"] == 0
        assert summary["payload_failure_chunks"] == 0

    def test_ready_rate_computed(self, tmp_path: Path) -> None:
        rows = [
            _valid_chunk(chunk_id="payload_1").model_dump(mode="json"),
            _valid_chunk(chunk_id="payload_2").model_dump(mode="json"),
        ]
        report = self._validate_rows(tmp_path, "payload_rate.jsonl", rows)

        assert report.payload_readiness_summary["ready_rate"] == 1.0

    def test_missing_required_payload_field_counted(self, tmp_path: Path) -> None:
        row = _valid_chunk().model_dump(mode="json")
        del row["source_node_id"]
        report = self._validate_rows(tmp_path, "payload_missing_required.jsonl", [row])

        summary = report.payload_readiness_summary
        assert summary["missing_required_field_counts"]["source_node_id"] == 1
        assert summary["payload_failure_chunks"] == 1
        assert summary["not_ready_chunks"] == 1
        assert report.errors_total == 1

    def test_empty_required_payload_field_counted(self, tmp_path: Path) -> None:
        row = _valid_chunk().model_dump(mode="json")
        row["hierarchy_path"] = ""
        report = self._validate_rows(tmp_path, "payload_empty_required.jsonl", [row])

        summary = report.payload_readiness_summary
        assert summary["empty_required_field_counts"]["hierarchy_path"] == 1
        assert summary["payload_failure_chunks"] == 1
        assert report.invalid_chunks == 1
        assert (
            next(
                issue
                for issue in report.sample_failures
                if issue.code == ProcessedJsonlValidationIssueCode.PAYLOAD_FIELD_MISSING
            ).context["failures"][0]["field"]
            == "hierarchy_path"
        )

    def test_article_level_requires_article_number(self, tmp_path: Path) -> None:
        row = _valid_chunk().model_dump(mode="json")
        row["article_number"] = None
        report = self._validate_rows(tmp_path, "payload_article_number.jsonl", [row])

        assert (
            report.payload_readiness_summary["missing_conditional_field_counts"]["article_number"]
            == 1
        )
        assert report.payload_readiness_summary["payload_failure_chunks"] == 1

    def test_clause_level_requires_article_and_clause_number(self, tmp_path: Path) -> None:
        row = _valid_chunk(
            level=ChunkingLevel.CLAUSE,
            chunk_kind="clause_level",
            clause_number="2",
            citation="Luật thử nghiệm, Khoản 2, Điều 1",
        ).model_dump(mode="json")
        row["clause_number"] = None
        report = self._validate_rows(tmp_path, "payload_clause_number.jsonl", [row])

        assert (
            report.payload_readiness_summary["missing_conditional_field_counts"]["clause_number"]
            == 1
        )
        assert report.payload_readiness_summary["payload_failure_chunks"] == 1

    def test_point_level_requires_article_clause_point(self, tmp_path: Path) -> None:
        row = _valid_chunk(
            level=ChunkingLevel.POINT,
            chunk_kind="point_level",
            clause_number="2",
            point_label="a",
            citation="Luật thử nghiệm, Điểm a, Khoản 2, Điều 1",
        ).model_dump(mode="json")
        row["point_label"] = None
        report = self._validate_rows(tmp_path, "payload_point_label.jsonl", [row])

        assert (
            report.payload_readiness_summary["missing_conditional_field_counts"]["point_label"] == 1
        )
        assert report.payload_readiness_summary["payload_failure_chunks"] == 1

    def test_missing_recommended_metadata_warns_only(self, tmp_path: Path) -> None:
        row = _valid_chunk().model_dump(mode="json")
        del row["metadata"]["is_empty_or_repealed"]
        report = self._validate_rows(tmp_path, "payload_metadata_warning.jsonl", [row])

        summary = report.payload_readiness_summary
        assert summary["missing_recommended_metadata_counts"]["is_empty_or_repealed"] == 1
        assert summary["payload_warning_chunks"] == 1
        assert summary["ready_chunks"] == 1
        assert report.invalid_chunks == 0

    def test_payload_failure_counts_once_per_chunk(self, tmp_path: Path) -> None:
        row = _valid_chunk().model_dump(mode="json")
        row["hierarchy_path"] = ""
        row["text_hash"] = ""
        report = self._validate_rows(tmp_path, "payload_multiple_failures.jsonl", [row])

        summary = report.payload_readiness_summary
        assert summary["payload_failure_chunks"] == 1
        assert summary["empty_required_field_counts"]["hierarchy_path"] == 1
        assert summary["empty_required_field_counts"]["text_hash"] == 1
        assert report.errors_total == 1

    def test_payload_warning_counts_once_per_chunk(self, tmp_path: Path) -> None:
        row = _valid_chunk().model_dump(mode="json")
        del row["metadata"]["is_empty_or_repealed"]
        del row["metadata"]["is_source_unit_repealed"]
        report = self._validate_rows(tmp_path, "payload_multiple_warnings.jsonl", [row])

        summary = report.payload_readiness_summary
        assert summary["payload_warning_chunks"] == 1
        assert sum(summary["missing_recommended_metadata_counts"].values()) == 2

    def test_payload_summary_aggregates_multiple_chunks(self, tmp_path: Path) -> None:
        ready = _valid_chunk(chunk_id="payload_ready").model_dump(mode="json")
        warning = _valid_chunk(chunk_id="payload_warning").model_dump(mode="json")
        del warning["metadata"]["is_empty_or_repealed"]
        not_ready = _valid_chunk(chunk_id="payload_not_ready").model_dump(mode="json")
        not_ready["hierarchy_path"] = ""

        report = self._validate_rows(
            tmp_path,
            "payload_mixed.jsonl",
            [ready, warning, not_ready],
        )

        summary = report.payload_readiness_summary
        assert summary["checked_chunks"] == 3
        assert summary["ready_chunks"] == 2
        assert summary["not_ready_chunks"] == 1
        assert summary["payload_failure_chunks"] == 1
        assert summary["payload_warning_chunks"] == 1
        assert summary["ready_rate"] == 0.6667


# ---------------------------------------------------------------------------
# Slice 3H scope: later checks are not yet implemented
# ---------------------------------------------------------------------------


class TestSlice3HScope:
    """Slice 3H audits payload readiness; final embedding checks stay neutral."""

    def test_count_reconciliation_passes_with_matching_report(self, tmp_path: Path) -> None:
        """Count reconciliation remains neutral when the report matches."""
        chunk = _valid_chunk(chunk_id="c1")
        jsonl_path = tmp_path / "recon.jsonl"
        _write_jsonl(jsonl_path, [chunk])

        validator = ProcessedJsonlValidator(_config(jsonl_path))
        report = validator.validate(jsonl_path)

        assert report.count_reconciliation_failures == 0
        assert report.status == "pass"

    def test_hierarchy_traceability_passes_with_matching_hierarchy(
        self,
        tmp_path: Path,
    ) -> None:
        """Matching hierarchy fixtures keep traceability counters neutral."""
        chunk = _valid_chunk(chunk_id="c1")
        jsonl_path = tmp_path / "hier.jsonl"
        _write_jsonl(jsonl_path, [chunk])

        validator = ProcessedJsonlValidator(_config(jsonl_path))
        report = validator.validate(jsonl_path)

        assert report.traceability_failures == 0
        assert report.traceability_checks_skipped is False

    def test_later_slice_fields_are_neutral(self, tmp_path: Path) -> None:
        """Fields for later slices are set to neutral values."""
        chunk = _valid_chunk(chunk_id="c1")
        jsonl_path = tmp_path / "neutral.jsonl"
        _write_jsonl(jsonl_path, [chunk])

        validator = ProcessedJsonlValidator(_config(jsonl_path))
        report = validator.validate(jsonl_path)

        assert report.count_reconciliation_failures == 0
        assert report.citation_failures == 0
        assert report.traceability_failures == 0
        assert report.contamination_failures == 0
        assert report.contamination_warnings == 0
        assert report.text_length_summary["count"] == 1
        assert report.parent_text_length_summary["count"] == 1
        assert report.long_parent_text_summary["long_count"] == 0
        assert report.repealed_metadata_summary["metadata_mismatch_failure_count"] == 0
        assert report.repealed_metadata_summary["metadata_mismatch_warning_count"] == 0
        assert report.payload_readiness_summary["checked_chunks"] == 1
        assert report.payload_readiness_summary["ready_chunks"] == 1
        assert report.payload_readiness_summary["not_ready_chunks"] == 0
        assert report.embedding_readiness == {}
