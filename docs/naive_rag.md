# Naive RAG Baseline

## Phase 8 Handoff

The validated retrieval foundation is now available:

```text
Collection: vnlaw_chunks_bgem3_v1_full
Points: 40,389
Embedding model: BAAI/bge-m3
Dense vector: dense
Dimension: 1024
Distance: Cosine
Sparse indexing: disabled
```

Phase 9A now begins with retrieval only:

1. Embed Vietnamese queries with the same BGE-M3 model.
2. Run dense top-k Qdrant search against named vector `dense`.
3. Return payload-backed evidence using `text`, `parent_text`, citation,
   hierarchy, law metadata, hashes, and source fields.
4. Evaluate retrieval relevance and filtering behavior.
5. Add LLM answer generation only when explicitly scoped after retrieval
   quality is understood.

Do not introduce sparse/hybrid retrieval, RRF, reranking, GraphRAG, or a
production API in the first retrieval slice.

## Phase 9A Implemented Baseline

The current implemented retrieval slice is read-only dense search:

```text
Vietnamese query
→ BGE-M3 query embedding
→ query-vector validation
→ Qdrant named-vector search using dense
→ typed payload-backed retrieval candidates
→ safe CLI summary / optional JSON report
```

Implemented files:

```text
configs/retrieval/retrieval.yml
src/retrieval/models.py
src/retrieval/filters.py
src/retrieval/dense_retriever.py
src/services/retrieval_service.py
scripts/run_dense_retrieval.py
tests/unit/retrieval/
```

Phase 9A does not call an LLM, generate answers, validate generated citations,
perform hybrid retrieval, run RRF, rerank, expose a FastAPI endpoint, or mutate
Qdrant/corpus artifacts.

## Phase 9A.1 Sanity Evaluation

Live dense-retrieval smoke tests passed technically but showed quality and
citation-risk limitations. The baseline can return the correct parent Article
context while ranking a sibling child Clause/Point ahead of the exact provision
needed for citation. This is especially risky for future generation because an
LLM could use `parent_text` content while citing the retrieved child chunk.

Phase 9A.1 adds:

```text
data/eval/manual_retrieval_queries.jsonl
src/retrieval/evaluation.py
scripts/evaluate_dense_retrieval.py
tests/unit/retrieval/test_evaluation.py
```

The evaluator measures:

- expected-target recall at 5/10/20 using explicit `match_level`
  semantics;
- Article-level hit at 5/10/20;
- MRR@20;
- best Article, Clause, Point, and exact-depth ranks;
- metadata completeness and issue counts;
- evidence/citation risk flags.

Manual expected targets declare whether the expected depth is `article`,
`clause`, or `point`. Article-level targets match any retrieved child chunk
under the expected Article. Clause-level targets match any retrieved chunk under
the expected Clause, including Point chunks. Point-level targets require the
exact Point label. Null fields below the declared depth are not treated as
exact-null requirements.

Dense-only retrieval should not be treated as production-ready or safe for
answer generation until these reports are reviewed and the citation risks are
handled. Hybrid search, RRF, and reranking remain Phase 10 work.

## Phase 9A.2 Evidence Safety

Phase 9A.2 adds evidence/context assembly rules without generating answers:

```text
RetrievalResult
→ EvidenceBundle
→ ordered EvidencePacket objects
→ citation-safe rendered context for later use
```

Implemented files:

```text
src/retrieval/evidence.py
tests/unit/retrieval/test_evidence.py
```

The evidence layer separates:

- citable child text, which stays adjacent to the retrieved chunk citation;
- article-level context, which is citable only for article-level chunks;
- broader parent Article context for child chunks, which is auxiliary only.

This directly handles the Article 113 annual-leave risk: if dense retrieval
returns a sibling child chunk such as Clause 4, but that chunk's `parent_text`
contains Clause 1, the packet remains citable only for Clause 4. The broader
`parent_text` is rendered under:

```text
Auxiliary article context, not directly citable under this child citation:
```

Evidence packets carry structural safety metadata:

```text
citation_scope: child_exact | article_context | unsafe_parent_context | missing_citation
safety_level: safe | caution | unsafe
parent_context_policy: absent | excluded | auxiliary_only | citable_article_context |
                       equivalent_to_child | deduplicated
```

Unsafe packets are used for missing citation, missing law/source metadata,
missing child text, or empty/repealed flags. Caution packets are still citable
at child level but require care because parent Article context, truncation, or
other non-fatal issues are present.

