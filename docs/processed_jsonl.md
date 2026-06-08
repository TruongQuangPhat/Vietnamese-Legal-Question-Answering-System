# Processed JSONL Validation

## Overview

Phase 7 validates the Phase 6 corpus-level JSONL output before embedding and
indexing. Phase 6 already writes the processed chunk file:

```text
data/processed/legal_chunks.jsonl
```

Phase 7 should treat that file as the canonical chunk corpus and verify that it
is safe for embedding/indexing. It should not recrawl, reclean, reparse, or
rechunk legal text unless a proven upstream blocker is separately approved.

## Current Input

Validated Phase 6 output:

```text
data/processed/legal_chunks.jsonl
artifacts/reports/chunking/chunking_report.json
artifacts/reports/chunking/full_corpus_validation_report.json
```

Phase 6 validation result:

```text
Laws:                    52
Chunks:                  40,389
Success with warnings:   18
Failed laws:             0
Empty/repealed chunks:   180
Source-tail markers:     0 in text, 0 in parent_text
Max parent_text length:  14,481 chars
Bad JSONL lines:         0
Duplicate chunk_id:      0
Selection-rule issues:   0
Chunk invariant issues:  0
```

## Validation Goals

Phase 7 should confirm:

- every JSONL line parses;
- every row validates as `LegalChunk`;
- all required fields are present;
- `chunk_id` is globally unique;
- report counts match JSONL counts;
- `text_hash` and `parent_text_hash` are correct;
- citations are non-empty and Vietnamese;
- `source_node_id` and `parent_article_node_id` remain traceable;
- `text` is the intended embedding content;
- `parent_text` is retained as Article context;
- long Article parent contexts are measured and classified for downstream
  context packing;
- no raw HTML, source-note tail, or generated legal content is introduced.

## Expected Phase 7 Output

Recommended report path:

```text
artifacts/reports/chunking/processed_jsonl_validation_report.json
```

Recommended report fields:

```text
schema_version
started_at
finished_at
duration_seconds
input_path
chunking_report_path
total_lines
valid_chunks
invalid_chunks
duplicate_chunk_ids
chunks_by_level
chunks_by_law
required_field_failures
hash_mismatches
citation_failures
long_parent_text_summary
warnings
errors
```

Phase 7 may also write diagnostic artifacts under:

```text
artifacts/runs/phase7_processed_jsonl_validation/
```

## Embedding-readiness Rules

Phase 8 embedding/indexing should use:

```text
embedding input: text
retrieval payload/context: parent_text
```

Do not embed `parent_text` as the primary vector text. `parent_text` can be very
long and is meant for downstream LLM context once a child chunk has been
retrieved.

The current Phase 6 hardening audit has:

```text
source-tail markers in text:        0
source-tail markers in parent_text: 0
max parent_text:                    14,481 chars
parent_text > 20,000 chars:         0 chunks
```

Phase 6 preserves whole Article context. Phase 7/8 should design payload
storage and context packing deliberately instead of splitting legal text
arbitrarily.

## Non-goals

Phase 7 should not implement:

- embedding;
- Qdrant collections;
- BM25 or sparse retrieval;
- reranking;
- Naive RAG;
- Advanced RAG;
- GraphRAG;
- API/backend;
- LLM generation.

## Useful Commands

Run the official Phase 6 chunking command before validating if outputs need to
be regenerated:

```bash
uv run python scripts/chunk_legal_corpus.py \
  --input-dir data/interim \
  --output data/processed/legal_chunks.jsonl \
  --report artifacts/reports/chunking/chunking_report.json \
  --overwrite \
  --verbose \
  --no-color
```

Basic quantity check:

```bash
uv run python -c "import json; from pathlib import Path; p=Path('data/processed/legal_chunks.jsonl'); print(sum(1 for _ in p.open(encoding='utf-8')))"
```
