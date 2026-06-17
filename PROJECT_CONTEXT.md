# VnLaw-QA Project Context

This file is the canonical current-state summary for repository contributors and coding assistants.

## 1. Project Goal

VnLaw-QA is a Vietnamese legal question-answering and retrieval-augmented generation system designed around:

- trusted legal sources;
- preserved legal hierarchy;
- source traceability;
- citation integrity;
- safe fallback when evidence is insufficient;
- reproducible evaluation.

It is not a generic chatbot and is not a replacement for professional legal advice.

## 2. Canonical Architecture

```text
Corpus Registry
→ Registry-driven Crawling
→ Raw Corpus Audit
→ Cleaning / Normalization
→ Legal Hierarchy Parsing
→ Parent-child Chunking
→ Processed Chunk Validation
→ Embedding / Qdrant Indexing
→ Dense Retrieval
→ Evidence Construction and Selection
→ Fallback-aware Naive RAG
→ Generation Evaluation
→ Manual Faithfulness Review
→ Offline Quality Gate
→ Benchmark-first Advanced Retrieval
→ GraphRAG / Agents
→ API / Deployment
→ MLOps / Maintenance
```

Repository layout:

```text
scripts/
  corpus/       # corpus pipeline CLI entrypoints
  indexing/     # embedding/Qdrant CLI entrypoints
  retrieval/    # retrieval, Naive RAG, evaluation, and QA CLI entrypoints

src/
  ingestion/    # registry, crawl, audit, cleaning, storage
  processing/   # hierarchy parsing, chunking, JSONL validation
  indexing/     # embedding and Qdrant indexing/validation
  retrieval/    # dense retrieval, evidence, selection, generation, evaluation, review, quality gate
  services/     # existing orchestration services
  api/          # future/separately scoped
  evaluation/   # future broader evaluation layer
  monitoring/   # future/separately scoped
  security/     # future/separately scoped
```

Scripts are thin wrappers. Reusable logic belongs under `src/`.

## 3. Core Legal RAG Principles

- No trusted source → no confident answer.
- No traceable citation → not a valid legal answer.
- Preserve hierarchy: Phần → Chương → Mục → Điều → Khoản → Điểm.
- Prefer consolidated legal documents (`VBHN`) when available.
- Do not invent laws, articles, clauses, points, procedures, penalties, or citations.
- Auxiliary parent context is not directly citable evidence.
- If the selected evidence is incomplete or unsafe, use fallback instead of guessing.
- Citation-ID integrity is separate from semantic faithfulness.
- Raw data is immutable; derived data is written separately.

Default trusted source:

```text
https://thuvienphapluat.vn
```

## 4. Completed Corpus and Indexing Foundation

### Corpus registry and ingestion

- Registry: `configs/laws/corpus_registry.yml`.
- Legal documents: 52.
- Crawled: 52/52.
- Raw audit: 52/52 passed.
- Cleaned outputs: 52/52 under `data/interim/{LAW_ID}/normalized.json`.

### Legal parsing and chunking

- Parsed hierarchy artifacts: 52/52.
- Parsed outputs: `data/interim/{LAW_ID}/hierarchy.json`.
- Processed corpus: `data/processed/legal_chunks.jsonl`.
- Valid chunks: 40,389.
- Invalid chunks: 0.
- Duplicate chunk IDs: 0.
- Hard validation errors: 0.
- Accepted non-blocking warnings remain visible.

Chunk design:

- child unit: Clause or Point where available;
- parent unit: Article;
- embedding content: `text`;
- contextual payload: `parent_text`;
- arbitrary character-window chunking is not used.

### Embedding and indexing

- Embedding model: `BAAI/bge-m3`.
- Qdrant collection: `vnlaw_chunks_bgem3_v1_full`.
- Points: 40,389.
- Vector name: `dense`.
- Dimension: 1024.
- Distance: cosine.
- Sparse indexing: not enabled in the current baseline.
- Full count/schema/payload/vector/filter validation passed.

## 5. Naive RAG Baseline Status

Phase 9 is closed with known limitations.

Implemented capabilities:

- typed dense retrieval from Qdrant;
- warning-aware and hierarchy-aware payload handling;
- evidence bundle construction;
- evidence safety and selection gate;
- `answer_allowed` versus fallback decisions;
- OpenRouter-backed generation through a provider-neutral client contract;
- selected-evidence-only prompting;
- safe Vietnamese fallback without an LLM call;
- citation-ID guard;
- repeatable generation evaluation;
- bounded evidence previews for manual review;
- manual claim-to-citation verdicts;
- prompt scope and complete-list hardening;
- configurable offline quality gate.

Current quality-gate result:

```text
quality_gate_passed
```

Current gate summary:

- hard violations: 0;
- quality violations: 0;
- remaining warnings: 2;
- warnings belong to the non-blocking `marriage_conditions_generation` case.

The annual-leave control remains a correct fallback case:

```text
decision = fallback_required
llm_called = false
```

Detailed technical documentation:

```text
docs/naive_rag.md
```

## 6. Current Evaluation Assets

Durable evaluation inputs:

```text
data/eval/manual_retrieval_queries.jsonl
data/eval/manual_naive_rag_generation_queries.jsonl
data/eval/manual_faithfulness_verdicts.json
configs/retrieval/quality_gate.yml
```

Reusable CLIs:

```text
scripts/retrieval/run_dense_retrieval.py
scripts/retrieval/evaluate_dense_retrieval.py
scripts/retrieval/run_selection_smoke.py
scripts/retrieval/run_naive_rag.py
scripts/retrieval/evaluate_naive_rag_generation.py
scripts/retrieval/export_naive_rag_manual_review.py
scripts/retrieval/evaluate_quality_gate.py
```

The current five-case generation suite is a regression and safety suite. It has already been used to inspect failures, harden prompting, and validate the quality gate.

It is not a held-out benchmark for claiming broad Vietnamese legal QA quality or for proving that an advanced retrieval system is better than the Naive RAG baseline.

## 7. Known Limitations

1. The reviewed generation suite contains only five cases.
2. The suite is suitable for regression, not broad generalization.
3. `marriage_conditions_generation` remains partial/non-blocking.
4. Complete-list questions require fuller evidence coverage.
5. Dense-only retrieval still falls back for the annual-leave control case.
6. Citation-ID validity does not guarantee semantic faithfulness.
7. Model output may vary across runs.
8. The current system is not production-ready legal advice.
9. Sparse retrieval, fusion, and reranking have not yet been evaluated on a frozen comparative benchmark.

## 8. Current Next Stage

The next stage should be benchmark-first Advanced RAG work.

Do not begin by immediately adding hybrid retrieval. First establish a controlled comparison framework.

Recommended sequence:

```text
1. Build a broader reviewed legal retrieval/QA benchmark.
2. Define and freeze development and held-out test splits.
3. Run the current Naive RAG baseline on the frozen benchmark.
4. Implement sparse retrieval and controlled dense+sparse fusion.
5. Evaluate hybrid retrieval on the development split.
6. Add reranking only as a separate ablation.
7. Run the final comparison once on the held-out test split.
8. Compare quality, safety, latency, and cost.
```

If no model is trained, use development and held-out test splits.

If embedding, reranking, routing, or rewriting models are trained/fine-tuned, introduce train/validation/test splits.

## 9. Comparative Evaluation Requirements

Naive and advanced systems should use the same:

- legal corpus;
- chunking;
- Qdrant snapshot;
- queries;
- generator model;
- prompt;
- evidence-selection policy;
- fallback policy;
- evaluation code.

Only the component under study should change.

Recommended retrieval metrics:

- Recall@k;
- MRR@k;
- NDCG@k;
- exact law/article/clause hit rate;
- complete evidence coverage rate;
- irrelevant evidence rate.

Recommended answer/safety metrics:

- answer-allowed precision;
- fallback precision/recall;
- citation-ID coverage;
- claim support rate;
- unsupported-claim rate;
- too-broad-claim rate;
- missing-key-condition rate;
- complete-list accuracy;
- blocking-case pass rate.

Recommended system metrics:

- retrieval latency;
- reranking latency;
- total response latency;
- token usage;
- cost;
- memory;
- throughput.

## 10. Immediate Tasks

1. Keep Phase 9 documentation consolidated in `docs/naive_rag.md`.
2. Preserve the current five-case suite as a regression suite.
3. Design a broader reviewed benchmark without inventing legal expectations.
4. Freeze development and test splits before tuning advanced retrieval.
5. Record a reproducible Naive RAG baseline on the frozen benchmark.
6. Scope hybrid retrieval and reranking as controlled ablations.
7. Continue carrying forward the marriage-condition completeness warning.