This layer does not fix dense ranking. It prevents future Naive RAG generation
from silently citing a child chunk for claims found only in broader parent
context.

## Phase 9A.3 Evidence Selection Gate

Phase 9A.3 adds answerability decisions without generating answers:

```text
EvidenceBundle
→ EvidenceSelectionResult
→ answer_allowed | fallback_required | needs_review
```

Implemented files:

```text
src/retrieval/selection.py
tests/unit/retrieval/test_selection.py
```

The selector chooses only evidence that is safe enough for a future generation
step and records why other packets were rejected. The result includes selected
evidence, rejected evidence, fallback reasons, warnings, and a rendered context
containing selected evidence only.

Default rules:

- unsafe packets are rejected;
- safe packets sort before caution packets;
- caution packets can be selected only when they still have citable child text,
  citation, law ID, and source URL;
- parent Article context is never promoted to directly citable text under a
  child citation;
- unsafe packets are never rendered into selected context;
- if all selected evidence is caution because only auxiliary parent context is
  available, fallback is required by default;
- optional evaluation-assisted mode can require selected evidence to match
  expected targets from the Phase 9A.1 manual evaluation dataset.

For the annual-leave case, sibling Article 113 chunks remain insufficient in
evaluation-assisted mode because they do not match Clause 1 or Points a/b/c.
The gate returns fallback/review instead of allowing clean downstream answer
generation from parent context alone.

This gate is the required input surface for Phase 9B, but it is not itself a
prompt template and it does not call an LLM.

## Phase 9A.4 Selection Smoke Test

Phase 9A.4 adds a read-only integration smoke test before any answer
generation:

```text
manual query
→ dense retrieval
→ evidence bundle assembly
→ evidence selection/fallback gate
→ JSON smoke report
```

Implemented files:

```text
src/retrieval/integration.py
scripts/run_selection_smoke.py
tests/unit/retrieval/test_integration.py
```

The smoke test reuses `data/eval/manual_retrieval_queries.jsonl`, including
`expected_decision` and `allowed_decisions` metadata for known manual cases. It
checks whether the current retrieval-side pipeline returns an acceptable
decision for each query:

- `annual_leave_days` should be `fallback_required` or `needs_review`, not
  clean `answer_allowed`, while exact Clause/Point evidence remains missing;
- `health_insurance_children_under_6` should allow an answer when exact point
  evidence is selected;
- `civil_code_scope` should allow an answer when Article-level evidence is
  selected;
- `marriage_conditions` is reported with selected evidence and risk state
  because Article 8 may rank lower;
- `civil_rights_protection` can pass as `answer_allowed` or `needs_review`
  depending on selected evidence safety.

The report includes run metadata, aggregate decision/pass counts, evidence and
selection config, per-query retrieval latency, decision, allowed decisions,
fallback reasons, selection warnings, risk flags, top result, selected/rejected
evidence summaries, and a rendered selected-context preview.

In evaluation/smoke mode, expected-target-aware selection prefers selectable
packets that match the manual expected targets before unrelated evidence. This
does not alter dense retrieval ranking. It ensures a lower-ranked but valid
expected Article/Clause/Point packet is not accidentally excluded by
`max_selected_packets`. The `civil_rights_protection` case validates this for
Article 2, while `annual_leave_days` remains blocked because sibling Article
113 clauses do not match the expected Clause 1 / Point a-b-c targets.

`--strict` additionally enforces Phase 9A.1 risk flags inside the selection
gate. Non-strict mode still reports risk flags but does not use them as hard
selection blockers.

This smoke test does not call an LLM, generate an answer, create prompts, fix
ranking, perform hybrid retrieval, rerank, or mutate Qdrant/corpus artifacts.

## Phase 9A.5 Workflow Boundary

Phase 9A.5 moves executable workflow logic from top-level scripts into reusable
modules:

```text
src/retrieval/workflows/common.py
src/retrieval/workflows/dense_retrieval.py
src/retrieval/workflows/dense_evaluation.py
src/retrieval/workflows/selection_smoke.py
```

The existing commands are preserved through thin wrappers:

```text
scripts/run_dense_retrieval.py
scripts/evaluate_dense_retrieval.py
scripts/run_selection_smoke.py
```

The workflow modules own argument parsing, config loading, dependency
construction, path safety checks, report writing, and console summaries. The
scripts only bootstrap imports and call the workflow `main()` function.

