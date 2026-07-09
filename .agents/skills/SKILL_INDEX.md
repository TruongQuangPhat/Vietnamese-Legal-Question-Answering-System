# VnLaw-QA Codex Skill Index

Use this index before modifying domain-specific code, configuration, tests, or documentation. Skills under `.agents/skills/` are the primary repository-specific guidance sources.

This file is a task router. It does not replace the canonical repository state or repository-wide instructions.

## Instruction Order

Before modifying the repository, read sources in this order:

1. `AGENTS.md`
2. `PROJECT_CONTEXT.md`
3. `.codex/context/INSTRUCTION_INDEX.md` when instruction routing matters
4. `.agents/skills/SKILL_INDEX.md`
5. Relevant `.agents/skills/<skill-name>/SKILL.md` files
6. Relevant implementation, tests, configuration, and documentation

When sources disagree:

* `AGENTS.md` defines repository-wide rules.
* `PROJECT_CONTEXT.md` defines the current project state and roadmap.
* Skill files provide task-specific implementation guidance.
* Generated reports, historical trackers, stale mirrors, and old phase notes are not authoritative.

Do not maintain manual mirrors of `AGENTS.md` or `PROJECT_CONTEXT.md`.

## Task-to-Skill Routing

| Task type                                                                                  | Read these skills                                                                                                                      |
| ------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| Mission, roadmap, current priorities, or workflow boundaries                               | `vnlaw-project-charter`, `vnlaw-workflow-review`                                                                                       |
| Repository layout, module ownership, or architectural boundaries                           | `vnlaw-project-structure`, `vnlaw-oop-code-quality`                                                                                    |
| Corpus registry or legal source changes                                                    | `vnlaw-source-corpus`, `vnlaw-data-ingestion`, `vnlaw-legal-accuracy`                                                                  |
| Crawling or raw artifact handling                                                          | `vnlaw-data-ingestion`, `vnlaw-source-corpus`, `vnlaw-security-secrets`                                                                |
| Cleaning HTML or normalizing Vietnamese legal text                                         | `vnlaw-cleaning-normalization`, `vnlaw-legal-accuracy`                                                                                 |
| Cleaning quality audit or normalization improvements                                       | `vnlaw-cleaning-normalization`, `vnlaw-evaluation-cicd`, `vnlaw-legal-accuracy`                                                        |
| Legal hierarchy parsing or chunk creation                                                  | `vnlaw-legal-parsing-chunking`, `vnlaw-legal-accuracy`                                                                                 |
| Processed chunk validation or embedding readiness                                          | `vnlaw-legal-parsing-chunking`, `vnlaw-embedding-indexing`, `vnlaw-evaluation-cicd`, `vnlaw-legal-accuracy`                            |
| Embedding chunks or configuring Qdrant                                                     | `vnlaw-embedding-indexing`, `vnlaw-retrieval-search-reranking`, `vnlaw-security-secrets`                                               |
| Dense retrieval, BM25 sparse retrieval, filters, fusion, or controlled reranking ablations | `vnlaw-retrieval-search-reranking`, `vnlaw-advanced-rag`, `vnlaw-legal-accuracy`                                                       |
| Naive RAG baseline maintenance or comparison                                               | `vnlaw-naive-rag`, `vnlaw-context-engineering`, `vnlaw-llm-generation`, `vnlaw-legal-accuracy`                                         |
| Benchmark data, splits, qrels, annotation, or comparative evaluation                       | `vnlaw-evaluation-cicd`, `vnlaw-advanced-rag`, `vnlaw-legal-accuracy`, `vnlaw-workflow-review`                                         |
| Advanced RAG final workflow, experiments, or controlled ablations                          | `vnlaw-advanced-rag`, `vnlaw-retrieval-search-reranking`, `vnlaw-context-engineering`, `vnlaw-evaluation-cicd`, `vnlaw-legal-accuracy` |
| Graph traversal, GraphRAG, or multi-agent retrieval                                        | `vnlaw-graphrag-agents`, `vnlaw-legal-accuracy`, `vnlaw-workflow-review`                                                               |
| Prompting, evidence packets, answer format, or citation behavior                           | `vnlaw-context-engineering`, `vnlaw-llm-generation`, `vnlaw-legal-accuracy`                                                            |
| Public legal answer behavior                                                               | `vnlaw-legal-accuracy`, `vnlaw-llm-generation`, `vnlaw-context-engineering`                                                            |
| FastAPI or backend service work                                                            | `vnlaw-api-backend`, `vnlaw-oop-code-quality`, `vnlaw-security-secrets`                                                                |
| Tests, metrics, release gates, regression checks, or CI                                    | `vnlaw-evaluation-cicd`, `vnlaw-workflow-review`                                                                                       |
| Secrets, PII, logs, database exposure, or Docker security                                  | `vnlaw-security-secrets`                                                                                                               |
| Documentation, docstrings, or repository guidance                                          | `vnlaw-docstrings-documentation`, `vnlaw-oop-code-quality`                                                                             |
| Pull-request review, cross-workflow changes, or scope validation                           | `vnlaw-workflow-review`, `vnlaw-project-charter`                                                                                       |

