# Naive RAG Baseline

## Overview

The Naive RAG phase establishes the first baseline question-answering system. It combines a single hybrid retriever with a strict generation prompt to produce Vietnamese legal answers with citations. This baseline validates that the retrieval pipeline returns relevant chunks and that the LLM can ground answers in provided context.

Naive RAG is intentionally simple:
- One retrieval pass (hybrid dense+sparse search)
- No reranking
- No query decomposition
- Strict citation enforcement
- Clear fallback when evidence is insufficient

This phase runs only after embedding & indexing is complete and validated.

## Quick Start

**Intended API endpoint** (design phase, not yet implemented):

```bash
curl -X POST "http://localhost:8000/api/v1/qa" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Quyền về đất đai của hộ gia đình là gì?",
    "max_chunks": 10,
    "confidence_threshold": 0.75
  }'
```

**Expected response**:
```json
{
  "answer": "Theo Điều 98 Luật Đất đai 2024, hộ gia đình có quyền sử dụng đất...",
  "citations": [
    {
      "chunk_id": "LDD_2024__article_98__clause_1",
      "citation": "Luật Đất đai 2024, Điều 98, Khoản 1",
      "source_url": "https://thuvienphapluat.vn/..."
    }
  ],
  "confidence": 0.89,
  "retrieved_chunks": [...],
  "fallback": false
}
```

## Architecture

```
┌──────────────────────┐
│  User Query          │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Query               │
│  Embedding           │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Top-k               │
│  Retrieval           │
│  (hybrid search)     │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Context             │
│  Packing             │
│  (with citations)    │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Strict Legal        │
│  Prompt              │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  LLM                 │
│  Generation          │
│  (Claude API)        │
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
│  Answer or           │
│  Fallback            │
└──────────────────────┘
```

## Components

### 1. Query Embedding

**Goal**: Convert user question into dense vector matching chunk embedding space.

**Process**:
- Use same embedding model as indexing (e.g., BGE-M3).
- Optionally generate sparse vector (BM25 tokenization) for hybrid retrieval.
- Normalize dense vector (if using cosine similarity).

**Output**: `query_vector` (list[float]) and optionally `query_sparse` (dict).

### 2. Top-k Retrieval

**Goal**: Fetch most relevant chunks from Qdrant.

**Retrieval method**: Hybrid search combining dense and sparse similarity.

**Parameters**:
- `k`: number of chunks to retrieve (default: 10)
- `fusion_method`: "rrf" (Reciprocal Rank Fusion) or weighted sum
- `metadata_filters`: optional filters (e.g., `law_id`, `effective_date` range)

**Query to Qdrant**:
```python
results = client.search(
    collection_name="vnlaw_qa_chunks",
    query_vector=("dense", query_vector),
    query_sparse_vector=query_sparse,  # if available
    limit=k,
    with_payload=True,
    with_vectors=False
)
```

**Output**: List of `ScoredPoint` with `chunk_id`, `score`, `payload`.

### 3. Context Packing

**Goal**: Assemble retrieved chunks into a coherent context for the LLM.

**Process**:
- Sort retrieved chunks by score (highest first).
- For each chunk, format as:
  ```
  [Citation: Luật Đất đai 2024, Điều 123, Khoản 2, Điểm c]
  Nội dung của Điểm c...
  ```
- Concatenate up to `max_chunks` (e.g., 10) with newlines between.
- Prepend with instruction header (see Strict Legal Prompt).

**Output**: Single `context` string.

### 4. Strict Legal Prompt

**Goal**: Force LLM to ground answer in provided context only.

**Template**:

```
You are a Vietnamese legal QA assistant. Answer the question using ONLY the provided context.
If the context does not contain relevant information, respond with the fallback message.

Cite every factual claim with the exact citation format: "Luật ..., Điều ..., Khoản ..., Điểm ..."
Do NOT invent laws, articles, or citations.

Context:
{context}

Question: {query}

Answer:
```

**Fallback message** (if no relevant context):
```
I could not find a specific regulation for this issue in the current legal corpus. Please check thuvienphapluat.vn directly or consult a qualified lawyer.
```

**LLM**: Claude API (Haiku or Sonnet for cost/speed trade-off). Temperature = 0 for determinism.

### 5. LLM Generation

**Goal**: Produce Vietnamese legal answer grounded in context.

**Process**:
- Send prompt to Anthropic API (`messages/create`).
- Stream response or wait for completion.
- Extract `content[0].text`.

**Output**: Generated answer string.

### 6. Citation Validator

**Goal**: Verify that answer mentions exist in retrieved context.

**Process**:
- Parse answer for citation patterns: `r"Luật .+, Điều \d+(, Khoản \d+(, Điểm [a-z])?)?"`
- For each found citation:
  - Check that at least one retrieved chunk has matching `citation` (exact string match).
  - If citation not found → mark as unsupported.
- If unsupported citations found OR answer length < threshold → trigger fallback.

**Confidence scoring**:
- Base confidence = average retrieval scores (from Qdrant).
- Adjust down if citation validator finds unsupported claims.
- Adjust down if answer is very short (< 50 chars) or generic.

**Decision**:
- If `confidence >= threshold` (default 0.75) and all citations supported → return answer.
- Else → return fallback message with `fallback: true`.

## Pipeline Execution Flow

1. Receive query via API (`/api/v1/qa`).
2. Generate query embedding (dense + sparse).
3. Perform hybrid retrieval from Qdrant (`k=10`).
4. Pack context with citation anchors.
5. Construct strict legal prompt.
6. Call Claude API → generate answer.
7. Run citation validator on answer vs retrieved chunks.
8. Compute confidence score.
9. If confidence ≥ threshold and citations valid → return answer with metadata.
10. Else → return fallback response.

## Data Models / Output Schema

