---
name: vnlaw-embedding-indexing
description: Use for embedding legal chunks, BGE-M3 dense/sparse representations, Qdrant collection setup, vector payload design, indexing verification, and embedding configuration.
allowed-tools: Read, Grep, Glob, LS, Bash, Edit, MultiEdit, Write
---

# Embedding and Vector Indexing Skill

Use this skill for embedding legal chunks and indexing them into Qdrant (Phase 8).

**Prerequisites**: Phases 0-6 are complete. Phase 7 processed JSONL validation
/ embedding-readiness checks must pass before indexing starts. The current
Phase 6 corpus is `data/processed/legal_chunks.jsonl` with 40,389 chunks.

## Goal

Convert validated legal chunks into searchable dense and sparse vector representations while preserving all legal metadata required for citation, filtering, and retrieval.

```text
data/processed/legal_chunks.jsonl
→ validate LegalChunk schema
→ embed chunk.text (dense + sparse)
→ upsert to Qdrant
→ store legal metadata and parent_text payload
→ verify point count and filters
```

## Embedding Strategy

Use an embedding model capable of both dense and sparse representations (e.g., BAAI/bge-m3).

Requirements:

- dense vectors for semantic retrieval;
- sparse lexical weights for exact legal term matching;
- batch embedding (batch size 32-64);
- deterministic configuration;
- metadata-preserving payload.

Do not embed arbitrary raw HTML, `parent_text`, or unvalidated text.

## Qdrant Collection

Use named vectors:

```text
dense
sparse
```

Expected dense dimension for BGE-M3-style embeddings: **1024**.

Use cosine distance for dense vectors.

## Payload Requirements

Every indexed point must preserve:

```text
chunk_id, law_id, law_name, law_type, legal_status
article_number, article_title, clause_number, point_label
hierarchy_path, citation
text (child content only)
parent_text (Article context payload, not the embedding input)
source_url, source_domain, source_type
effective_date, expiry_date, issued_date
text_hash, metadata
```

Payloads must support filtering by:

```text
law_id, legal_status, effective_date, law_type
```

Do not embed `parent_text` as the primary vector text. If payload storage keeps
`parent_text`, design long-context handling deliberately because Phase 6
preserves full Article context.

## OOP and Docstring Rules

Expected components:

```text
BaseEmbedder        # Protocol for embedding providers
BGEEmbedder         # BGE-M3 dense+sparse implementation
EmbeddingBatcher    # batched embedding with progress
VectorStore         # Qdrant collection + upsert operations
ChunkLoader         # async streaming chunk loader from JSONL
IndexingService     # end-to-end indexing orchestration
IndexingValidator   # post-indexing verification
```

Rules:

- Use typed models for embedding input/output.
- Keep embedding logic separate from vector database upsert logic.
- Use async I/O for all Qdrant operations.
- Public classes/functions must have Google-style docstrings.
- Docstrings must explain model assumptions, vector dimensions, batch behavior, and failure modes.

## Verification

After indexing, verify:

- point count equals number of processed chunks;
- required payload fields are present;
- filters work for `law_id`, `effective_date`, `legal_status`;
- search results include hierarchy, source URL, and citation;
- no chunks without legal hierarchy were indexed.

## Do Not

- Do not embed `parent_text` as the primary vector text.
- Do not drop `parent_text` from the retrieval context.
- Do not index chunks without hierarchy metadata.
- Do not hardcode collection settings in multiple files.
- Do not upsert invalid chunk records.
- Do not lose source traceability during indexing.
- Do not start indexing before Phase 7 JSONL validation passes.
