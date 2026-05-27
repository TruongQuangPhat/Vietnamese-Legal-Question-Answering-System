# Processed JSONL Export & Validation

## Overview

The Processed JSONL phase takes validated parent-child chunks and exports them to line-delimited JSON (JSONL) files, one per law. Before writing, the system validates schema correctness, detects duplicates, and ensures citation integrity. The resulting `data/processed/{law_id}.jsonl` files are the input to the embedding and indexing stages.

This phase acts as a quality gate: only chunks that pass all validation rules proceed to embedding.

## Quick Start

**Intended CLI** (design phase, not yet implemented):

```bash
uv run python -m src.processing.export_jsonl \
  --input-dir data/interim \
  --output-dir data/processed \
  --report-dir data/reports \
  --law-ids LDD_2024 BLDS_2015
```

**Expected workflow**:
1. Input: `data/interim/{law_id}/chunks.jsonl` (raw chunks from chunker)
2. Validation: schema, duplicates, citations, required fields
3. Output: `data/processed/{law_id}.jsonl` (validated chunks)
4. Report: `data/reports/processed_validation.json` (summary + errors)

## Architecture

```
┌──────────────────────┐
│  Parent-child        │
│  Chunks (raw)        │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Schema              │
│  Mapper               │
│  (Pydantic validate) │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Duplicate           │
│  Detector            │
│  (chunk_id, text)    │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Citation            │
│  Validator           │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  JSONL               │
│  Writer              │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Validation          │
│  Report              │
└──────────────────────┘
```

## Components

### 1. Schema Mapper

**Goal**: Ensure each chunk dict conforms to the canonical schema.

**Process**:
- Read each line from `chunks.jsonl`.
- Parse JSON → validate against Pydantic `ProcessedChunk` model (see schema below).
- If validation fails, record error with line number and validation errors; skip chunk.

**Required fields** (all mandatory unless noted):
- `chunk_id`, `law_id`, `law_name`, `law_type`, `legal_status`
- `level`, `article_number`, `article_title`, `clause_number` (nullable), `point_label` (nullable)
- `hierarchy_path` (object with part/chapter/section/article/clause/point keys)
- `text`, `parent_id`, `parent_text`
- `citation`, `source_url`, `source_domain`, `source_type`
- `issued_date`, `effective_date`, `expiry_date` (nullable)
- `text_hash`, `metadata` (dict)

**Failure**: `ValidationError` logged; chunk excluded from output.

### 2. Duplicate Detector

**Goal**: Prevent duplicate chunks from entering the corpus.

**Checks**:
- **Duplicate `chunk_id` within same law**: Two lines with same `chunk_id` → error.
- **Identical content**: Two chunks with same `(text, citation)` → warning (may indicate parser duplication).

**Action**:
- On first occurrence, keep chunk.
- On duplicate `chunk_id`, skip and record error with both line numbers.
- On identical `(text, citation)`, skip and record warning (less severe).

**Note**: `chunk_id` should be deterministic; duplicates indicate upstream bug in chunker.

### 3. Citation Validator

**Goal**: Ensure Vietnamese legal citation format is correct.

**Rules**:
- Must match regex: `r"^Luật .+, Điều \d+(, Khoản \d+(, Điểm [a-z])?)?$"`
- At minimum: "Luật ..., Điều N"
- Optional: ", Khoản N"
- Optional: ", Điểm X" after Khoản
- No English words ("Article", "Clause", "Point").

**Action**: Invalid citation → record error, skip chunk.

### 4. JSONL Writer

**Goal**: Write validated chunks to output file, one JSON object per line.

**Process**:
- Open `data/processed/{law_id}.jsonl` for writing (UTF-8).
- For each chunk that passes all checks, write `json.dumps(chunk, ensure_ascii=False) + "\n"`.
- Maintain line counter for error reporting.

**Performance**: Stream lines; do not load entire file into memory.

### 5. Validation Report Writer

**Goal**: Produce summary JSON with pass/fail statistics and error details.

**Output**: `data/reports/processed_validation.json`

