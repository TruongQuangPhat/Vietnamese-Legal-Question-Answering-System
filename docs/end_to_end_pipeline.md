# VnLaw-QA: End-to-End Pipeline Overview

## 1. Overview

VnLaw-QA is a Vietnamese Legal Question-Answering system using RAG (Retrieval-Augmented Generation) architecture to answer legal questions based on accurate legal text sources.

Unlike general chatbots, Legal QA requires:
- **Source transparency**: Every answer must cite exact Clause, Article, Point, Law, and effective year.
- **Legal hierarchy preservation**: Part → Chapter → Section → Article → Clause → Point must remain intact.
- **Citation validation**: System validates citation accuracy before answering.
- **Clear fallback**: If no suitable source found, system declines to answer and suggests direct verification.

Current status: the corpus and retrieval/generation evaluation stack are
implemented through final Advanced RAG / strict generation evaluation. The
corpus has 52/52 raw artifacts, 52/52 normalized outputs, 52/52 hierarchy
outputs, and `data/processed/legal_chunks.jsonl` with 40,389 validated chunks.
Dense indexing is complete in Qdrant collection
`vnlaw_chunks_bgem3_v1_full`. The Naive RAG baseline remains a baseline with
known limitations. The final adopted retrieval strategy is
`coverage_aware_quota`; reranking was evaluated but not adopted; time-aware
filtering and GraphRAG remain future/separately scoped. API deployment is now
implemented through the Azure App Service production container backend, and
MLOps/maintenance controls are partially implemented through CI gates,
container deployment, warmup, and production smoke workflows.

Current benchmark status:

```text
benchmark_version = v0.1.0
query_count = 128
development = 85
held_out_test = 43
held_out_test = reporting_only
```

## 2. Quick Start

Recommended development flow:

```
uv sync
  ↓
Registry & Corpus check (configs/laws/corpus_registry.yml)
  ↓
Crawling → data/raw/ (52 laws)
  ↓
Raw Corpus Audit & Validation
  ↓
Cleaning / Normalization
  ↓
Legal Hierarchy Parsing
  ↓
Parent-child Chunking
  ↓
Processed Chunk Validation & Embedding Readiness
  ↓
Embedding & Indexing
  ↓
Naive RAG (baseline)
  ↓
Advanced RAG (coverage-aware hybrid retrieval)
  ↓
GraphRAG + Agents
  ↓
Evaluation (benchmark metrics + strict generation diagnostics)
  ↓
API / Deployment
```

**Important**: Final benchmark results are engineering evidence, not qualified
human legal review or production legal-advice certification.

## 3. Full Architecture

End-to-end pipeline:

```
┌─────────────────────┐
│  Corpus Registry    │ configs/laws/corpus_registry.yml
│  (52 law_id entries)│
└──────────┬──────────┘
           │
           ▼
┌─────────────────────────┐
│ Registry-driven Crawler │ → data/raw/{law_id}/latest/
│ (thuvienphapluat.vn)    │   artifacts/reports/crawling/crawl_report.json
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  Raw Corpus Audit       │ → artifacts/reports/audit/raw_corpus_audit.json
│  & Validation           │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  Cleaning / Norm        │ → cleaned Vietnamese legal text
│  (Unicode, whitespace)  │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  Legal Hierarchy Parser │ → JSON: {part, chapter, article,
│  (Phần/Chương/Mục/Điều) │   clause, point, metadata}
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  Parent-child Chunker   │ → child chunks (embedding)
│                         │ → parent context (LLM context)
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  Processed Chunk Valid. │ → data/processed/*.jsonl
│  (citation integrity)   │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  Embedding (BGE-M3)     │ → dense + sparse vectors
│  (dense + sparse)       │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  Vector Index (Qdrant)  │ → hybrid search index
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  Retriever              │ → relevant chunks (metadata filters)
│  (hybrid dense+sparse)  │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  Reranker (cross-enc)   │ → top-k reordered results
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  Context Packer         │ → citation-anchored prompt
│  (with parent context)  │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  LLM Generator          │ → Vietnamese legal answer
│  (LLM provider)         │   with citations
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  Citation Validator     │ → verify source grounding
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  Evaluation (RAGAS)     │ → quality metrics
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  API / Deployment       │ → FastAPI endpoints
│  (Docker, vLLM)         │   + monitoring
└─────────────────────────┘
```

## 4. Phase-by-phase Pipeline

### Phase 0 — Project Setup & Principles

**Goal**: Establish architectural principles, coding standards, project structure, and development tooling.

**Input**: None (initialization phase).

**Pipeline Summary**: Defines Python 3.11+, OOP standards, type hints, Pydantic V2, async I/O, Google-style docstrings, logging, security policies, and directory structure.

**Output**: `AGENTS.md`, `PROJECT_CONTEXT.md`, `pyproject.toml`,
`.agents/skills/`, `.codex/context/`, and the repository layout used by
`scripts/`, `src/`, `tests/`, `configs/`, and `docs/`.