No retrieval behavior, evaluation metrics, evidence safety rules, selection
decisions, report schemas, or command-line flags were intentionally changed.
Phase 9B scripts follow the same boundary: reusable workflow
logic under `src/`, top-level `scripts/` as compatibility wrappers only.

## Overview

The Naive RAG phase will establish the first baseline question-answering
system. Its first slice is dense retrieval only; answer generation follows
only after retrieval behavior is measured.

Naive RAG is intentionally simple:
- One dense retrieval pass against the existing Qdrant collection
- No reranking
- No query decomposition
- Payload-backed citation and context assembly

This phase runs only after embedding & indexing is complete and validated.

## Quick Start

Run one read-only dense retrieval query:

```bash
uv run --extra qdrant --extra embedding python scripts/run_dense_retrieval.py \
  --query "Quyền sử dụng đất của hộ gia đình là gì?" \
  --collection-name vnlaw_chunks_bgem3_v1_full \
  --url http://localhost:6333 \
  --top-k 10 \
  --device cpu \
  --output artifacts/reports/retrieval/manual_query_result.json
```

The console summary includes rank, score, chunk ID, citation, law metadata,
hierarchy labels, source URL, and a text preview. The optional JSON report
includes typed result metadata and text/parent-text previews, not an answer.

Run the manual sanity evaluation:

```bash
uv run --extra qdrant --extra embedding python scripts/evaluate_dense_retrieval.py \
  --queries data/eval/manual_retrieval_queries.jsonl \
  --collection-name vnlaw_chunks_bgem3_v1_full \
  --url http://localhost:6333 \
  --top-k 20 \
  --device cpu \
  --output artifacts/reports/retrieval/dense_retrieval_eval.json
```

Run the selection integration smoke test:

```bash
uv run --extra qdrant --extra embedding python scripts/run_selection_smoke.py \
  --queries data/eval/manual_retrieval_queries.jsonl \
  --collection-name vnlaw_chunks_bgem3_v1_full \
  --url http://localhost:6333 \
  --top-k 20 \
  --device cpu \
  --output artifacts/reports/retrieval/selection_smoke_report.json
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
│  (dense search)      │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Typed Evidence      │
│  Results             │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  EvidenceBundle      │
│  Assembly            │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Evidence Selection  │
│  Gate                │
└──────────────────────┘
```

Implemented Phase 9B Naive RAG generation extends this retrieval baseline:

