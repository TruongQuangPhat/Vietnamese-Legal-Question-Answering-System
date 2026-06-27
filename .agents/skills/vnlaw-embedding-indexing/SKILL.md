---
name: vnlaw-embedding-indexing
description: Use for embedding validated legal chunks, BGE-M3 dense vectors, Qdrant collection setup, vector payload design, indexing verification, and embedding/indexing maintenance.
---

# Embedding and Vector Indexing Skill

Use this skill when maintaining, reviewing, or debugging legal chunk embedding and Qdrant dense indexing.

This skill should be used only after processed JSONL chunks have passed validation.

## Current Status

Embedding and dense indexing are implemented for the current corpus.

Current index state:

```text
processed chunks = 40,389
embedding model = BAAI/bge-m3
Qdrant collection = vnlaw_chunks_bgem3_v1_full
named vector = dense
dimension = 1024
distance = cosine
indexed points = 40,389
```

The current adopted retrieval system uses BGE-M3 dense retrieval plus BM25 sparse retrieval, followed by RRF and coverage-aware quota retrieval. Sparse BM25 retrieval is not represented as a Qdrant sparse named vector in the final adopted pipeline.

Do not re-embed, re-index, recreate, delete, or upsert Qdrant collections unless the user explicitly scopes that operation.

Protected paths include:

```text
data/raw/**
data/interim/**
data/reports/**
data/processed/legal_chunks.jsonl
artifacts/reports/evaluation/**
```

## Goal

Convert validated legal chunks into searchable dense vectors while preserving legal metadata required for retrieval, evidence selection, citation, and generation.

```text
data/processed/legal_chunks.jsonl
  → validate processed chunks
  → embed chunk text
  → upsert dense vectors into Qdrant
  → store legal metadata and auxiliary parent context payload
  → verify point count and payload contract
```

Sparse/BM25 retrieval should be handled separately from Qdrant dense indexing unless a task explicitly scopes a new sparse-vector indexing experiment.

## Relevant Files and Components

Use the repository’s current structure. Relevant files may include:

```text
src/indexing/
src/services/
scripts/indexing/
configs/models.yml
configs/retrieval.yml
data/processed/legal_chunks.jsonl
tests/unit/indexing/
tests/integration/retrieval/
```

Do not create new indexing abstractions unless the task requires them.

## Validation Before Indexing

Before any real indexing task, validate the processed JSONL input:

```bash
uv run python scripts/corpus/validate_processed_jsonl.py \
  --input data/processed/legal_chunks.jsonl \
  --config configs/processing/processed_jsonl_validation.yml \
  --output /tmp/processed_jsonl_validation_report.json \
  --pretty
```

This command reads the protected processed JSONL file. Do not run commands that modify protected data unless explicitly scoped.

## Embedding Strategy

Requirements:

* embed only validated child chunk text as the primary vector text;
* use deterministic model/config settings;
* preserve metadata required for retrieval and citation;
* batch embedding safely;
* keep model configuration reproducible;
* avoid embedding raw HTML, unvalidated text, or auxiliary parent context as the primary vector text.

Parent context should remain available in payload for generation/context support, but the primary dense vector should represent the citable child chunk.

## Qdrant Collection

Use the current dense vector contract:

```text
collection = vnlaw_chunks_bgem3_v1_full
vector name = dense
dimension = 1024
distance = cosine
```

Collection and vector settings should live in configuration files or centralized config objects, not scattered across the codebase.

## Payload Requirements

Every indexed point should preserve citation and legal traceability metadata such as:

```text
chunk_id
law_id
law_name
year
status
article_id
clause_id
point_id
hierarchy_text
text or child_text
parent_text or auxiliary parent context
source_url
citation
cross_references
parser_version
chunker_version
content_hash
```

Payloads should support filtering or downstream selection by stable legal metadata such as:

```text
law_id
status
article_id
clause_id
point_id
domain_tags if available
```

Do not drop source URL, citation, law ID, hierarchy, or parent context fields during indexing.

## OOP and Docstring Rules

Expected components may include:

```text
BaseEmbedder
BGEEmbedder
EmbeddingBatcher
QdrantVectorStore
IndexingService
IndexingReport
```

Rules:

* Use typed models for embedding input/output.
* Keep embedding logic separate from vector database upsert logic.
* Public classes/functions must have Google-style docstrings where project style requires it.
* Docstrings must explain model assumptions, vector dimensions, batch behavior, payload preservation, and failure modes.

## Verification

After a real indexing task, verify:

* Qdrant point count equals the number of valid processed chunks;
* named vector `dense` exists and has dimension 1024;
* required payload fields are present;
* search results include hierarchy, source URL, citation, child text, and auxiliary parent context;
* duplicate text chunks keep distinct IDs/citations when legally distinct;
* warning metadata and repeal/status flags remain visible where available.

Use read-only verification unless the task explicitly scopes index mutation.

## Testing Guidance

Prefer tests with fake embedding models and fake Qdrant clients.

Integration tests should use tiny fixtures and `tmp_path`, not the full corpus or real Qdrant, unless explicitly scoped.

Current workflow-level retrieval integration tests exist under:

```text
tests/integration/retrieval/
```

## Official Reports

If an indexing task is explicitly scoped, write user-facing indexing reports under:

```text
artifacts/reports/indexing/<run_id>/
```

Use functional report fields such as:

```text
report_type
run_type
indexing_strategy
collection_name
vector_name
embedding_model
point_count
payload_ready_rate
```

Do not expose internal roadmap labels or historical phase labels in official report schemas.

Treat checkpoints as runtime/resume artifacts rather than user-facing reports by default.

## Do Not

* Do not embed `parent_text` as the primary vector text.
* Do not drop parent context from retrieval/generation payload.
* Do not upsert invalid processed chunks.
* Do not lose source traceability during indexing.
* Do not hardcode collection settings in multiple files.
* Do not commit Qdrant storage or model caches.
* Do not describe BM25 sparse retrieval as a Qdrant sparse named vector unless a separate sparse-vector indexing task is explicitly implemented.
* Do not re-embed, re-index, upsert, recreate, or delete Qdrant collections unless explicitly scoped.
* Do not modify protected corpus outputs unless explicitly scoped.