**Validation Criteria**:
- Code follows PEP8 + type hints
- `uv run mypy src` passes
- `uv run pytest tests/unit` passes
- All public functions/classes have docstrings

**Status**: Implemented

**Detailed documentation**: See `AGENTS.md` (repository rules),
`PROJECT_CONTEXT.md` (current state), and `pyproject.toml` (tool config).

---

### Phase 1 — Legal Corpus Registry

**Goal**: Create an accurate list of 52 Vietnamese legal documents as the trusted corpus.

**Input**: List of laws from thuvienphapluat.vn.

**Pipeline Summary**: Build YAML registry with fields: `law_id`, `title`, `url`, `effective_date`, `expiry_date`, `status`, `vbhn_id` (if available). Each `law_id` is unique.

**Output**: `configs/laws/corpus_registry.yml` (52 entries).

**Validation Criteria**:
- All entries have the 7 required fields
- `law_id` is unique
- URLs are valid (thuvienphapluat.vn format)
- `effective_date` and `status` are valid

**Status**: Implemented

**Detailed documentation**: See `configs/laws/corpus_registry.yml` and `docs/corpus_registry.md`.

---

### Phase 2 — Registry-driven Crawling

**Goal**: Download all 52 HTML artifacts from thuvienphapluat.vn based on the registry.

**Input**: `configs/laws/corpus_registry.yml`.

**Pipeline Summary**: Registry Crawler reads the registry, selects eligible
targets, fetches HTML, saves to `data/raw/{law_id}/latest/main.html` with
metadata JSON, and preserves previous snapshots under `crawls/{timestamp}/`
when force refresh is used. Includes retry, rate-limiting, and error logging.

**Output**: `data/raw/{law_id}/latest/` (52 directories, each containing
`main.html` and `metadata.json`).

**Validation Criteria**:
- 52/52 directories exist in `data/raw/`
- Each `latest/main.html` is present and non-empty
- Metadata matches registry entry
- No unresolved HTTP 4xx/5xx errors

**Status**: Implemented (52/52 laws crawled successfully)

**Detailed documentation**: `docs/raw_data_crawling.md`

---

### Phase 3 — Raw Corpus Audit & Validation

**Goal**: Verify that crawled artifacts are complete, readable, trusted, and
safe to feed into Cleaning & Normalization.

**Input**: `data/raw/{law_id}/latest/main.html` and
`data/raw/{law_id}/latest/metadata.json`.

**Pipeline Summary**:
- Load registry law IDs
- Scan raw artifact directories
- Validate `main.html` and `metadata.json`
- Detect suspiciously small HTML, error pages, and metadata mismatches
- Write `artifacts/reports/audit/raw_corpus_audit.json`

**Output**: `artifacts/reports/audit/raw_corpus_audit.json`.

**Validation Criteria**:
- 52 registry entries are represented in `data/raw/`
- 52 raw artifacts are valid
- No missing raw HTML or metadata files
- No critical metadata mismatches

**Status**: Implemented

**Detailed documentation**: `docs/raw_corpus_audit.md`

---

### Phase 4 — Cleaning & Normalization

**Goal**: Convert raw HTML into clean Vietnamese legal text, normalize Unicode and whitespace, preserve legal heading structure.

**Input**: `data/raw/{law_id}/latest/main.html` plus
`data/raw/{law_id}/latest/metadata.json`.

**Pipeline Summary**:
- Preferred TVPL legal body selection
- Block-aware HTML extraction that keeps block boundaries but avoids inline
  node fragmentation
- Start trimming that preserves early Article 1 and skips source-law/amendment
  pre-body notes
- Unicode and conservative whitespace normalization
- Safe line-fragment repair without merging clause or point boundaries
- Encoded TVPL footer/watermark artifact cleanup
- Article metric generation with references separated from real headings

**Output**: `data/interim/{law_id}/normalized.json` and optional
`data/interim/{law_id}/cleaned.txt`.

**Validation Criteria**:
- 52/52 valid audited artifacts produce `normalized.json`
- Article markers and Article 1 headings are preserved
- Article references and real article headings are reported separately
- No suspiciously short outputs
- No missing article markers
- Known encoded TVPL watermark/footer artifacts are removed

**Status**: Implemented and gate-ready

**Detailed documentation**: `docs/cleaning_normalization.md`

---

### Phase 5 — Legal Hierarchy Parsing — Complete and Hardened

Full-corpus run:

```text
Total documents: 52
Success: 6
Success with warnings: 46
Failed: 0
Validator failures: 0
RED: 0
ORANGE: 0
Source-tail leakage: 0
AMBIGUOUS_CLAUSE_CANDIDATE: 0
POINT_LIKE_LINE_OUTSIDE_CLAUSE: 0
Output: data/interim/{LAW_ID}/hierarchy.json
Report: artifacts/reports/parsing/legal_parsing_report.json
```

Remaining warnings are accepted non-blocking caveats for Phase 6 chunk
validation: SOURCE_NOTE_EXCLUDED, EMPTY_ARTICLE_NODE,
NODE_ID_COLLISION_RESOLVED, ARTICLE_COUNT_MISMATCH,
MAX_ARTICLE_NUMBER_MISMATCH.
### Phase 6 — Parent-child Chunking

