# Parent-child Chunking Pipeline

## Overview

Phase 6 transforms validated legal hierarchy artifacts into deterministic
parent-child chunks. It preserves Vietnamese legal hierarchy and citation
traceability without arbitrary token or character windows.

The implementation uses:

- child unit for embedding: Article, Clause, or Point according to hierarchy;
- parent context for generation: full Article text in `parent_text`;
- one corpus-level JSONL output: `data/processed/legal_chunks.jsonl`;
- one report: `artifacts/reports/chunking/chunking_report.json`.

Phase 6 does not embed, index, retrieve, generate answers, or implement RAG.

## Status

Phase 6 is complete and validated.

```text
Input laws:              52
Successful laws:         52
Failed laws:             0
Total chunks:            40,389
Article chunks:          1,322
Clause chunks:           20,643
Point chunks:            18,424
Duplicate chunk_id:      0
Bad JSONL lines:         0
Selection-rule issues:   0
Chunk invariant issues:  0
```

Validation audit:

```text
artifacts/reports/chunking/full_corpus_validation_report.json
```

## Official Command

```bash
uv run python scripts/chunk_legal_corpus.py \
  --input-dir data/interim \
  --output data/processed/legal_chunks.jsonl \
  --report artifacts/reports/chunking/chunking_report.json \
  --overwrite \
  --verbose \
  --no-color
```

Useful priority-audit command:

```bash
uv run python scripts/chunk_legal_corpus.py \
  --input-dir data/interim \
  --output artifacts/runs/chunking/priority/legal_chunks.jsonl \
  --report artifacts/reports/chunking/priority_chunking_report.json \
  --law-ids BLDS_2015 BLHS_VBHN LDD_VBHN LTTHC LVL_2025 LANM_2025 LHNGD_VBHN LTATGT_VBHN \
  --overwrite \
  --verbose \
  --no-color
```

## Inputs and Outputs

Input:

```text
data/interim/{LAW_ID}/hierarchy.json
```

Outputs:

```text
data/processed/legal_chunks.jsonl
artifacts/reports/chunking/chunking_report.json
```

Audit artifacts:

```text
artifacts/reports/chunking/priority_audit.json
artifacts/reports/chunking/full_corpus_validation_report.json
artifacts/runs/chunking/priority/legal_chunks.jsonl
```

## Implemented Components

```text
src/processing/legal_chunk_models.py
src/processing/legal_chunker.py
src/processing/legal_chunk_validator.py
src/services/chunking_service.py
scripts/chunk_legal_corpus.py
```

Tests:

```text
tests/unit/processing/test_legal_chunk_models.py
tests/unit/processing/test_legal_chunker.py
tests/unit/processing/test_legal_chunk_validator.py
tests/unit/services/test_chunking_service.py
tests/unit/services/test_chunk_legal_corpus_cli.py
```

## Chunk Selection Rules

For each Article in source order:

1. Article without Clause children:
   - create one article-level chunk;
   - `text = Article.text`;
   - `parent_text = Article.text`.
2. Clause without Point children:
   - create one clause-level chunk;
   - `text = Clause.text`;
   - `parent_text = parent Article.text`.
3. Clause with Point children:
   - create one point-level chunk per Point;
   - `text = Point.text`;
   - `parent_text = parent Article.text`.

The chunker does not create synthetic Clause or Point nodes. It does not chunk
Law, Part, Chapter, or Section nodes.

## Canonical Chunk Fields

Each JSONL row is a `LegalChunk` with these key fields:

```text
schema_version
chunker_version
chunk_id
law_id
law_name
source_url
source_domain
source_type
source_file
level
chunk_kind
source_node_id
parent_article_node_id
parent_chunk_id
article_number
article_title
clause_number
point_label
citation
hierarchy_path
text
parent_text
start_offset
end_offset
article_start_offset
article_end_offset
text_hash
parent_text_hash
metadata
warnings
```

`text` is the future embedding unit. `parent_text` is the full Article context
for retrieval/generation payloads.

## Deterministic IDs

Chunk IDs are derived from Phase 5 `LegalNode.node_id` and preserve
collision-resolved suffixes:

```text
chunk_id = "{source_node_id}__chunk"
parent_chunk_id = "{article_node_id}__parent"
```

Example:

```text
BLDS_2015__root__article_1__clause_1__point_a__chunk
BLDS_2015__root__article_1__parent
```

Do not reconstruct IDs from displayed Article/Clause/Point numbers.

## Citation Format

Citations are Vietnamese and legally meaningful:

```text
{Law Name}, Điều {article_number}
{Law Name}, Khoản {clause_number}, Điều {article_number}
{Law Name}, Điểm {point_label}, Khoản {clause_number}, Điều {article_number}
```

Examples from validated output:

```text
Bộ luật Dân sự 2015, Điều 1
Bộ luật Dân sự 2015, Khoản 1, Điều 2
Bộ luật Dân sự 2015, Điểm a, Khoản 1, Điều 27
```

## Validation Rules

Full-corpus validation checks:

- every JSONL line parses;
- `chunk_id` is unique;
- `source_node_id` exists in the hierarchy;
- `parent_article_node_id` exists and is an Article;
- `text` equals the source node text;
- `parent_text` equals the parent Article text;
- child offsets are inside Article offsets;
- source offsets match hierarchy offsets;
- SHA-256 hashes match `text` and `parent_text`;
- selection rules match the hierarchy exactly;
- no Law/Part/Chapter/Section chunks exist;
- report counts match JSONL line counts and grouped counts.

## Long Parent Text Caveat

Phase 6 intentionally keeps the full Article parent context. The full corpus has
570 chunks with `parent_text` longer than 8,000 characters; max parent context is
58,955 characters.

This is not a Phase 6 defect. Phase 7/8 must handle long parent contexts during
embedding-readiness checks, payload design, retrieval, and prompt context
packing. Do not split Article parent text in Phase 6 using arbitrary character
or token windows.

## Next Phase

Next phase:

```text
Phase 7 — Processed JSONL Validation / embedding-readiness checks
```

Phase 8 embedding/indexing should embed `text` only and keep `parent_text` as
retrieval/LLM context payload.
