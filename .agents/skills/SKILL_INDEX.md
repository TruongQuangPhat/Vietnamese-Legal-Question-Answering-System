# VnLaw-QA Codex Skill Index

Use this index before modifying domain-specific code, configuration, tests, or
documentation. Skills under `.agents/skills/` are the primary
repository-specific guidance sources.

This file is a task router. It does not replace the canonical repository state
or repository-wide instructions.

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
* Generated reports, historical trackers, stale mirrors, and old phase notes are
  not authoritative.

Do not maintain manual mirrors of `AGENTS.md` or `PROJECT_CONTEXT.md`.

## Task-to-Skill Routing

| Task type                                                                    | Read these skills                                                                                                                      |
| ---------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| Mission, roadmap, current priorities, or stage boundaries                    | `vnlaw-project-charter`, `vnlaw-workflow-review`                                                                                       |
| Repository layout, module ownership, or architectural boundaries             | `vnlaw-project-structure`, `vnlaw-oop-code-quality`                                                                                    |
| Corpus registry or legal source changes                                      | `vnlaw-source-corpus`, `vnlaw-data-ingestion`, `vnlaw-legal-accuracy`                                                                  |
| Crawling or raw artifact handling                                            | `vnlaw-data-ingestion`, `vnlaw-source-corpus`, `vnlaw-security-secrets`                                                                |
| Cleaning HTML or normalizing Vietnamese legal text                           | `vnlaw-cleaning-normalization`, `vnlaw-legal-accuracy`                                                                                 |
| Cleaning quality audit or normalization improvements                         | `vnlaw-cleaning-normalization`, `vnlaw-evaluation-cicd`, `vnlaw-legal-accuracy`                                                        |
| Legal hierarchy parsing or chunk creation                                    | `vnlaw-legal-parsing-chunking`, `vnlaw-legal-accuracy`                                                                                 |
| Processed chunk validation or embedding readiness                            | `vnlaw-legal-parsing-chunking`, `vnlaw-embedding-indexing`, `vnlaw-evaluation-cicd`, `vnlaw-legal-accuracy`                            |
| Embedding chunks or configuring Qdrant                                       | `vnlaw-embedding-indexing`, `vnlaw-retrieval-search-reranking`, `vnlaw-security-secrets`                                               |
| Dense search, filters, fusion, sparse retrieval, or reranking                | `vnlaw-retrieval-search-reranking`, `vnlaw-advanced-rag`, `vnlaw-legal-accuracy`                                                       |
| Existing Naive RAG baseline                                                  | `vnlaw-naive-rag`, `vnlaw-context-engineering`, `vnlaw-llm-generation`, `vnlaw-legal-accuracy`                                         |
| Benchmark construction, annotation, frozen splits, or comparative evaluation | `vnlaw-evaluation-cicd`, `vnlaw-advanced-rag`, `vnlaw-legal-accuracy`, `vnlaw-workflow-review`                                         |
| Advanced RAG experiments or controlled ablations                             | `vnlaw-advanced-rag`, `vnlaw-retrieval-search-reranking`, `vnlaw-context-engineering`, `vnlaw-evaluation-cicd`, `vnlaw-legal-accuracy` |
| Graph traversal, GraphRAG, or multi-agent retrieval                          | `vnlaw-graphrag-agents`, `vnlaw-legal-accuracy`, `vnlaw-workflow-review`                                                               |
| Prompting, evidence packets, answer format, or citation behavior             | `vnlaw-context-engineering`, `vnlaw-llm-generation`, `vnlaw-legal-accuracy`                                                            |
| Public legal answer behavior                                                 | `vnlaw-legal-accuracy`, `vnlaw-llm-generation`, `vnlaw-context-engineering`                                                            |
| FastAPI or backend service work                                              | `vnlaw-api-backend`, `vnlaw-oop-code-quality`, `vnlaw-security-secrets`                                                                |
| Tests, metrics, release gates, regression checks, or CI                      | `vnlaw-evaluation-cicd`, `vnlaw-workflow-review`                                                                                       |
| Secrets, PII, logs, database exposure, or Docker security                    | `vnlaw-security-secrets`                                                                                                               |
| Documentation, docstrings, or repository guidance                            | `vnlaw-docstrings-documentation`, `vnlaw-oop-code-quality`                                                                             |
| Pull-request review, cross-stage changes, or scope validation                | `vnlaw-workflow-review`, `vnlaw-project-charter`                                                                                       |

## Current Stage Discipline

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
* evidence construction and selection;
* fallback-aware Naive RAG;
* generation regression evaluation;
* manual faithfulness review;
* prompt precision hardening;
* offline quality gate.

The Naive RAG baseline is closed with known limitations.

The current next stage is benchmark-first Advanced RAG evaluation.

The required sequence is:

```text
broader reviewed benchmark
→ deterministic development and held-out test split
→ frozen Naive RAG baseline
→ controlled sparse/hybrid retrieval experiments
→ controlled fusion experiments
→ reranking ablation
→ final held-out comparison
```

