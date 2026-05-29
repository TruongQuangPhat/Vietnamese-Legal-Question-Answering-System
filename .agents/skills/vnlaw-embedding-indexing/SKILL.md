---
name: vnlaw-embedding-indexing
description: Use for embedding legal chunks, BGE-M3 dense/sparse representations, Qdrant collection setup, vector payload design, indexing verification, and embedding configuration.
---

# Embedding and Vector Indexing Skill

Use this skill for embedding legal chunks and indexing them into Qdrant.

This skill should be used only after processed JSONL chunks already validate against the `LegalChunkNode` schema.

## Goal

Convert validated legal chunks into searchable dense and sparse vector representations while preserving all legal metadata required for citation, filtering, and retrieval.

```text
processed JSONL
  → validate LegalChunkNode
  → embed child content
  → upsert dense/sparse vectors
  → store metadata payload
  → verify point count and filters
```

## Expected Files

```text
src/ingestion/embedder.py
src/retrieval/vector_store.py
src/core/config.py
configs/models.yml
configs/retrieval.yml
data/processed/{law_id}.jsonl
tests/unit/ingestion/test_embedder.py
tests/unit/retrieval/test_vector_store.py
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

Do not embed arbitrary raw HTML or unvalidated text.

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
content
parent_content
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

- Do not embed only `parent_content`.
- Do not drop `parent_content` from payload.
- Do not index chunks without hierarchy metadata.
- Do not hardcode collection settings in multiple files.
- Do not upsert invalid `LegalChunkNode` records.
- Do not lose source traceability during indexing.