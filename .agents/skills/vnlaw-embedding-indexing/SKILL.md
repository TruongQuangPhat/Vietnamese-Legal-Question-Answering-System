---
name: vnlaw-embedding-indexing
description: Use for embedding legal chunks, BGE-M3 dense/sparse representations, Qdrant collection setup, vector payload design, indexing verification, and embedding configuration.
---

# Embedding and Vector Indexing Skill

Use this skill for embedding legal chunks and indexing them into Qdrant.

This skill should be used only after processed JSONL chunks already validate
against the Phase 6 `LegalChunk` schema.

Current project status: Phase 6 Parent-child Chunking is complete and validated
with `data/processed/legal_chunks.jsonl` containing 40,389 chunks, 0 failed
laws, 0 source-tail markers in `text`/`parent_text`, and 180 empty/repealed
chunks flagged. Phase 7 Processed JSONL Validation / embedding-readiness checks
is next. Do not create embedding/indexing code until the Phase 7 validation
gate passes.

## Goal

Convert validated legal chunks into searchable dense and sparse vector representations while preserving all legal metadata required for citation, filtering, and retrieval.

```text
data/processed/legal_chunks.jsonl
  → validate LegalChunk rows
  → embed chunk.text
  → upsert dense/sparse vectors
  → store legal metadata and parent_text payload
  → verify point count and filters
```

## Expected Future Files

```text
src/indexing/embedder.py
src/indexing/vector_store.py
src/core/config.py
configs/models.yml
configs/retrieval.yml
data/processed/legal_chunks.jsonl
tests/unit/indexing/test_embedder.py
tests/unit/indexing/test_vector_store.py
```

## Embedding Strategy

Use an embedding model capable of both dense and sparse representations, such as a BGE-M3-style model.

Requirements:

- dense vectors for semantic retrieval;
- sparse lexical weights for exact legal term matching;
- batch embedding;
- deterministic configuration;
- metadata-preserving payload;
- reproducible model config in `configs/models.yml`.

Do not embed arbitrary raw HTML, `parent_text`, or unvalidated text.

## Qdrant Collection

Use named vectors:

```text
dense
sparse
```

Expected dense dimension for BGE-M3-style embeddings:

```text
1024
```

Use cosine distance for dense vectors unless the model documentation requires otherwise.

Collection and vector settings must live in configuration files, not scattered across the codebase.

## Payload Requirements

Every indexed point must preserve:

```text
chunk_id
law_id
law_name
year
effective_date
expiry_date
status
domain_tags
article_id
clause_id
point_id
hierarchy_text
text
parent_text
cross_references
source_url
crawled_at
parser_version
```

Payloads must support filtering by:

```text
law_id
status
effective_date
expiry_date
domain_tags
```

## OOP and Docstring Rules

Expected components:

```text
BaseEmbedder
BGEEmbedder
EmbeddingBatcher
VectorStore
QdrantVectorStore
IndexingService
```

Rules:

- Use typed models for embedding input/output.
- Keep embedding logic separate from vector database upsert logic.
- Public classes/functions must have Google-style docstrings.
- Docstrings must explain model assumptions, vector dimensions, batch behavior, and failure modes.

## Verification

After indexing, verify:

- point count equals number of processed chunks;
- required payload fields are present;
- filters work for `law_id`, `status`, `effective_date`, and `domain_tags`;
- search results include hierarchy, source URL, and parent context;
- no chunks without legal hierarchy were indexed.

## Do Not

- Do not embed `parent_text` as the primary vector text.
- Do not drop `parent_text` from retrieval/generation context payload.
- Do not index chunks without hierarchy metadata.
- Do not hardcode collection settings in multiple files.
- Do not upsert invalid `LegalChunk` records.
- Do not lose source traceability during indexing.