**Goal**: Create chunks for embedding (child) and LLM context (parent) using parent-child model to preserve citation integrity.

**Input**: `data/interim/{law_id}/hierarchy.json`.

**Pipeline Summary**:
- **Parent unit**: full Article + metadata (title, article number)
- **Child unit**: Article, Clause, or Point according to hierarchy rules
- **Chunk ID design**: `{source_node_id}__chunk`, preserving Phase 5 node IDs
  and collision-resolved suffixes
- **Citation construction**: `{Law Name}, Điều ...`, `{Law Name}, Khoản ...,
  Điều ...`, or `{Law Name}, Điểm ..., Khoản ..., Điều ...`
- **Metadata propagation**: `law_id`, `law_name`, `article_number`,
  `article_title`, `clause_number`, `point_label`, `citation`,
  `hierarchy_path`, `source_url`, `source_domain`, `source_type`, offsets,
  hashes, and repealed/empty flags
- **Text fields**:
  - `text`: content for embedding (Article/Clause/Point child unit)
  - `parent_text`: full Article for LLM context
- **Hierarchy structure**: `hierarchy_path` string built only from real
  ancestors
- **Parent reference**: `parent_article_node_id` and logical
  `parent_chunk_id`
- **Traceability**: `text_hash` for duplicate detection, `source_url` and `source_domain` for provenance
- Reason for not using arbitrary character chunking: would break legal clauses, invalidate citations, destroy hierarchy.

**Output**: `data/processed/legal_chunks.jsonl`.

**Validation Criteria**:
- Each chunk has unique `chunk_id` and valid Vietnamese citation format
- `parent_text` exists and contains `text`
- Metadata is complete (`law_id`, `law_name`, article/clause/point fields,
  source fields, offsets, hashes, and repealed flags)
- `hierarchy_path` correctly reflects legal hierarchy levels
- `parent_article_node_id` references a valid Article node
- `source_url`, `source_domain`, `source_type` present
- `text_hash` computed and present
- No empty `text` fields
- 0 source-tail markers in `text` and `parent_text`

**Status**: Complete and hardened. Final output has 40,389 chunks, 0 failed
laws, 0 duplicate chunk IDs, 0 chunk invariant issues, 180 empty/repealed
chunks flagged, and 0 source-tail markers in `text`/`parent_text`.

**Detailed documentation**: `docs/parent_child_chunking.md`

---

### Phase 7 — Processed Chunk Validation & Embedding Readiness

**Goal**: Export validated chunks to standard JSONL format, check schema, duplicates, and integrity before embedding.

**Input**: `data/processed/legal_chunks.jsonl`.