Do not begin by immediately implementing BM25, sparse indexing, RRF, reranking,
query rewriting, GraphRAG, agents, API, or UI before the benchmark and frozen
comparison protocol are established.

The existing five-case suite must remain a development, safety, and regression
suite. It must not be used as held-out proof that an advanced retrieval system
is broadly better than the Naive RAG baseline.

If a task crosses the current stage boundary:

1. Read `vnlaw-workflow-review`.
2. Identify the boundary explicitly.
3. Preserve existing baseline behavior.
4. Keep the change separately scoped.
5. Do not implement future components implicitly.

## Baseline Preservation Rules

Unless a task explicitly scopes a baseline change, preserve:

* the validated legal corpus;
* `data/processed/legal_chunks.jsonl`;
* the existing Qdrant collection;
* dense embeddings;
* prompt behavior;
* evidence-selection behavior;
* fallback behavior;
* citation-ID guard behavior;
* the five-case regression suite;
* the existing offline quality gate.

Do not weaken safety or quality thresholds merely to make a new experiment
pass.

Do not refactor completed retrieval or generation logic as a side effect of
building the broader evaluation layer.

Broader benchmark and comparative evaluation logic should use
`src/evaluation/` where appropriate while existing Naive RAG regression logic
remains under `src/retrieval/`.

## Legal Accuracy Requirements

All tasks involving legal data, retrieval, evidence, prompting, generation, or
evaluation must preserve these invariants:

* No trusted source means no confident legal answer.
* No traceable citation means the answer is not a valid legal answer.
* Never fabricate laws, articles, clauses, points, procedures, penalties,
  effective dates, or citations.
* Preserve the hierarchy:
  `Phần → Chương → Mục → Điều → Khoản → Điểm`.
* Prefer consolidated documents (`VBHN`) when available.
* Auxiliary parent context is not directly citable unless selected child
  evidence explicitly supports the claim.
* Insufficient, incomplete, unsafe, or indirectly relevant evidence must use
  the existing fallback path.
* Citation-ID validity does not prove semantic faithfulness.
* The system supports legal research and must not be represented as a
  replacement for professional legal advice.

## Functional Naming Rule

Phase labels are allowed in roadmap and status documentation, but they must not
be encoded into implementation identifiers.

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
quality_gate_passed
```

## Protected Paths and Runtime Safety

Do not mutate these paths unless the task explicitly requires an official
pipeline rerun:

```text
data/raw/
data/interim/
data/reports/
data/processed/legal_chunks.jsonl
```

Unless explicitly scoped:

* do not recreate or delete Qdrant collections;
* do not upsert points;
* do not update Qdrant payloads;
* do not re-index the corpus;
* do not commit Qdrant storage;
* do not commit model caches;
* do not commit virtual environments or generated caches;
* do not print, log, or serialize secrets;
* do not write API keys into reports;
* do not call external LLM services for work that can be completed offline.

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

Before introducing a new module, check whether an existing module already owns
that responsibility.

## Evaluation Discipline

Before claiming that an advanced system improves over the Naive RAG baseline:

1. Build a broader legally reviewed benchmark.
2. Keep the existing five-case regression suite separate.
3. Define deterministic development and held-out test splits.
4. Group paraphrases and provision families to prevent split leakage.
5. Freeze the held-out test split before tuning.
6. Freeze the Naive RAG baseline configuration and metadata.
7. Tune retrieval changes only on the development split.
8. Keep corpus, chunking, generator, prompt, selection, fallback, and
   evaluation code fixed for the primary retrieval comparison.
9. Run the final held-out comparison only after configurations are fixed.
10. Report quality, safety, latency, cost, memory, and throughput trade-offs.

If learned or fine-tuned components are introduced, use
train/validation/test splits rather than only development/test splits.

Do not invent legal expectations to increase benchmark size.

## Required Workflow Before Editing

Before editing repository files:

1. Read the canonical instructions and current project context.
2. Read the relevant skill files.
3. Inspect relevant implementation, tests, configurations, and documentation.
4. Run `git status --short`.
5. State a concise implementation plan.
6. Identify validation commands.
7. Confirm whether protected paths or external services are involved.
8. Surface any stage boundary before making changes.

## Required Workflow After Editing

After editing:

1. Summarize the changes.
2. List changed files.
3. Explain important design choices.
4. Report tests and validation commands.
5. Report failures, warnings, and remaining limitations.
6. Confirm that protected paths were not unintentionally changed.
7. Confirm that secrets were not logged or committed.
8. Do not claim success when validation fails.

## Standard Validation

Use the relevant subset of:

```bash
uv run python -m py_compile <touched-python-files>
uv run pytest <relevant-tests> -q
uv run ruff check src scripts tests
uv run ruff format --check <touched-files-or-directories>
uv lock --check
git diff --check
```

Do not broadly reformat unrelated legacy code merely to make a repository-wide
formatting check pass.

## Explicitly Out of Scope Without Separate Authorization

Do not introduce any of the following as part of an unrelated task:

* corpus mutation;
* chunking changes;
* Qdrant re-indexing;
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
