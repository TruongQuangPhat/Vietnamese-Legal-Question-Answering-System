# Parent-child Chunking Pipeline

## Overview

The Parent-child Chunking phase transforms the legal hierarchy tree into embedding-ready chunks while preserving citation integrity. The model uses **parent** units (full Điều) for LLM context and **child** units (Khoản or Điểm) for embedding and retrieval.

This design ensures that:
- Retrieved chunks are precise (specific Khoản/Điểm).
- LLM context contains the full Điều for interpretation.
- Citations remain traceable to exact legal provisions.
- Legal hierarchy is never broken by arbitrary character limits.

## Quick Start

**Intended CLI** (design phase, not yet implemented):

```bash
uv run python scripts/chunk_legal_corpus.py \
  --input-dir data/interim \
  --output-dir data/interim \
  --report artifacts/reports/chunking/chunking_report.json \
  --law-ids LDD_VBHN BLDS_2015
```

**Expected workflow**:
1. Input: `data/interim/{law_id}/hierarchy.json`
2. Output: `data/interim/{law_id}/chunks.jsonl` (one child chunk per line)
3. Chunks feed into JSONL validation and embedding.

## Architecture

```
┌──────────────────────┐
│  LegalDocumentNode   │
│  Tree                │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Article Parent      │
│  Builder             │
│  (extract full Điều) │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Clause/Point        │
│  Child Extractor     │
│  (embedding units)   │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Citation            │
│  Builder             │
│  (Vietnamese format) │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Metadata            │
│  Propagator          │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Chunk               │
│  Validator           │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Parent-child        │
│  Chunks (JSONL)      │
└──────────────────────┘
```

## Components

### 1. Article Parent Builder

**Goal**: Create parent units representing full Điều with metadata.

**Process**:
- For each `LegalNode` with `level="article"`:
  - `parent_id` = `{law_id}__article_{article_number}`
  - `parent_text` = node's full `text` (entire Điều including all Khoản and Điểm).
  - `article_title` = node's `title` (if present).
  - Inherit `law_id`, `law_name`, `law_type`, `legal_status` from registry metadata.
  - Store `source_url`, `source_domain`, `source_type` from crawler metadata.
  - Include date fields: `issued_date`, `effective_date`, `expiry_date`.

**Output**: In-memory parent cache keyed by `parent_id`.

### 2. Clause/Point Child Extractor

**Goal**: Create child chunks for embedding. Each child is either a Khoản or a Điểm.

**Rule**:
- Child unit must be a leaf node: `level="clause"` or `level="point"`.
- If an article has no clauses, the article itself becomes a child (rare; means article has direct text).
- Child `text` = node's `text` (only the specific clause/point content).

**Child chunk fields**:
- `chunk_id`: deterministic unique ID (see convention below)
- `level`: `"clause"` or `"point"` (or `"article"` if no child clauses)
- `article_number`: from node's parent article
- `article_title`: from parent article node
- `clause_number`: if level ≥ clause, else null
- `point_label`: if level = point, else null
- `text`: child content (embedding text)
- `parent_id`: reference to parent article's `parent_id`
- `parent_text`: full text of parent article (from parent cache)

### 3. Citation Builder

**Goal**: Construct Vietnamese legal citation string.

**Format**:
```
Luật {law_name}, Điều {article_number}, Khoản {clause_number}, Điểm {point_label}
```

Components:
- Omit `Khoản` if not present (article-level chunk).
- Omit `Điểm` if not present (clause-level chunk).
- Always include `Luật {law_name}` and `Điều {article_number}`.

**Examples**:
- `"Luật Đất đai (VBHN 2025), Điều 123, Khoản 2, Điểm c"`
- `"Luật Đất đai (VBHN 2025), Điều 123, Khoản 2"` (no point)
- `"Luật Đất đai (VBHN 2025), Điều 123"` (article-level only)

**Important**: Do NOT use English "Article/Clause/Point".

### 4. Metadata Propagator

**Goal**: Attach full traceability metadata to each chunk.

**Required fields**:
- `law_id`, `law_name`, `law_type`, `legal_status`
- `source_url`, `source_domain`, `source_type`
- `issued_date`, `effective_date`, `expiry_date`
- `text_hash`: SHA256 of `text` (for duplicate detection)
- `hierarchy_path`: object mapping each level to its display label (see schema)
- `metadata`: implementation metadata (`parser_version`, `chunker_version`, `raw_artifact_path`)