**Pipeline Summary**:
- Validate `data/processed/legal_chunks.jsonl`
- Required fields per line (canonical schema):
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

    "text_hash": "sha256...",
    "metadata": {
      "parser_version": "v0.1",
      "chunker_version": "v0.1",
      "raw_artifact_path": "data/raw/LDD_VBHN/latest/main.html"
    }
  }
  ```
- Schema validation (Pydantic model)
- Duplicate chunk detection (same `chunk_id` or identical `text`+`citation`)
- Empty text detection
- Invalid citation detection (missing article/clause/point)
- Output: `artifacts/reports/chunking/processed_validation.json` (pass/fail, error list)

**Output**: `data/processed/*.jsonl`, `artifacts/reports/chunking/processed_validation.json`.

**Validation Criteria**:
- All 52 files exist in `data/processed/`
- Each file is parseable JSONL, no schema violations
- No duplicate `chunk_id` within same law
- All `citation` fields follow Vietnamese legal format (e.g., "Luật ..., Điều ..., Khoản ..., Điểm ...")
- `hierarchy_path` correctly structured with null for missing levels
- `parent_id` and `parent_text` present and consistent
- `source_domain`, `source_type`, `text_hash` present
- `issued_date`, `effective_date`, `expiry_date` properly formatted
- Zero empty `text` fields

**Status**: Complete and validated.

**Detailed documentation**: `docs/processed_jsonl.md`

---

### Phase 8 — Embedding & Indexing

**Goal**: Create BGE-M3 dense embeddings from child chunks and build the Qdrant
dense index used by retrieval.

**Input**: `data/processed/*.jsonl` (only runs after validation passes).

**Pipeline Summary**:
- Embedding model selection: `BAAI/bge-m3`
- Batch embedding generation with async workers
- Vector schema:
  - `vector`: dense embedding (float32[1024])
  - sparse vectors are not stored in the current Qdrant collection
  - `payload`: full chunk metadata including: `law_id`, `law_name`, `law_type`, `legal_status`, `article_number`, `article_title`, `clause_number`, `point_label`, `hierarchy_path`, `citation`, `effective_date`, `issued_date`, `expiry_date`, `source_url`, `source_domain`, `source_type`, `parent_id`, `parent_text`, `text_hash`, `metadata`
- Vector store: Qdrant dense index
- Metadata filtering: filter by `law_id`, `effective_date` ranges, article ranges
- Effective-date filtering: future/not adopted in the final evaluated pipeline
- Source traceability: each vector payload contains full `source_url` and `citation`
- Index refresh strategy: incremental updates for new laws, periodic full reindex

**Output**: Qdrant collection `vnlaw_chunks_bgem3_v1_full` with 40,389 points
across 52 legal documents.

**Validation Criteria**:
- Collection size matches total chunks (no missing vectors)
- Dense search works with payload metadata. Sparse BM25 and RRF fusion are
  implemented outside the current Qdrant vector collection.
- Metadata filters work correctly (filter by law_id, effective_date)
- Retrieval latency < target (e.g., <100ms p95)
- Point-in-time effective date filtering is not adopted yet.

**Status**: Complete and validated.

**Detailed documentation**: `docs/embedding_indexing.md`

---

### Phase 9 — Naive RAG

**Goal**: Build baseline RAG system with single retriever, strict citation, fallback, and initial evaluation.

**Input**: Qdrant index, processed JSONL, LLM client.

**Pipeline Summary**:
- User query → embedding → Qdrant hybrid search → retrieve top-k chunks (k=5-10)
- Context packing: concatenate `parent_text` + `text` from top-k, prepend citation anchors
- Strict generation prompt:
  - "Answer using ONLY provided context"
  - "Cite every fact with exact citation format: Điều X, Khoản Y, Điểm Z"
  - "If context insufficient, respond with fallback message"
- LLM Generator: configured LLM provider with legal prompt
- Citation validator: check answer mentions exist in retrieved context
- Fallback: if confidence < 0.75 or no retrieved chunks match query intent → fallback response

**Output**: Vietnamese legal answer with citations, or fallback message.

**Validation Criteria**:
- 100% citations traceable to retrieved chunks (no hallucinated citations)
- Fallback triggered when context is irrelevant
- Baseline evaluation on golden QA dataset (answer relevance > threshold)
- Latency < target (e.g., <2s end-to-end)

**Status**: Closed with known limitations. It remains the dense baseline, not
the final adopted workflow.

**Detailed documentation**: `docs/naive_rag.md`

---

### Phase 10 — Advanced RAG

**Goal**: Enhance retrieval quality with dense+sparse retrieval, fixed RRF
fusion, coverage-aware quota retrieval, strict evidence selection, citation
guarding, and answerability fallback.

**Input**: Query, Qdrant index.

**Pipeline Summary**:
- Multi-retriever:
  - Dense retrieval (vector similarity)
  - Sparse retrieval (BM25 on text)
  - Hybrid: combine with Reciprocal Rank Fusion (RRF)
- Reranking: evaluated separately with `BAAI/bge-reranker-v2-m3` but not
  adopted.
- Confidence and fallback behavior: answer only from selected citable child
  evidence; fallback when evidence is insufficient.
- Citation validation: cross-check citations in answer against retrieved context
- Time-aware retrieval: future/not adopted.
- Output: reordered, confidence-scored chunks

**Output**: Top-k coverage-aware retrieval results and selected citable child
evidence for strict generation.

**Validation Criteria**:
- Retrieval metrics on frozen benchmark `v0.1.0`.
- Strict generation metrics with citation ID guard.
- Safe fallback behavior for expected `fallback_required` cases.

**Status**: Implemented and evaluated. Final adopted retrieval is
`coverage_aware_quota`. Reranking was not adopted.

**Detailed documentation**: `docs/advanced_rag.md`

---

### Phase 11 — GraphRAG & Agents

**Goal**: Implement legal knowledge graph for multi-hop reasoning and agent orchestration (only after Naive & Advanced RAG are stable).

**Input**: Parsed hierarchy, cross-references, Neo4j.

**Pipeline Summary**:
- Legal graph nodes:
  - `Law`: law metadata
  - `Article`: Điều
  - `Clause`: Khoản
  - `Point`: Điểm
  - `Entity`: organizations, people, procedures
  - `Penalty`: punishments, fines
- Legal graph edges:
  - `BELONGS_TO` (child → parent)
  - `REFERENCES` (this Article references another)
  - `AMENDS` (newer law amends older)
  - `SUPERSEDES` (replaces obsolete)
  - `DEFINES` (Law defines a concept)
  - `RELATED_TO` (semantic similarity)
- Graph traversal: from retrieved Article → traverse REFERENCES → fetch related provisions
- Vector explorer: combine graph results with vector retrieval
- Orchestrator: merge evidence from multiple retrievers (vector + graph) → context packing → LLM
- Agent routing: intent classification → graph-only, vector-only, or hybrid

**Output**: Graph-augmented context, multi-hop answers.

**Validation Criteria**:
- Cross-reference accuracy (AMENDS/SUPERSEDES tracking is correct)
- Multi-hop reasoning produces correct synthesized answers
- Graph traversal does not create cycles or infinite loops
- Orchestrator merging does not hallucinate

**Status**: Future extension

**Detailed documentation**: `docs/graphrag_agents.md`

---

### Phase 12 — Evaluation

**Goal**: Evaluate system with comprehensive metrics, golden QA dataset, and CI gates.

**Input**: Test queries with ground truth answers/citations.

**Pipeline Summary**:
- Parser tests: unit tests for hierarchy parsing (Article/Clause/Point detection)
- Chunk validation tests: every chunk has valid citation
- Retrieval evaluation:
  - Article recall: % true articles retrieved
  - Clause recall: % true clauses retrieved
  - Citation exact match: retrieved citation matches ground truth
- Generation quality:
  - Faithfulness: answer is faithful to context
  - Answer relevance: answer addresses the question
  - Unsupported claim rate: % claims without context support
- Fallback evaluation:
  - Fallback precision: % fallback cases that are correct (should have fallen back)
  - Fallback recall: % cases needing fallback that did fallback
- System metrics:
  - Latency (p50, p95, p99)
  - Retrieval time, generation time
  - Regression detection: compared to baseline

**Output**: frozen benchmark reports, strict generation evaluation reports,
production smoke results, and diagnostics under the documented evaluation and
deployment report locations.

**Validation Criteria**:
- Frozen benchmark schema and splits remain reproducible.
- Retrieval and strict generation evaluations complete without runtime errors.
- Citation ID validity and answerability fallback policy are enforced.
- Production smoke validates runtime health, warmup/cache, and hybrid dense
  retrieval separately from benchmark quality.
- All CI gates pass before merge.

**Status**: Implemented for frozen benchmark, strict generation evaluation,
and production smoke validation.

**Detailed documentation**: `docs/evaluation.md`

---

### Phase 13 — API & Production Deployment

**Goal**: Package the system as a product API and run it in the accepted
production Vercel + Azure App Service container deployment.

**Input**: All components (retrieval, generation, validation).

**Pipeline Summary**:
- FastAPI backend:
  - `POST /api/v1/legal-qa/ask` returns answer, citations, evidence, warnings,
    request metadata, and request ID.
  - `GET /health` is a lightweight process liveness check.
  - `GET /api/v1/readiness` checks shallow production readiness, including
    Qdrant collection availability.
  - `GET /api/v1/legal-qa/warmup` loads and verifies the packaged BGE-M3 model
    and process-local encoder cache.
- Frontend:
  - Vercel production: `https://vnlaw-qa.vercel.app`.
  - Production API base URL points to the Azure backend.
- Backend production:
  - Azure App Service container:
    `https://vnlaw-backend-prod-phat.azurewebsites.net`.
  - ACR: `vnlawacrphat.azurecr.io`.
  - Current verified image:
    `vnlawacrphat.azurecr.io/vnlaw-backend:84880a47e7a84eafcb064a5d03613b5350e86d4f`.
- Retrieval runtime:
  - production mode is hybrid;
  - BGE-M3 is packaged at `/models/embedding/bge-m3`;
  - runtime uses offline Hugging Face settings;
  - dense retrieval uses BGE-M3 query embedding, `DenseRetriever`, and Qdrant;
  - sparse fallback is emergency/degraded resilience only.
- Error handling and logging: structured responses and sanitized timing logs;
  no raw stack traces, secrets, prompts, raw evidence text, or provider payloads
  in normal logs.

**Output**: FastAPI product API, Next.js product UI, production container
images in ACR, Azure App Service production backend, Vercel frontend, warmup
and Production Ask Smoke workflows.

**Validation Criteria**:
- `/health` returns 200.
- `/api/v1/readiness` returns ready with Qdrant collection available.
- Warmup passes and reports `cache_hit_after=true`; a second warmup reports
  cache reuse with `cache_hit_before=true`.
- Controlled ask/repeated ask smoke returns `decision=answered`, citations,
  `retrieval_mode=hybrid`, `dense_retrieval_used=true`, and `fallback_used=false`.
- Production Ask Smoke passes and remains strict on severe infrastructure or
  degraded retrieval warnings.
- Secret and protected-path checks remain clean.

**Status**: Implemented and production verified.

**Detailed documentation**: `docs/api_deployment.md`

---

### Phase 14 — MLOps & Maintenance

**Goal**: Keep system optimized, monitor quality, and handle corpus updates safely.

**Input**: Production infrastructure, corpus registry updates.

**Pipeline Summary**:
- Corpus update workflow:
  - New law added → update registry → recrawl → audit → process → embed → index
  - Versioned raw artifacts: `data/raw/v{version}/{law_id}/`
  - Processed data versioning: `data/processed/v{version}/`
  - Index refresh: incremental (add new vectors) + periodic full reindex
- CI/CD:
  - Automated tests: parser, chunk validation, retrieval smoke test
  - Regression evaluation: compared to previous version on golden QA
  - Deployment gates: all tests pass, evaluation metrics stable
- Monitoring:
  - Retrieval quality over time (sampled queries, human eval)
  - Citation accuracy drift detection
  - Latency SLOs
  - Error rate alerts
- Maintenance tasks: re-normalize old artifacts, re-embed with new model, graph updates

**Output**: CI quality gates, protected-path guard, lightweight secret scan,
container deployment workflow, production warmup/cache validation, Production
Ask Smoke workflow, Azure runbook, and corpus/index maintenance design notes.

**Validation Criteria**:
- CI stages pass before merge/deploy.
- Protected paths and secrets remain clean.
- Production deploys verify image, health, readiness, warmup/cache, and strict
  ask smoke.
- Dense fallback or severe retrieval warnings fail hybrid production smoke.
- Corpus/index refreshes remain separately scoped and must be run through
  controlled maintenance workflows.

**Status**: Partially implemented / ongoing. CI gates, container deployment,
runbooks, protected-path checks, secret scanning, warmup validation, repeated
ask validation, and Production Ask Smoke are implemented. Monitoring, alerts,
automated rollback, richer dashboards, and corpus/index refresh automation
remain future work.

**Detailed documentation**: Integrated into `docs/api_deployment.md`,
`docs/mlops_maintenance.md`, and future runbooks.

---

## 5. Validation Gates

Each phase must pass its gate before proceeding to the next.

| Gate | Required Evidence | Example Check | Why It Matters |
|------|-------------------|---------------|----------------|
| Setup gate | `pyproject.toml`, `AGENTS.md`, `mypy`/`pytest` pass | `uv run mypy src` → 0 errors | Code quality baseline |
| Registry gate | `configs/laws/corpus_registry.yml` with 52 entries | `grep -c "law_id:" configs/laws/corpus_registry.yml` = 52 | Ensures corpus scope is accurate |
| Crawling gate | 52 raw artifact directories | `ls data/raw/ | wc -l` = 52 | Raw data exists before processing |
| Raw audit gate | `artifacts/reports/audit/raw_corpus_audit.json` zero critical errors | Audit script exits 0 | Detect corrupted/missing artifacts early |
| Cleaning gate | All texts UTF-8, legal headings intact | Spot-check `Điều`, `Khoản`, `Điểm` readable | Input text quality affects parsing |
| Parsing gate | Parser tests: >99% Article detection | Unit tests on sample documents | Parser is foundation for chunking and retrieval |
| Chunking gate | Every chunk has valid `chunk_id` and `citation` | Validate all `chunks.jsonl` files | Citation integrity is mandatory for Legal QA |
| Processed Chunk Validation gate | 52 files, schema valid, zero duplicates | `pydantic` validation pass, duplicate check | Input stability for embedding |
| Indexing gate | Qdrant collection size matches chunks | Count vectors = total chunks | No data loss in embedding |
| Naive RAG gate | 100% citations traceable, fallback works | Eval: no hallucinated citations | Legal QA requires source grounding |
| Advanced RAG gate | Precision@k > Naive RAG baseline | Retrieval eval metrics improve | Actual quality improvement? |
| GraphRAG gate | Multi-hop accuracy > threshold | Human eval or golden QA | Graph traversal must be accurate, no hallucination |
| API/deployment gate | Health=200, security scan clean, load test pass | `curl /health`, OWASP scan, `hey` load test | Production readiness |

**Principles**:
- Crawling success alone is **not enough** — audit, cleaning, parsing quality gates must pass.
- No source means **no confident answer** — retrieval must return relevant, in-effect laws.
- No citation means **not a valid Legal QA answer** — every generated answer must cite exact Article/Clause/Point.

---

## 8. Pipeline-level Troubleshooting

| Issue | Possible Cause | How to Check | Recommended Fix |
|-------|----------------|--------------|-----------------|
| `corpus_registry.yml` count mismatch (≠52) | Registry not finalized, extra/missing entries | `grep -c "law_id:" configs/laws/corpus_registry.yml` | Reconcile with intended corpus list, ensure exactly 52 |
| Missing raw artifact directory | Crawl failed, network error, skipped law | `ls data/raw/` vs registry `law_id` list | Rerun crawler for missing `law_id`, check logs |
| Extra raw artifact directory | Stale data from previous crawl | `ls data/raw/` shows dirs not in registry | Remove dirs not in registry, or update registry if intended |
| `main.html` very small (<1KB) | Blocked page, captcha, login required, error page | `du -h data/raw/{law_id}/latest/main.html` | Inspect only targeted snippets, fix crawler headers/retry |
| Metadata `law_id` mismatch | Crawler saved wrong metadata | Check `data/raw/{law_id}/latest/metadata.json` vs registry | Fix crawler to use correct `law_id` from registry |
| Missing `source_url` in metadata | Crawler bug | Inspect metadata file | Ensure crawler populates all required fields from registry |
| Vietnamese text shows garbled characters | Wrong encoding, encoding not normalized | `file -I data/raw/{law_id}/latest/main.html` | Ensure crawler saves as UTF-8, cleaner normalizes Unicode |
| Parser fails to detect `Article` | Unusual numbering, regex too strict | Run parser on sample, check logs | Loosen regex patterns, handle edge cases (Roman, LaTeX-style) |
| Chunk has no `citation` field | Chunker didn't build citation properly | Inspect `chunks.jsonl` | Ensure chunker constructs citation from article/clause/point numbers |
| Duplicate `chunk_id` within same law | Chunker logic error, same clause parsed twice | Validate `chunk_id` uniqueness | Fix chunker to generate unique IDs, deduplicate |
| Retrieval returns wrong law (different `law_id`) | Metadata filter not applied, query ambiguous | Check retrieval query payload | Add strict `law_id` filter if context known, improve query embedding |
| Generated answer unsupported by context | LLM hallucination, prompt weak | Compare answer sentences with retrieved `text` | Strengthen prompt: "ONLY use provided context", add citation validator |
| GraphRAG gives irrelevant multi-hop path | Graph edges incorrect, traversal too broad | Inspect graph query, intermediate nodes | Validate `REFERENCES`/`AMENDS` edges, limit traversal depth |

---

## 9. Best Practices

- **Do not skip raw audit** — crawling success ≠ data quality. Audit catches corrupted/missing artifacts early.
- **Do not chunk by arbitrary character length** — legal documents have semantic units (Điều, Khoản, Điều). Breaking them destroys citations.
- **Preserve legal hierarchy from Phần → Chương → Mục → Điều → Khoản → Điểm** throughout the pipeline. Once lost, cannot recover.
- **Keep `source_url` and `citation` from raw data to final answer** — traceability is non-negotiable for Legal QA.
- **Prefer deterministic validation before LLM-based validation** — schema checks, duplicate detection, citation integrity are cheaper and more reliable than LLM judges.
- **Do not implement GraphRAG before Naive RAG and Advanced RAG are stable** — GraphRAG adds complexity; ensure baseline retrieval quality first.
- **Use small branches and small PRs** — each phase is a natural boundary. Merge often, keep diffs reviewable.
- **Keep docs updated after each phase** — `docs/` is source of truth for future contributors.
- **Avoid logging secrets or sensitive user queries** — PII in legal questions is common; strip or hash before logging.
- **Do not let LLM invent citations** — enforce citation validation: every cited Điều/Khoản/Điểm must exist in retrieved context. If not found, trigger fallback.
- **Validate encoding early** — Vietnamese Unicode issues cascade. Ensure UTF-8 throughout.
- **Respect effective dates** — a law may be amended or repealed. Filter by `effective_date` at retrieval time to avoid outdated provisions.

---

## 10. Changelog

### Version 0.2 (2026-06-01)

- Updated current status after Phase 4 Cleaning & Normalization became
  gate-ready.
- Updated the next immediate phase to Legal Hierarchy Parsing.
- Aligned paths with current repository layout: `configs/`, `scripts/`,
  `src/services/`, `src/ingestion/`, `data/raw/{law_id}/latest/`,
  `data/interim/`, and phase-specific `artifacts/reports/<phase>/`.

### Version 0.1 (2026-05-21)

- Added initial end-to-end pipeline overview.
- Documented current project status: registry 52 laws, crawling 52/52 complete.
- Defined Phase 3 Raw Corpus Audit & Validation as the next immediate phase at
  that time.
- Detailed Phase 0–14 with Goal/Inputs/Pipeline Summary/Outputs/Validation Criteria/Status/Documentation.
- Added Current Implementation Status table (all 14 phases).
- Added Recommended Branch Roadmap with validation gates per branch.
- Added Validation Gates table (13 gates with required evidence, checks, rationale).
- Added Pipeline-level Troubleshooting table (15 common issues with fixes).
- Added Best Practices (12 practical rules).
- Added Related Documentation index (existing/planned/future).

---

## 11. Related Documentation

| Document | Status | Description |
|----------|--------|-------------|
| `docs/project_phase_journal.md` | Existing | Project phase journal and pipeline notes |
| `docs/raw_data_crawling.md` | Existing | Raw data crawling phase details |
| `docs/project_setup.md` | Existing | Project setup, tooling, standards |
| `docs/corpus_registry.md` | Existing | Corpus registry schema and maintenance |
| `docs/raw_corpus_audit.md` | Existing | Raw artifact audit procedure |
| `docs/cleaning_normalization.md` | Existing | HTML-to-text, Unicode, whitespace handling |
| `docs/legal_parsing.md` | Implemented | Legal hierarchy parsing algorithm and edge cases |
| `docs/parent_child_chunking.md` | Implemented | Parent-child chunking design, chunk schema, and citation construction |
| `docs/processed_jsonl.md` | Existing | JSONL export schema and validation |
| `docs/embedding_indexing.md` | Implemented | BGE-M3 dense index and Qdrant validation |
| `docs/naive_rag.md` | Implemented baseline | Baseline RAG implementation |
| `docs/advanced_rag.md` | Implemented and evaluated | Coverage-aware hybrid retrieval and strict generation |
| `docs/graphrag_agents.md` | Future extension | Legal graph schema, traversal, agent orchestration |
| `docs/evaluation.md` | Implemented | Benchmark metrics, strict generation evaluation, diagnostics |
| `docs/api_deployment.md` | Implemented production backend | FastAPI endpoints, Azure container deployment, Vercel integration, security notes |
| `docs/mlops_maintenance.md` | Partially implemented / ongoing | Corpus updates, index refresh, monitoring, runbooks |

**Legend**: future/separately scoped means design notes exist, but the feature
is not part of the adopted evaluated pipeline.

---

## Appendix: Phase Status Summary

### Phase 0 — Project Setup & Principles — Implemented

### Phase 1 — Legal Corpus Registry — Implemented

### Phase 2 — Registry-driven Crawling — Implemented (52/52 laws crawled successfully)

### Phase 3 — Raw Corpus Audit & Validation — Implemented

### Phase 4 — Cleaning & Normalization — Implemented and gate-ready

Final Cleaning & Normalization validation produced 52/52 normalized artifacts
and 52/52 optional cleaned text artifacts. The cleaner removes known TVPL
encoded footer/watermark artifacts and reports article references separately
from real article headings.

### Phase 5 — Legal Hierarchy Parsing — Complete and Hardened

Full-corpus run:

```text
Total documents: 52
Success: 6
Success with warnings: 46
Failed: 0
Validator failures: 0
RED: 0
ORANGE: 0
Source-tail leakage: 0
AMBIGUOUS_CLAUSE_CANDIDATE: 0
POINT_LIKE_LINE_OUTSIDE_CLAUSE: 0
Output: data/interim/{LAW_ID}/hierarchy.json
Report: artifacts/reports/parsing/legal_parsing_report.json
```

Remaining warnings are accepted non-blocking caveats for Phase 6 chunk
validation: SOURCE_NOTE_EXCLUDED, EMPTY_ARTICLE_NODE,
NODE_ID_COLLISION_RESOLVED, ARTICLE_COUNT_MISMATCH,
MAX_ARTICLE_NUMBER_MISMATCH.
### Phase 6 — Parent-child Chunking — Complete and hardened

### Phase 7 — Processed Chunk Validation & Embedding Readiness — Complete

### Phase 7.5 — LLM-Assisted Corpus Audit & Context Refresh — Complete

Decision: Go with watch items. Historical semantic-audit details are preserved
in project history; current status is summarized in `PROJECT_CONTEXT.md`.

### Phase 8 — Embedding & Indexing — Complete and validated

All 40,389 validated chunks are indexed in Qdrant collection
`vnlaw_chunks_bgem3_v1_full` using `BAAI/bge-m3`, named dense vector `dense`,
dimension 1024, cosine distance, and deterministic UUIDv5 point IDs. Full
schema, payload, vector, filter, and retrieval sanity validation passed.

### Phase 9 — Retrieval / Naive RAG — Closed

The Naive RAG baseline was implemented, evaluated, and closed with known
limitations. It remains a historical comparator and is not the current
production retrieval path.

### Phase 10 — Advanced RAG — Implemented and productionized

Final adopted retrieval is `coverage_aware_quota`. Production retrieval mode is
hybrid: BGE-M3 query embedding, `DenseRetriever`, Qdrant dense retrieval, local
BM25 sparse retrieval, fixed RRF fusion, coverage-aware quota retrieval,
evidence selection, and strict generation. Reranking was evaluated but not
adopted in current production. Time-aware filtering is not adopted. Sparse-only
is not production mode; sparse remains emergency/degraded fallback only.

### Phase 11 — GraphRAG & Agents — Future extension

GraphRAG and multi-agent retrieval are future extensions and are not in the
current production path.

### Phase 12 — Evaluation — Implemented

Frozen benchmark evaluation and strict generation checks are implemented.
Production smoke checks are also implemented for deployment/runtime validation.
Benchmark evaluation and production smoke have different purposes: benchmark
results measure retrieval/generation quality, while production smoke validates
health, readiness, BGE-M3 warmup/cache, dense retrieval, fallback absence, and
safe runtime behavior.

### Phase 13 — API & Production Deployment — Implemented

The FastAPI backend is productionized as an Azure App Service Linux container
served from Azure Container Registry. Vercel production is integrated with the
accepted Azure backend at
`https://vnlaw-backend-prod-phat.azurewebsites.net`. Production health,
readiness, warmup, repeated ask smoke, and GitHub Production Ask Smoke pass.
The current verified production image is
`vnlawacrphat.azurecr.io/vnlaw-backend:84880a47e7a84eafcb064a5d03613b5350e86d4f`.
Render is legacy/deprecated/rollback-only context, not current production.

### Phase 14 — MLOps & Maintenance — Partially implemented / ongoing

CI quality gates, protected-path checks, lightweight secret scanning, fake-mode
container health smoke, production container deployment, warmup validation, and
Production Ask Smoke are implemented. The Azure runbook documents rollback and
the observed reliable stop/start procedure for large backend image recycle.
Remaining future work includes richer production monitoring, alerts, automated
rollback, dashboards, and long-term corpus/index maintenance automation.