Schema:
```json
{
  "law_id": "LDD_2024",
  "timestamp": "2025-01-01T12:00:00Z",
  "input_file": "data/interim/LDD_2024/chunks.jsonl",
  "output_file": "data/processed/LDD_2024.jsonl",
  "summary": {
    "total_input_chunks": 1500,
    "valid_chunks": 1498,
    "invalid_chunks": 2,
    "duplicate_chunk_id_errors": 0,
    "citation_errors": 1,
    "schema_errors": 1,
    "warnings": 1
  },
  "errors": [
    {
      "line": 42,
      "chunk_id": "LDD_2024__article_5__clause_2",
      "error_type": "schema_validation",
      "message": "field required: 'point_label'"
    },
    {
      "line": 150,
      "chunk_id": "LDD_2024__article_10__clause_1__point_a",
      "error_type": "citation_format",
      "message": "Citation must match Vietnamese format"
    }
  ],
  "warnings": [
    {
      "line": 999,
      "chunk_id": "LDD_2024__article_20__clause_1",
      "warning_type": "identical_content",
      "message": "Chunk text and citation identical to chunk LDD_2024__article_20__clause_2"
    }
  ]
}
```

## Pipeline Execution Flow

1. Read all `chunks.jsonl` files for the 52 laws (or specific `--law-ids`).
2. For each file:
   - Initialize counters and error lists.
   - Stream lines → parse JSON → validate schema.
   - Check for duplicate `chunk_id` (track seen IDs in set).
   - Validate citation format (regex).
   - Write valid chunks to `data/processed/{law_id}.jsonl`.
   - Accumulate errors and warnings.
3. After all files, write aggregate report `data/reports/processed_validation.json`.
4. Exit code:
   - `0` if all files have zero invalid chunks.
   - `1` if any invalid chunks found.
   - `2` on usage error or exception.

## Data Models / Output Schema

### Pydantic Model for Processed Chunk

```python
from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional

Level = Literal["article", "clause", "point"]

class HierarchyPath(BaseModel):
    part: Optional[str] = None
    chapter: Optional[str] = None
    section: Optional[str] = None
    article: str
    clause: Optional[str] = None
    point: Optional[str] = None

class ProcessedChunk(BaseModel):
    chunk_id: str
    law_id: str
    law_name: str
    law_type: str
    legal_status: str
    level: Level
    article_number: str
    article_title: str
    clause_number: Optional[str] = None
    point_label: Optional[str] = None
    hierarchy_path: HierarchyPath
    text: str
    parent_id: str
    parent_text: str
    citation: str
    source_url: str
    source_domain: str
    source_type: str
    issued_date: str  # YYYY-MM-DD
    effective_date: str  # YYYY-MM-DD
    expiry_date: Optional[str] = None  # YYYY-MM-DD or null
    text_hash: str
    metadata: dict = {}

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, v):
        assert v.strip(), "text must not be empty or whitespace only"
        return v

    @field_validator("citation")
    @classmethod
    def citation_format(cls, v):
        import re
        pattern = r"^Luật .+, Điều \d+(, Khoản \d+(, Điểm [a-z])?)?$"
        assert re.match(pattern, v), f"Citation '{v}' must match Vietnamese legal format"
        return v
```

### JSONL File Format

`data/processed/{law_id}.jsonl` contains one compact JSON object per line, UTF-8 encoded. Example:

```json
{"chunk_id":"LDD_2024__article_123__clause_2__point_c","law_id":"LDD_2024","law_name":"Luật Đất đai 2024","law_type":"law","legal_status":"active","level":"point","article_number":"123","article_title":"Điều 123. Tên điều luật","clause_number":"2","point_label":"c","hierarchy_path":{"part":null,"chapter":"Chương I","section":null,"article":"Điều 123","clause":"Khoản 2","point":"Điểm c"},"text":"Nội dung của Điểm c...","parent_id":"LDD_2024__article_123","parent_text":"Toàn bộ nội dung Điều 123...","citation":"Luật Đất đai 2024, Điều 123, Khoản 2, Điểm c","source_url":"https://thuvienphapluat.vn/...","source_domain":"thuvienphapluat.vn","source_type":"html","issued_date":"2024-01-18","effective_date":"2025-01-01","expiry_date":null,"text_hash":"sha256:abcd1234...","metadata":{"parser_version":"v0.1","chunker_version":"v0.1","raw_artifact_path":"data/raw/LDD_2024/latest/main.html"}}
{"chunk_id":"LDD_2024__article_123__clause_2","law_id":"LDD_2024",...}
```

### Validation Report Schema

See Architecture section above.

## CLI Reference

### Main Command

```bash
# Export and validate all laws
uv run python -m src.processing.export_jsonl \
  --input-dir data/interim \
  --output-dir data/processed \
  --report-dir data/reports

# Specific laws only
uv run python -m src.processing.export_jsonl \
  --law-ids LDD_2024 BLDS_2015 \
  --input-dir data/interim \
  --output-dir data/processed

# Check only (dry-run validation without writing)
uv run python -m src.processing.export_jsonl \
  --validate-only \
  --input-dir data/interim
```