**hierarchy_path structure**:
```json
{
  "part": "Phần I" | null,
  "chapter": "Chương 1" | null,
  "section": "Mục 2" | null,
  "article": "Điều 123",
  "clause": "Khoản 2" | null,
  "point": "Điểm c" | null
}
```

Values are constructed from the node's number and the parent hierarchy.

### 5. Chunk Validator

**Goal**: Ensure each chunk is well-formed before export.

**Checks**:
- `chunk_id` is unique within the law.
- `text` is non-empty and not pure whitespace.
- `parent_id` exists in parent cache.
- `citation` follows Vietnamese format (regex: `r"Luật .+, Điều \d+"`).
- `hierarchy_path` correctly reflects node's level.
- `text_hash` matches computed SHA256.
- `source_url` present and valid URL format.

**Failure**: Log error with `chunk_id`, skip invalid chunk (do not write), continue processing others.

## Pipeline Execution Flow

1. Load `hierarchy.json` for a `law_id`.
2. Build parent cache: iterate all article-level nodes, store `parent_id → parent_text + metadata`.
3. For each node in tree with `level` in `["clause", "point"]` (or article-level if no children):
   - Determine `chunk_id` using convention.
   - Lookup parent article from hierarchy (walk up tree if needed).
   - Extract `parent_id`, `parent_text` from parent cache.
   - Build `hierarchy_path` from node's ancestry.
   - Compute `text_hash` (SHA256 of `text`).
   - Construct `citation` (Vietnamese format).
   - Propagate law-level metadata from registry.
4. Run Chunk Validator; if passes, yield chunk dict.
5. Write chunks as JSONL lines to `chunks.jsonl`.

## Data Models / Output Schema

### Chunk ID Convention

Pattern: `{law_id}__article_{article_number}__clause_{clause_number}__point_{point_label}`

- For clause-level chunk (no point): `{law_id}__article_{article_number}__clause_{clause_number}`
- For point-level chunk: include all three segments.
- For article-level chunk (no clauses): `{law_id}__article_{article_number}`

Examples:
- `LDD_VBHN__article_123__clause_2__point_c`
- `LDD_VBHN__article_123__clause_2`
- `LDD_VBHN__article_123`

### Canonical Chunk Schema

```json
{
  "chunk_id": "LDD_VBHN__article_123__clause_2__point_c",
  "law_id": "LDD_VBHN",
  "law_name": "Luật Đất đai (VBHN 2025)",
  "law_type": "law",
  "legal_status": "active",

  "level": "point",
  "article_number": "123",
  "article_title": "Điều 123. Tên điều luật",
  "clause_number": "2",
  "point_label": "c",

  "hierarchy_path": {
    "part": null,
    "chapter": "Chương I",
    "section": null,
    "article": "Điều 123",
    "clause": "Khoản 2",
    "point": "Điểm c"
  },

  "text": "Nội dung của Điểm c...",
  "parent_id": "LDD_VBHN__article_123",
  "parent_text": "Toàn bộ nội dung Điều 123...",

  "citation": "Luật Đất đai (VBHN 2025), Điều 123, Khoản 2, Điểm c",
  "source_url": "https://thuvienphapluat.vn/...",
  "source_domain": "thuvienphapluat.vn",
  "source_type": "html",

  "issued_date": "2024-01-18",
  "effective_date": "2025-01-01",
  "expiry_date": null,

  "text_hash": "sha256:abcd1234...",
  "metadata": {
    "parser_version": "v0.1",
    "chunker_version": "v0.1",
    "raw_artifact_path": "data/raw/LDD_VBHN/latest/main.html"
  }
}
```

### Why Not Arbitrary Character Chunking

Legal documents have semantic units (Điều, Khoản, Điểm). Splitting arbitrarily:
- Breaks citations (cannot point to exact clause).
- Loses legal hierarchy.
- Causes chunk boundary to cut in middle of a legal provision.
- Makes retrieval imprecise and generation unreliable.

Parent-child chunking respects legal structure and ensures every retrieved chunk is a complete, citable legal unit.

## CLI Reference

### Intended Commands