## Current Workflow Discipline

The canonical current state is defined in `PROJECT_CONTEXT.md`.

The following foundations are complete and validated:

* corpus registry;
* registry-driven crawling;
* raw corpus audit;
* cleaning and normalization;
* legal hierarchy parsing;
* parent-child chunking;
* processed chunk validation;
* BGE-M3 dense embedding;
* Qdrant dense indexing;
* dense retrieval;
* local BM25 sparse retrieval;
* RRF fusion;
* coverage-aware quota retrieval;
* evidence construction and selection;
* fallback-aware Naive RAG baseline;
* strict legal generation;
* citation ID guard;
* answerability fallback guard;
* optional PostgreSQL conversation-store validation with guarded smoke and
  database integration tests;
* retrieval evaluation;
* strict generation evaluation;
* workflow-level integration tests for corpus, retrieval, evaluation, and
  guarded database validation.

Current benchmark state:

```text
benchmark = v0.1.0
total queries = 128
development split = 85
held-out test split = 43
answer_allowed = 110
fallback_required = 18
held-out test = reporting-only
```

Current adopted retrieval strategy:

```text
coverage_aware_quota
dense_candidate_k = 50
sparse_candidate_k = 50
final_top_k = 10
rrf_k = 60
dense_weight = 1.0
sparse_weight = 1.5
quota = fused_best 5, sparse_quota 4, dense_quota 1
```

Current adopted strict generation workflow:

```text
coverage-aware hybrid retrieval
→ evidence selection
→ strict legal generation
→ citation ID guard
→ answerability fallback guard
```

Latest Advanced RAG strict generation report:

```text
artifacts/reports/evaluation/advanced_rag/strict_generation_evaluation_answer_policy_refresh_20260708_235500
decision_accuracy = 0.8671875
fallback_required_fallback_rate = 1.0
citation_id_validity_rate = 1.0
retrieval_error_count = 0
generation_error_count = 0
```

For authenticated Qdrant Cloud evaluation, use `QDRANT_API_KEY` from the
private environment. Real benchmark runs require explicit user approval, unique
output directories, and fixed historical reports must not be overwritten.
Naive RAG remains a historical baseline unless explicitly rerun. Latency
comparisons require the same runtime environment.

Reranking was evaluated as a controlled ablation but was not adopted.

API/backend and UI infrastructure are deployed separately from the adopted
evaluated pipeline; see `PROJECT_CONTEXT.md` and `docs/api_deployment.md` for
current status and limitations. GraphRAG, multi-agent retrieval, time-aware
filtering, fine-tuning, monitoring, and MLOps infrastructure remain future or
separately scoped unless the user explicitly requests them.

If a task crosses the current workflow boundary:

1. Read `vnlaw-workflow-review`.
2. Identify the boundary explicitly.
3. Preserve current validated behavior.
4. Keep the change separately scoped.
5. Do not implement future components implicitly.

## Baseline and Final Workflow Preservation Rules

Unless a task explicitly scopes a change, preserve:

* the validated legal corpus;
* `data/processed/legal_chunks.jsonl`;
* benchmark/qrels/evidence group data;
* the existing Qdrant collection;
* dense embeddings;
* BM25 sparse retrieval behavior;
* RRF behavior;
* coverage-aware quota retrieval behavior;
* prompt behavior;
* evidence-selection behavior;
* fallback behavior;
* citation-ID guard behavior;
* answerability fallback guard behavior;
* Naive RAG baseline behavior;
* existing unit and integration tests;
* official evaluation artifacts.

Do not weaken safety or quality thresholds merely to make a new experiment pass.

Do not refactor completed retrieval or generation logic as a side effect of documentation, evaluation, API, GraphRAG, or future-work tasks.

Comparative evaluation logic should use `src/evaluation/` where appropriate while existing RAG and retrieval regression logic remains in its current owning modules.

## Legal Accuracy Requirements

All tasks involving legal data, retrieval, evidence, prompting, generation, or evaluation must preserve these invariants:

* No trusted source means no confident legal answer.
* No traceable citation means the answer is not a valid legal answer.
* Never fabricate laws, articles, clauses, points, procedures, penalties, effective dates, or citations.
* Preserve the hierarchy: `Phần → Chương → Mục → Điều → Khoản → Điểm`.
* Prefer consolidated documents (`VBHN`) when available.
* Auxiliary parent context is not directly citable.
* Selected child evidence must support the legal claim.
* Insufficient, incomplete, unsafe, parent-only, or indirectly relevant evidence must use fallback.
* Citation-ID validity does not prove semantic faithfulness.
* The system supports legal research and must not be represented as a replacement for professional legal advice.

## Functional Naming Rule

Phase labels are allowed in roadmap and historical documentation, but they must not be encoded into active implementation identifiers.