**Arguments**:
- `--input-dir`: Directory containing `{law_id}/chunks.jsonl` (default: `data/interim`)
- `--output-dir`: Where to write `{law_id}.jsonl` (default: `data/processed`)
- `--report-dir`: Where to write `processed_validation.json` (default: `data/reports`)
- `--law-ids`: List of specific laws; if omitted, process all found in input dir.
- `--validate-only`: Run checks but do not write output files.

## Testing

**Unit tests**:
- `test_schema_validation()`: valid chunk passes Pydantic; missing required field fails.
- `test_duplicate_detection()`: duplicate `chunk_id` detected, first kept, second rejected.
- `test_citation_validator()`: Vietnamese format accepted, English format rejected.
- `test_text_hash()`: hash matches SHA256 of input text.
- `test_hierarchy_path_required()`: `hierarchy_path.article` must be present.

**Integration test**:
- Given a directory of `chunks.jsonl` files from chunker, `export_jsonl` produces 52 files in `data/processed/`.
- All output files contain only valid chunks; `processed_validation.json` reports `valid_chunks == total_input_chunks`.
- Run twice on same input → identical output files (deterministic).

## Error Handling

- **Schema validation failure**: Log error with line number, skip chunk, continue.
- **Duplicate chunk_id**: Log error with both line numbers, skip duplicate.
- **Citation invalid**: Log error, skip chunk.
- **I/O errors**: `FileNotFoundError`, `OSError` — abort processing for that law, log error, continue to next.
- **Report directory not writable**: Abort with exit code 2.

Aggregate error count determines exit code; partial success still writes valid chunks to output.

## Troubleshooting

| Issue | Possible Cause | How to Check | Recommended Fix |
|-------|----------------|--------------|-----------------|
| All chunks rejected | Schema mismatch (wrong fields) | Inspect first line of chunks.jsonl; compare to schema | Update chunker to produce canonical schema |
| Duplicate chunk_id errors | Chunker produced non-deterministic IDs | Check duplicate IDs in error report | Fix chunker ID generation to be deterministic and unique |
| Citation errors for all chunks | Citation builder used English format | Look at citation field in error sample | Switch to Vietnamese format: "Luật ..., Điều ..., Khoản ..., Điểm ..." |
| Missing `hierarchy_path` field | Chunker did not populate | Schema error says field required | Ensure chunker builds `hierarchy_path` from node ancestry |
| Output file empty | All chunks invalid or wrong input directory | Check `summary.valid_chunks` count | Fix upstream chunker; verify input dir path |
| Report not generated | Report directory not writable | Check `data/reports/` exists and is writable | Create directory or change `--report-dir` |
| Warnings about identical content | Parser produced duplicate clause/point nodes | Inspect warning `chunk_id` pairs | Verify parser hierarchy tree has no duplication |

## Best Practices

- **Fail fast on schema** — reject invalid chunks early; do not propagate bad data to embedding.
- **Track duplicates across entire law** — `chunk_id` uniqueness must hold per law; if duplicate found, it's a chunker bug.
- **Keep error details** — report should include line numbers and messages to debug upstream.
- **Deterministic output** — same input should produce byte-identical JSONL files.
- **Separate validation from writing** — consider `--validate-only` flag for CI quality gates.
- **Report as single source of truth** — downstream indexing should check report before loading embeddings.

## Changelog

### Version 0.1 (2026-05-21)

- Created initial JSONL export and validation documentation.
- Defined schema validation with Pydantic model (canonical chunk schema).
- Specified duplicate detection (chunk_id, identical content) and citation format validation.
- Provided validation report JSON structure with summary and error details.
- Documented CLI interface and testing strategy.
- Added troubleshooting for common export failures.

## Related Documentation

| Document | Status | Description |
|----------|--------|-------------|
| `docs/project_phase_journal.md` | Existing | Project phase journal and pipeline notes |
| `docs/project_setup.md` | Implemented | Environment setup and coding standards |
| `docs/corpus_registry.md` | Implemented | Corpus registry schema and design |
| `docs/raw_corpus_audit.md` | Designed | Raw artifact audit procedure |
| `docs/cleaning_normalization.md` | Existing | HTML-to-text and Unicode normalization |
| `docs/legal_parsing.md` | Existing | Legal hierarchy parsing algorithm |
| `docs/parent_child_chunking.md` | Existing | Parent-child chunking design |
| `docs/embedding_indexing.md` | Planned | Embedding model and Qdrant indexing |