```bash
# Generate chunks for all laws
uv run python scripts/chunk_legal_corpus.py \
  --input-dir data/interim \
  --output-dir data/interim \
  --report artifacts/reports/chunking/chunking_report.json

# Specific laws with format options
uv run python scripts/chunk_legal_corpus.py \
  --law-ids LDD_VBHN \
  --input-dir data/interim \
  --output-dir data/interim \
  --output-format jsonl

# Validate existing chunks.jsonl
uv run python scripts/chunk_legal_corpus.py \
  --validate data/interim/LDD_VBHN/chunks.jsonl
```

## Testing

**Unit tests**:
- `test_chunk_id_generation()`: deterministic IDs follow pattern, unique within law.
- `test_citation_builder()`: Vietnamese format correct, omits absent levels.
- `test_parent_child_linkage()`: every child `parent_id` points to existing article parent.
- `test_text_hash_computation()`: SHA256 matches actual text.
- `test_hierarchy_path_builder()`: `hierarchy_path` correctly reflects ancestry.

**Integration test**:
- Given a `hierarchy.json` with at least 10 articles, `chunker` produces `chunks.jsonl` with all clause/point nodes as chunks.
- All chunks pass Chunk Validator.
- No duplicate `chunk_id`.
- Every chunk's `parent_text` contains its `text` (substring check).

## Error Handling

- **Missing parent article**: Should not happen if hierarchy is valid; log error and skip child.
- **Empty child text**: Skip chunk, log warning with `node_id`.
- **Hash computation failure**: Rare; retry or mark chunk invalid.
- **Metadata missing from registry**: Cannot proceed; raise `ConfigurationError` — check registry entry.

All errors include `law_id` and node identifier.

## Troubleshooting

| Issue | Possible Cause | How to Check | Recommended Fix |
|-------|----------------|--------------|-----------------|
| Chunk count too low | Parser missed clauses/points; or articles have no children | Count nodes in hierarchy.json vs chunks.jsonl | Verify parser detected all levels; check hierarchy tree completeness |
| Duplicate chunk_id | Node numbering conflict (same article/clause/point) | Find duplicate IDs in report | Ensure node_id generation includes full ancestry; disambiguate if needed |
| Citation format wrong | Citation builder used English labels | Inspect sample chunk | Fix to Vietnamese: "Luật ..., Điều ..., Khoản ..., Điểm ..." |
| parent_text does not contain text | Parent-child linkage incorrect | Substring check failed | Verify parent_id points to correct article; ensure article text includes child text |
| Missing source_url | Registry or metadata not propagated | Check chunk `source_url` | Ensure registry metadata loaded and attached to every chunk |
| text_hash mismatch | Hash computed on different string than stored | Recompute hash on chunk.text | Ensure hash is final field after all transformations; compute once |

## Best Practices

- **Deterministic IDs** — same input hierarchy must produce identical chunk IDs every run; essential for incremental updates.
- **Parent cache efficiency** — build once, reuse for all children of same article.
- **Stateless chunking** — chunker should not depend on previous runs; can rerun on same hierarchy to reproduce.
- **Validate before write** — reject invalid chunks; never write broken data to JSONL.
- **Keep parent_text full** — do not truncate; LLM needs full article context.
- **Metadata completeness** — every chunk must carry law-level metadata for downstream filtering and traceability.

## Changelog

### Version 0.1 (2026-05-21)

- Created initial parent-child chunking documentation.
- Defined parent (full Điều) and child (Khoản/Điểm) model.
- Specified chunk ID pattern, citation builder (Vietnamese format), metadata propagation.
- Introduced `hierarchy_path` for display hierarchy.
- Provided canonical chunk schema with all required fields.
- Explained why arbitrary character chunking is unsafe.
- Documented validation rules and testing strategy.

## Related Documentation

| Document | Status | Description |
|----------|--------|-------------|
| `docs/project_phase_journal.md` | Existing | Project phase journal and pipeline notes |
| `docs/project_setup.md` | Implemented | Environment setup and coding standards |
| `docs/corpus_registry.md` | Implemented | Corpus registry schema and design |
| `docs/raw_corpus_audit.md` | Designed | Raw artifact audit procedure |
| `docs/cleaning_normalization.md` | Existing | HTML-to-text and Unicode normalization |
| `docs/legal_parsing.md` | Existing | Legal hierarchy parsing algorithm |
| `docs/processed_jsonl.md` | Existing | JSONL export schema and validation |