```
┌──────────────────────┐
│  Retrieved Evidence  │
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
│  (OpenRouter)        │
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
- Normalize dense vector (if using cosine similarity).

**Output**: `query_vector` (list[float]).

### 2. Top-k Retrieval

**Goal**: Fetch most relevant chunks from Qdrant.

**Retrieval method**: Dense cosine search using named vector `dense`.

**Parameters**:
- `k`: number of chunks to retrieve (default: 10)
- `metadata_filters`: optional filters (e.g., `law_id`, `effective_date` range)

**Query to Qdrant**:
```python
results = client.search(
    collection_name="vnlaw_chunks_bgem3_v1_full",
    query_vector=("dense", query_vector),
    limit=k,
    with_payload=True,
    with_vectors=False
)
```

**Output**: List of `ScoredPoint` with `chunk_id`, `score`, `payload`.

### 3. Evidence Context Assembly

**Goal**: Assemble retrieved chunks into citation-safe evidence packets before
any future LLM use.

**Process**:
- Preserve retrieval rank.
- Deduplicate repeated chunk IDs.
- Keep child `text` next to its retrieved citation.
- Render broader child `parent_text` as auxiliary context unless the chunk is
  article-level.
- For each packet, format citable text separately from auxiliary context:
  ```
  [E1]
  Citation: Luật Đất đai (VBHN 2025), Điều 123, Khoản 2, Điểm c
  Citable text:
  Nội dung của Điểm c...

  Auxiliary article context, not directly citable under this child citation:
  Điều 123...
  ```
- Mark truncated text with an explicit truncation marker.

**Output**: `EvidenceBundle` plus a rendered context string.

### 4. Evidence Selection Gate

**Goal**: Decide whether the assembled evidence is safe enough for future
answer generation.

**Process**:
- Reject unsafe packets.
- Prefer safe packets over caution packets.
- Select caution packets only when child text remains citable.
- Keep auxiliary parent context visibly separate from child citable text.
- Return `fallback_required` or `needs_review` when evidence is insufficient or
  structurally risky.

**Output**: `EvidenceSelectionResult` with selected context or fallback/review
reasons.

### 5. Strict Legal Prompt (future)

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

**Fallback message** (if no selected citation-safe evidence):
```
Hiện tại hệ thống chưa tìm được căn cứ pháp lý đủ an toàn để trả lời chắc chắn.
```

**LLM**: OpenRouter chat completions. Default model:
`google/gemini-2.5-flash`. Temperature = 0 by default.

### 5. LLM Generation

**Goal**: Produce Vietnamese legal answer grounded in context.

**Process**:
- Call OpenRouter only when `EvidenceSelectionResult.decision == answer_allowed`.
- Use selected evidence only in the prompt.
- Extract the first assistant message text.
- Run the lightweight `[E#]` citation guard.

**Output**: Generated answer string.

### 6. Citation Validator (future)

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

Implemented Phase 9A flow:

1. Receive one query via `scripts/run_dense_retrieval.py`.
2. Validate non-empty query and positive `top_k`.
3. Generate a BGE-M3 dense query embedding.
4. Validate that the query vector is numeric, finite, non-empty, and
   1024-dimensional.
5. Query Qdrant collection `vnlaw_chunks_bgem3_v1_full` using named vector
   `dense`, `with_payload=True`, and `with_vectors=False`.
6. Map Qdrant results into typed `RetrievedChunk` objects.
7. Preserve citation, hierarchy, source metadata, warning metadata, repealed
   flags, and indexing provenance where present.
8. Print a safe summary and optionally write a retrieval JSON report.

Implemented Phase 9A.1 evaluation flow:

1. Load manual queries from `data/eval/manual_retrieval_queries.jsonl`.
2. Run the existing dense retriever read-only for each query.
3. Compare results against manual expected targets.
4. Distinguish Article-level hits from exact provision hits.
5. Compute recall/MRR and metadata completeness metrics.
6. Emit conservative evidence/citation risk flags.
7. Write a JSON evaluation report.

Implemented Phase 9A.4 selection smoke flow:

1. Load manual queries and allowed decisions from
   `data/eval/manual_retrieval_queries.jsonl`.
2. Run the existing dense retriever read-only for each query.
3. Build an `EvidenceBundle` from the retrieval result.
4. Run the evidence selection/fallback gate.
5. Compare the decision against the query's allowed decisions.
6. Write a JSON smoke report with selected/rejected evidence summaries and a
   rendered selected-context preview.

Implemented Phase 9A.5 workflow boundary:

1. Keep the same user-facing script commands.
2. Route each script into a `src/retrieval/workflows/` module.
3. Keep shared path and JSON report helpers in
   `src/retrieval/workflows/common.py`.
4. Leave retrieval, evaluation, evidence, and selection semantics unchanged.

Implemented Phase 9B Naive RAG generation flow:

1. Use selected evidence only from `EvidenceSelectionResult`.
2. Construct a strict legal prompt.
3. If `decision != answer_allowed`, return deterministic fallback without
   calling the LLM.
4. If `decision == answer_allowed`, call OpenRouter with temperature 0 by
   default.
5. Run a lightweight citation ID guard over generated `[E#]` citations.
6. Return either a cited answer result or a safe fallback result.

Implemented Phase 9B files:

```text
src/retrieval/llm_client.py
src/retrieval/prompting.py
src/retrieval/generation.py
src/retrieval/rag_pipeline.py
src/retrieval/workflows/naive_rag.py
scripts/run_naive_rag.py
```

OpenRouter is the first concrete provider. Non-secret defaults live in
`configs/llm/openrouter.yml`:

```text
base_url=https://openrouter.ai/api/v1
default_model=google/gemini-2.5-flash
dev_model=google/gemini-2.5-flash-lite
```

`OPENROUTER_API_KEY` is required only when the evidence gate allows generation.
It belongs only in the real environment or uncommitted project `.env`. The CLI
loads `.env` automatically with exported environment values taking precedence.
Fallback/review results do not call OpenRouter.

Configuration precedence:

```text
model: --model > OPENROUTER_MODEL > config default_model > emergency fallback
base URL: OPENROUTER_BASE_URL > config base_url > emergency fallback
API key: OPENROUTER_API_KEY from environment/.env only; no fallback
```

Never commit `.env`, print the API key, or include it in reports.

The prompt contains selected evidence only. Rejected evidence, unsafe evidence,
and raw retrieval results are not included. Auxiliary parent Article context is
shown only in a section labeled as not directly citable. Every selected packet
receives an internal citation ID (`[E1]`, `[E2]`, ...), and generated citation
IDs are mapped back to real source/citation metadata.

## Phase 9C Generation Evaluation

Phase 9C reuses the existing `run_naive_rag(...)` pipeline for a small manual
dataset. It does not duplicate retrieval, evidence selection, prompting, or
generation logic.

Deterministic checks include:

- actual decision is allowed for the case;
- LLM calls match the expected policy;
- fallback/review decisions do not call the LLM or return citations;
- required answers contain valid mapped `[E#]` IDs;
- missing and unknown citation IDs are counted;
- answer text is likely Vietnamese;
- configured unsafe/confidence phrases are absent;
- secret-like provider authentication content is absent.

Run:

```bash
uv run --extra qdrant --extra embedding python scripts/evaluate_naive_rag_generation.py \
  --queries data/eval/manual_naive_rag_generation_queries.jsonl \
  --collection-name vnlaw_chunks_bgem3_v1_full \
  --url http://localhost:6333 \
  --top-k 20 \
  --device cpu \
  --provider openrouter \
  --model google/gemini-2.5-flash-lite \
  --output artifacts/reports/retrieval/naive_rag_generation_eval.json
```

The report exposes `citation_id_coverage_rate`,
`unknown_citation_id_count`, and `missing_citation_id_count`. Citation ID
coverage is not semantic faithfulness. The baseline is not production-ready,
does not provide professional legal advice, and does not include Phase 10
retrieval improvements or an LLM judge.

The initial live run with `google/gemini-2.5-flash-lite` passed all three cases
with citation ID coverage 1.0, fallback policy pass rate 1.0, and zero
unknown/missing citation IDs, forbidden phrases, or secret leaks.

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
  "answer": "Theo Điều 98 Luật Đất đai (VBHN 2025), hộ gia đình có quyền sử dụng đất để xây dựng nhà ở...",
  "citations": [
    {
      "chunk_id": "LDD_VBHN__article_98__clause_1__point_a",
      "citation": "Luật Đất đai (VBHN 2025), Điều 98, Khoản 1, Điểm a",
      "source_url": "https://thuvienphapluat.vn/..."
    }
  ],
  "confidence": 0.89,
  "retrieved_chunks": [
    {
      "chunk_id": "LDD_VBHN__article_98__clause_1__point_a",
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

### Implemented Dense Retrieval CLI

```bash
uv run --extra qdrant --extra embedding python scripts/run_dense_retrieval.py \
  --query "Quyền về đất đai của hộ gia đình?" \
  --url http://localhost:6333 \
  --collection-name vnlaw_chunks_bgem3_v1_full \
  --top-k 10 \
  --device cpu
```

Supported safe filters:

```text
--law-id
--chunk-kind
--level
--article-number
--source-domain
--exclude-repealed
```

## Testing

**Implemented Phase 9A unit tests**:
- retrieval query validation and top-k validation;
- dense vector dimension and finite-value validation;
- Qdrant result mapping into typed retrieval objects;
- missing optional payload fields tolerated;
- missing critical payload fields reported as typed issues;
- Qdrant called with named vector `dense`, `with_payload=True`, and
  `with_vectors=False`;
- safe filter construction over indexed payload fields;
- CLI parser and output-path safety helpers.

**Implemented Phase 9A.1 unit tests**:
- manual query record parsing;
- Article-level and exact provision matching;
- recall and MRR computation;
- empty result handling;
- wrong-law and wrong-Article risk flags;
- parent-context/child-provision mismatch risk flags;
- aggregate metric computation;
- evaluation report shape;
- evaluation CLI parser and path validation.

**Implemented Phase 9A.4 unit tests**:
- smoke pipeline composition with mocked retriever/builder/selector;
- decision pass/fail checks from `allowed_decisions`;
- batch aggregation and per-query error capture;
- case-id filtering;
- report shape and rendered-context preview truncation;
- enum serialization for selected/rejected evidence summaries;
- smoke CLI parser and path validation.

**Implemented Phase 9A.5 workflow tests**:
- wrapper scripts import workflow `main()` functions;
- workflow parsers preserve existing command flags;
- shared JSON writer creates parent directories and writes UTF-8 JSON.

**Implemented Phase 9B unit tests**:
- OpenRouter missing-key handling and `MockLLMClient`;
- selected-evidence-only prompt construction;
- auxiliary context labeling as not directly citable;
- deterministic fallback result construction;
- lightweight `[E#]` citation guard;
- fallback/needs-review decisions skip LLM calls;
- answer-allowed decisions call the mock LLM exactly once;
- rejected/unsafe evidence does not appear in the LLM prompt;
- annual-leave-style exact target miss remains fallback;
- health-insurance-style exact point evidence allows generation;
- Naive RAG workflow parser and thin script wrapper.

**Implemented Phase 9C unit tests**:
- decision and LLM call policy;
- fallback policy;
- missing and unknown citation IDs;
- likely Vietnamese output;
- forbidden phrases and secret-like leakage;
- aggregate report metrics;
- injected workflow runner and secret-free report writing;
- thin evaluation script wrapper.

**Integration test**:
- Phase 9A: query → embedding → Qdrant dense retrieval → typed evidence.
- Phase 9B: query → retrieval → evidence selection → fallback or generation.

**Golden QA evaluation** (separate phase 12):
- Dataset of (query, expected answer, expected citation).
- Metrics: answer relevance, citation accuracy, faithfulness, unsupported claim rate.

## Error Handling

- **Empty query**: rejected before embedding.
- **Invalid `top_k`**: rejected before embedding.
- **Embedding failure**: returned as a retrieval error.
- **Vector dimension mismatch or non-finite values**: rejected before Qdrant.
- **Qdrant search failure**: returned as a retrieval error.
- **Missing optional payload fields**: tolerated.
- **Missing critical payload fields**: reported in typed retrieval issues.

Phase 9B generation errors return structured fallback results. Missing
OpenRouter credentials, provider errors, prompt construction failures, and
strict invalid citation failures are reported without exposing API keys.

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

### Version 0.2 (2026-06-12)

- Implemented Phase 9A dense retrieval baseline.
- Added typed retrieval models, safe filters, a read-only dense retriever,
  service wrapper, config, CLI, and unit tests.
- Kept answer generation, prompt templates, citation validation, hybrid search,
  RRF, reranking, FastAPI, and evaluation out of scope.

### Version 0.3 (2026-06-12)

- Implemented Phase 9A.1 dense retrieval sanity evaluation and evidence-risk
  audit.
- Added a small manual query dataset, exact-vs-Article hit metrics, MRR@20,
  metadata completeness metrics, risk flags, evaluation CLI, and mocked unit
  tests.
- Documented that dense-only retrieval is not yet reliable enough for answer
  generation without further evidence handling.

### Version 0.4 (2026-06-12)

- Implemented Phase 9A.2 evidence safety/context assembly, Phase 9A.3 evidence
  selection/fallback rules, and Phase 9A.4 selection integration smoke tests.
- Added citation-safe evidence packets, answerability decisions, selected
  evidence rendering, and JSON smoke reports for known manual retrieval cases.
- Kept LLM answer generation, prompt templates, generated-citation validation,
  hybrid retrieval, RRF, and reranking out of scope.

### Version 0.5 (2026-06-12)

- Moved retrieval workflow logic into `src/retrieval/workflows/`.
- Kept top-level retrieval scripts as backward-compatible thin wrappers.
- Preserved command flags, report paths, and retrieval-side behavior.
- Documented the workflow boundary for Phase 9B entrypoints.

### Version 0.6 (2026-06-12)

- Implemented Phase 9B fallback-aware Naive RAG generation.
- Added OpenRouter and mock LLM clients, selected-evidence prompt building,
  deterministic fallback results, and lightweight `[E#]` citation checks.
- Added `scripts/run_naive_rag.py` as a thin wrapper around
  `src/retrieval/workflows/naive_rag.py`.
- Kept hybrid retrieval, RRF, reranking, GraphRAG, agents, API endpoints, and
  production legal-advice claims out of scope.

### Version 0.7 (2026-06-12)

- Implemented Phase 9C repeatable Naive RAG generation evaluation.
- Added a three-case manual dataset, deterministic safety validators, aggregate
  JSON reporting, and a thin evaluation command.
- Kept semantic faithfulness as a manual/separate evaluation concern.

### Version 0.1 (2026-05-21)

- Created initial Naive RAG baseline documentation.
- Defined initial future pipeline: query embedding → retrieval → context
  packing → strict prompt → LLM → citation validator → answer/fallback.
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