Do not use phase labels in:

* source filenames;
* script filenames;
* configuration filenames;
* dataset filenames;
* artifact filenames;
* test filenames;
* class names;
* function names;
* variable names;
* schemas;
* statuses;
* report metadata;
* CLI paths;
* public APIs.

Use functional names such as:

```text
legal_qa_benchmark.yml
validate_benchmark.py
BenchmarkValidator
retrieval_comparison_report.json
coverage_aware_quota
strict_generation_evaluation
answerability_fallback_guard
quality_gate_passed
```

## Protected Paths and Runtime Safety

Do not mutate these paths unless the task explicitly requires an official pipeline rerun:

```text
data/raw/
data/interim/
data/reports/
data/processed/legal_chunks.jsonl
data/eval/
artifacts/reports/evaluation/
```

Unless explicitly scoped:

* do not recreate or delete Qdrant collections;
* do not upsert points;
* do not update Qdrant payloads;
* do not re-index the corpus;
* do not re-embed the corpus;
* do not overwrite benchmark, qrels, or evidence group data;
* do not overwrite official evaluation artifacts;
* do not commit Qdrant storage;
* do not commit model caches;
* do not commit virtual environments or generated caches;
* do not print, log, or serialize secrets;
* do not write API keys into reports;
* do not call external LLM services for work that can be completed offline;
* do not run real embedding, reranking, Qdrant, or full benchmark workflows unless explicitly scoped.

## Repository Architecture

Scripts must remain thin wrappers.

```text
scripts/
  corpus/
  indexing/
  retrieval/
  evaluation/

src/
  core/
  ingestion/
  processing/
  services/
  indexing/
  retrieval/
  generation/
  evaluation/
  api/
  monitoring/
  security/
```

Use the existing repository layout rather than creating parallel abstractions.

Reusable logic belongs under `src/`. CLI scripts should be limited to:

* argument parsing;
* dependency construction;
* calling reusable services;
* concise output;
* documented exit codes.

Before introducing a new module, check whether an existing module already owns that responsibility.

## Evaluation Discipline

Before claiming that a new system improves over the current baseline or final adopted workflow:

1. Define the dataset, split, and benchmark version.
2. Keep development and held-out test split semantics clear.
3. Keep held-out test reporting-only and do not tune on it.
4. Preserve corpus, chunking, prompt, selection, fallback, and evaluation code unless the task explicitly scopes a broader comparison.
5. Tune retrieval or generation changes only on development data.
6. Run final held-out comparison only after configurations are fixed.
7. Report retrieval quality, answer/fallback safety, citation validity, case pass rate, and error counts.
8. Report known limitations, including no qualified human legal review.

If learned or fine-tuned components are introduced, use train/validation/test splits rather than only development/test splits.

Do not invent legal expectations to increase benchmark size.

Do not describe reranking, GraphRAG, time-aware filtering, API/backend, or fine-tuning as adopted unless separately implemented and evaluated.

## Required Workflow Before Editing

Before editing repository files:

1. Read the canonical instructions and current project context.
2. Read the relevant skill files.
3. Inspect relevant implementation, tests, configurations, and documentation.
4. Run `git status --short`.
5. State a concise implementation plan.
6. Identify validation commands.
7. Confirm whether protected paths or external services are involved.
8. Surface any workflow boundary before making changes.

## Required Workflow After Editing

After editing:

1. Summarize the changes.
2. List changed files.
3. Explain important design choices.
4. Report tests and validation commands.
5. Report failures, warnings, and remaining limitations.
6. Confirm that protected paths were not unintentionally changed.
7. Confirm that official evaluation artifacts were not unintentionally changed.
8. Confirm that secrets were not logged or committed.
9. Do not claim success when validation fails.

## Standard Validation

Use the relevant subset of:

```bash
env UV_CACHE_DIR=/tmp/vnlaw-uv-cache find src scripts tests -name '*.py' -exec uv run python -m py_compile {} +

uv run pytest tests/unit -q --durations=30
uv run pytest tests/integration -q --durations=30

uv run ruff check src scripts tests
uv run ruff format --check src scripts tests

uv lock --check
git diff --check
```

Do not broadly reformat unrelated legacy code merely to make a repository-wide formatting check pass.

## Explicitly Out of Scope Without Separate Authorization

Do not introduce any of the following as part of an unrelated task:

* corpus mutation;
* chunking changes;
* benchmark/qrels/evidence group changes;
* Qdrant re-indexing;
* Qdrant collection mutation;
* real LLM/API calls;
* embedding inference;
* reranking inference;
* full benchmark evaluation;
* quality-gate weakening;
* GraphRAG;
* multi-agent retrieval;
* API implementation;
* UI implementation;
* authentication;
* deployment;
* fine-tuning;
* monitoring or MLOps infrastructure;
* production legal-advice claims;
* new trusted legal-source architecture.

Each of these requires an explicitly scoped task and the relevant skill review.