### API Request

```json
{
  "query": "Quyền sử dụng đất của hộ gia đình?",
  "max_chunks": 10,
  "confidence_threshold": 0.75
}
```

### API Response (success)

```json
{
  "answer": "Theo Điều 98 Luật Đất đai 2024, hộ gia đình có quyền sử dụng đất để xây dựng nhà ở...",
  "citations": [
    {
      "chunk_id": "LDD_2024__article_98__clause_1__point_a",
      "citation": "Luật Đất đai 2024, Điều 98, Khoản 1, Điểm a",
      "source_url": "https://thuvienphapluat.vn/..."
    }
  ],
  "confidence": 0.89,
  "retrieved_chunks": [
    {
      "chunk_id": "LDD_2024__article_98__clause_1__point_a",
      "score": 0.92,
      "payload": { ... }
    }
  ],
  "fallback": false,
  "processing_time_ms": 1450
}
```

### API Response (fallback)

```json
{
  "answer": "I could not find a specific regulation for this issue in the current legal corpus. Please check thuvienphapluat.vn directly or consult a qualified lawyer.",
  "citations": [],
  "confidence": 0.0,
  "retrieved_chunks": [...],  # still included for debugging
  "fallback": true,
  "processing_time_ms": 1200
}
```

## CLI Reference

### Intended CLI for testing

```bash
# Single query
uv run python -m src.generation.naive_rag \
  --query "Quyền về đất đai của hộ gia đình?" \
  --qdrant-url http://localhost:6333 \
  --collection-name vnlaw_qa_chunks

# Batch evaluation (with golden QA)
uv run python -m src.generation.naive_rag \
  --eval-dataset data/eval/golden_qa.jsonl \
  --output-dir data/eval/naive_rag_results
```

## Testing

**Unit tests**:
- `test_context_packing()`: retrieved chunks formatted with citation anchors.
- `test_prompt_template()`: prompt contains context and query; fallback instruction present.
- `test_citation_validator()`: exact citation match detected; unsupported citation rejected.
- `test_confidence_scoring()`: confidence < threshold triggers fallback.

**Integration test**:
- End-to-end: query → retrieval → generation → answer.
- Verify answer contains at least one citation from retrieved context.
- Latency < 2 seconds (p95) for simple queries.
- Fallback triggered for out-of-corpus questions.

**Golden QA evaluation** (separate phase 12):
- Dataset of (query, expected answer, expected citation).
- Metrics: answer relevance, citation accuracy, faithfulness, unsupported claim rate.

## Error Handling

- **Qdrant search failure**: Log error, return fallback with `confidence=0`, include error in response for debugging.
- **LLM API failure**: Retry with exponential backoff (max 3 attempts); after failures, return fallback.
- **Timeout**: If retrieval or generation exceeds timeout (e.g., 5s), abort and fallback.
- **Malformed response**: If LLM returns non-text or empty, treat as failure → fallback.

All errors logged with structured context; API returns 200 even for fallback (business logic error, not HTTP error).

## Troubleshooting

| Issue | Possible Cause | How to Check | Recommended Fix |
|-------|----------------|--------------|-----------------|
| No citations in answer | Prompt too weak OR LLM ignoring instruction | Inspect raw LLM response | Strengthen prompt: "Cite every fact with exact format"; add citation validator |
| Hallucinated citations | LLM invented citations not in context | Compare answer citations with retrieved `citation` fields | Enforce citation validator to reject unsupported citations; trigger fallback |
| Retrieval returns irrelevant chunks | Query embedding mismatch OR index not built correctly | Inspect retrieved `payload.text`; check embedding model | Verify embedding model matches indexing model; test with known similar queries |
| High latency (>5s) | LLM API slow OR retrieval slow | Measure time per stage | Optimize Qdrant query (filters, k); use faster LLM model (Haiku); cache frequent queries |
| Fallback for all queries | Confidence threshold too high OR validator too strict | Check confidence scores in logs | Lower threshold (e.g., 0.6); review validator logic; ensure retrieval returns relevant chunks |
| Empty context sent to LLM | Retrieval returned zero results | Check `retrieved_chunks` length | Verify index has data; check query embedding; test Qdrant directly |

## Best Practices

- **No source → fallback** — if retrieval returns zero chunks, immediately fallback; do not call LLM.
- **Citation grounding** — every factual sentence must have a citation from context; validator enforces this.
- **Deterministic prompts** — same query should produce same answer (temperature=0, fixed model).
- **Latency budget** — target < 2s end-to-end; monitor p50/p95.
- **Log full trace** — record query, retrieved chunk IDs, answer, confidence for debugging and evaluation.
- **Keep fallback clear** — do not attempt to answer if confidence low; better to say "I don't know" than hallucinate.

## Changelog

### Version 0.1 (2026-05-21)

- Created initial Naive RAG baseline documentation.
- Defined pipeline: query embedding → hybrid retrieval → context packing → strict prompt → LLM → citation validator → answer/fallback.
- Specified API request/response schema with citations and confidence.
- Provided fallback policy and confidence threshold mechanism.
- Documented testing strategy and golden QA evaluation.
- Added troubleshooting for common retrieval/generation issues.

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
| `docs/processed_jsonl.md` | Existing | JSONL export schema and validation |
| `docs/embedding_indexing.md` | Future extension | Embedding model and Qdrant indexing |
| `docs/advanced_rag.md` | Future extension | Hybrid retrieval, reranking, time-aware filtering |
| `docs/graphrag_agents.md` | Future extension | Legal graph schema, traversal, agent orchestration |
| `docs/evaluation.md` | Future extension | Evaluation metrics, golden QA dataset, CI gates |
| `docs/api_deployment.md` | Future extension | FastAPI endpoints, Docker deployment, security |