## 11. Out of Scope Until Explicitly Requested

- GraphRAG and agents.
- FastAPI and production API contracts.
- UI implementation.
- Authentication and user management.
- Fine-tuning.
- Production deployment.
- Monitoring/MLOps implementation.
- Re-indexing the validated corpus.
- Mutating protected corpus paths.

## 12. Protected Paths and Runtime State

Do not mutate without an explicitly scoped official rerun:

```text
data/raw/
data/interim/
data/reports/
data/processed/legal_chunks.jsonl
```

Do not commit:

- Qdrant storage;
- Hugging Face/model caches;
- virtual environments;
- Python caches;
- generated runtime evaluation reports;
- local secrets.

Qdrant should be read-only unless a task explicitly scopes indexing or collection migration.

## 13. Important Paths

```text
AGENTS.md
PROJECT_CONTEXT.md
.codex/context/INSTRUCTION_INDEX.md
.agents/skills/README.md
.agents/skills/SKILL_INDEX.md
configs/laws/corpus_registry.yml
configs/retrieval/quality_gate.yml
data/processed/legal_chunks.jsonl
data/eval/
artifacts/reports/indexing/
src/ingestion/
src/processing/
src/indexing/
src/retrieval/
scripts/corpus/
scripts/indexing/
scripts/retrieval/
docs/naive_rag.md
docs/advanced_rag.md
docs/evaluation.md
```

## 14. Core Commands

### Test and lint

```bash
uv run pytest
uv run ruff check src scripts tests
uv run ruff format --check src scripts tests
uv lock --check
git diff --check
```

### Run Naive RAG

```bash
uv run --extra qdrant --extra embedding python \
  scripts/retrieval/run_naive_rag.py \
  --query "Trẻ em dưới 6 tuổi được hưởng bảo hiểm y tế như thế nào?" \
  --collection-name vnlaw_chunks_bgem3_v1_full \
  --url http://localhost:6333 \
  --top-k 20 \
  --device cpu \
  --provider openrouter
```

### Run generation evaluation

```bash
uv run --extra qdrant --extra embedding python \
  scripts/retrieval/evaluate_naive_rag_generation.py \
  --queries data/eval/manual_naive_rag_generation_queries.jsonl \
  --collection-name vnlaw_chunks_bgem3_v1_full \
  --url http://localhost:6333 \
  --top-k 20 \
  --device cpu \
  --provider openrouter \
  --include-evidence-preview \
  --evidence-preview-chars 500 \
  --output artifacts/reports/retrieval/naive_rag_generation_eval.json
```

### Run offline quality gate

```bash
uv run python scripts/retrieval/evaluate_quality_gate.py \
  --generation-report artifacts/reports/retrieval/naive_rag_generation_eval.json \
  --faithfulness-verdicts data/eval/manual_faithfulness_verdicts.json \
  --policy configs/retrieval/quality_gate.yml \
  --output artifacts/reports/retrieval/quality_gate.json
```

Runtime reports under `artifacts/reports/` should remain ignored unless explicitly designated as durable artifacts.

## 15. Roadmap

| Stage | Status |
| --- | --- |
| Corpus registry, crawl, audit, cleaning | Complete |
| Legal hierarchy parsing and parent-child chunking | Complete |
| Processed JSONL validation and corpus audit | Complete |
| BGE-M3 embedding and dense Qdrant indexing | Complete |
| Dense retrieval and fallback-aware Naive RAG | Complete |
| Generation evaluation, faithfulness review, prompt hardening, quality gate | Complete |
| Phase 9 closure | Complete with known limitations |
| Benchmark construction and frozen split | Next |
| Advanced retrieval comparison | Future / next stage |
| GraphRAG and agents | Future |
| API and UI | Future |
| Deployment and MLOps | Future |

Branch guidance:

```text
feature/data-crawling           done
feature/raw-corpus-audit        done
feature/cleaning-normalization  done
feature/legal-parser-chunking   done
feature/processed-jsonl         done
feature/embedding-indexing      done
feature/naive-rag               done
feature/advanced-rag            next
feature/graphrag-agents         future
feature/evaluation              future
feature/api-deployment          future
```
