# VnLaw-QA Repository Instructions

## 1. Mission

VnLaw-QA is a Vietnamese legal question-answering and retrieval-augmented generation system. It is not a generic chatbot.

The repository must prioritize:

- legal source traceability;
- citation integrity;
- deterministic data processing;
- safe fallback when evidence is insufficient;
- reproducible evaluation;
- clean separation between domain logic, orchestration, CLI entrypoints, and runtime artifacts.

The system supports legal research. It must not be presented as a replacement for professional legal advice.

## 2. Instruction Order

Before making changes, read sources in this order:

1. `AGENTS.md` — canonical repository rules.
2. `PROJECT_CONTEXT.md` — canonical current project state and roadmap.
3. `.codex/context/INSTRUCTION_INDEX.md` — instruction routing and source locations.
4. `.agents/skills/SKILL_INDEX.md` — task-to-skill routing.
5. Relevant `.agents/skills/<skill-name>/SKILL.md` files.
6. Relevant implementation, tests, configs, and documentation.

Do not treat generated reports, old mirrors, or stale phase notes as authoritative context.

## 3. Core Legal Accuracy Rules

- No trusted source means no confident legal answer.
- No traceable citation means the answer is not a valid legal answer.
- Never fabricate laws, articles, clauses, points, penalties, procedures, effective dates, or citations.
- Preserve Vietnamese legal hierarchy: Phần → Chương → Mục → Điều → Khoản → Điểm.
- Prefer consolidated documents (`VBHN`) when available.
- Preserve document title, law ID, article, clause, point, source URL, effective metadata, and hierarchy identifiers.
- Auxiliary parent context may support understanding, but it is not directly citable unless the selected child evidence explicitly supports the claim.
- If evidence is insufficient, incomplete, unsafe, or not directly relevant, use the existing fallback path instead of guessing.
- Citation-ID validity is not semantic faithfulness. A valid `[E#]` mapping does not prove that a claim is fully supported.

Default trusted legal source:

```text
https://thuvienphapluat.vn
```

Do not add another source unless the task explicitly scopes and documents that architectural decision.

## 4. Current Architecture

### CLI entrypoints

```text
scripts/
  corpus/
  indexing/
  retrieval/
  evaluation/
```

Scripts must remain thin wrappers that:

- parse CLI arguments;
- call reusable services or domain modules;
- print concise summaries;
- return documented exit codes.

Do not place reusable business logic in scripts.

### Source layout

- `src/ingestion/` — registry, crawling, raw audit, cleaning, storage.
- `src/processing/` — legal hierarchy parsing, chunking, processed JSONL validation.
- `src/indexing/` — embedding and Qdrant indexing/validation.
- `src/retrieval/` — dense retrieval, local BM25 sparse retrieval, RRF fusion, coverage-aware quota retrieval, evidence construction and selection, RAG pipeline behavior, citation guard integration, and fallback behavior.
- `src/generation/` — LLM client wrappers, prompt rendering, answer formatting, and generation-specific helpers where implemented.
- `src/evaluation/` — frozen benchmark schemas, metrics, retrieval evaluation, strict generation evaluation, evidence diagnostics, error analysis, and artifact contracts.
- `src/services/` — orchestration where a service boundary already exists.
- `src/api/` — FastAPI Legal QA product API.
- `apps/frontend/` — Next.js Legal QA product UI.
- `src/monitoring/`, `src/security/` — future or separately scoped functionality.

Use the existing repository layout rather than introducing parallel abstractions.
There is intentionally no `apps/backend`; do not create one or move backend
code out of `src/api`.


## 5. Current Project Status

The Naive RAG baseline is closed with known limitations. The final adopted evaluated workflow uses coverage-aware hybrid retrieval and strict generation with citation ID and answerability fallback guards.

Current durable state:

- 52 legal documents are registered, crawled, audited, cleaned, parsed, and chunked.
- `data/processed/legal_chunks.jsonl` contains 40,389 validated chunks.
- Qdrant collection `vnlaw_chunks_bgem3_v1_full` contains 40,389 BGE-M3 dense vectors.
- Dense retrieval, local BM25 sparse retrieval, fixed RRF fusion, coverage-aware quota retrieval, evidence safety/selection, fallback-aware generation, citation ID guard, answerability fallback guard, repeatable generation evaluation, evidence previews, manual claim-to-citation review, prompt precision hardening, and offline diagnostics are implemented.
- The current offline gate status is `quality_gate_passed`.
- The five-case suite is a small regression baseline, not a held-out benchmark proving broad Vietnamese legal QA quality.
- Frozen benchmark `v0.1.0` contains 128 queries: 85 development and 43 held-out reporting-only cases.
- Final adopted retrieval is `coverage_aware_quota`.
- Reranking was evaluated but not adopted.
- Latest Advanced RAG strict generation all-split metrics are recorded in
  `artifacts/reports/evaluation/advanced_rag/strict_generation_evaluation_answer_policy_refresh_20260708_235500`
  and include decision accuracy `0.8671875`, fallback-required fallback rate
  `1.000`, citation ID validity `1.000`, retrieval errors `0`, and generation
  errors `0`.
- The Legal QA product MVP is complete for fake-mode local demo usage:
  FastAPI endpoints under `src/api`, Next.js frontend under `apps/frontend`,
  local Makefile commands, backend/frontend Dockerfiles, and
  `docker-compose.yml` fake-mode stack.
- Conversation storage remains memory by default. PostgreSQL conversation
  storage is optional through `LEGAL_QA_CONVERSATION_STORE=postgres` and
  `LEGAL_QA_DATABASE_URL`, with schema at
  `scripts/database/postgres_conversation_store.sql` and guarded real-DB
  validation through `scripts/database/smoke_postgres_conversation_store.py`.
  Neon managed PostgreSQL validation for this store completed on 2026-07-09,
  and production Render PostgreSQL conversation storage was enabled and
  conversation-CRUD verified on 2026-07-09. Render stores
  `LEGAL_QA_DATABASE_URL` as a secret, uses
  `LEGAL_QA_CONVERSATION_STORE=postgres`, keeps `LEGAL_QA_AUTH_ENABLED=false`,
  and keeps rate limiting enabled. Do not use production
  `/api/v1/legal-qa/ask` for conversation storage validation.
- Production anonymous session ownership enablement is prepared but not yet
  verified. It requires manual Render updates to
  `LEGAL_QA_AUTH_ENABLED=true`, a strong secret
  `LEGAL_QA_SESSION_SECRET`, `LEGAL_QA_SESSION_HEADER=X-Legal-QA-Session`,
  backend redeploy, and conversation-ownership-only smoke verification.
- Fake mode is the default local/demo path. It does not require Qdrant,
  OpenRouter, embedding models, rerankers, or legal corpus data. Real mode is
  manual and must not be used in routine validation.

See `PROJECT_CONTEXT.md`, `docs/advanced_rag.md`, `docs/evaluation.md`, and `docs/naive_rag.md` for current status and technical details.


## 6. Functional Naming Rule

Phase labels are documentation and project-management concepts only.

Do not encode roadmap phase numbers in:

- source filenames;
- script filenames;
- config filenames;
- dataset filenames;
- artifact filenames;
- test filenames;
- class names;
- function names;
- variables;
- statuses;
- schemas;
- report metadata;
- CLI paths;
- public APIs.

Use functional or domain names such as:

```text
quality_gate.yml
manual_faithfulness_verdicts.json
evaluate_quality_gate.py
QualityGateEvaluator
quality_gate_passed
```

Phase labels may appear in `README.md`, `PROJECT_CONTEXT.md`, `docs/`, and roadmap/status descriptions.

## 7. Python and OOP Standards

- Use Python 3.11+.
- Add `from __future__ import annotations` to new Python files unless there is a clear reason not to.
- Use complete type hints at public boundaries.
- Use Pydantic v2 for config and schema boundaries where appropriate.
- Prefer typed models, dataclasses, or protocols over untyped dictionaries.
- Keep classes small and single-purpose.
- Prefer dependency injection for infrastructure clients.
- Do not instantiate Qdrant, HTTP, or LLM clients deep inside domain logic.
- Keep I/O boundaries explicit.
- Use custom exceptions and structured logging where appropriate.
- Do not use `except Exception: pass` in production code.
- Keep scripts thin and reusable logic under `src/`.
- Do not create duplicate modules for one-off experiments.

## 8. Documentation Standards

- Use Google-style docstrings for public classes, functions, methods, Pydantic models, non-trivial algorithms, and legal/RAG components.
- Document purpose, arguments, return values, exceptions, side effects, legal assumptions, and retrieval assumptions.
- Keep `README.md` high-level.
- Keep `PROJECT_CONTEXT.md` current and concise.
- Keep technical component documentation functional rather than phase-named where possible.
- Do not create standalone phase trackers after a phase is closed.
- Do not commit generated runtime reports unless the repository explicitly defines them as durable source artifacts.

## 9. Data Protection and Protected Paths

Do not mutate these paths unless the task explicitly requires an official rerun:

```text
data/raw/
data/interim/
data/reports/
data/processed/legal_chunks.jsonl
data/eval/
artifacts/reports/evaluation/
```

Additional rules:

- Raw data is immutable.
- Derived artifacts belong in their designated directories.
- Do not commit Qdrant storage, model caches, virtual environments, or generated caches.
- Do not remove accepted warnings merely to improve metrics.
- Preserve IDs, citations, hierarchy metadata, hashes, source metadata, warning visibility, and repeal flags.
- Do not split legal text by arbitrary character windows when that breaks legal meaning.

## 10. Configuration Convention

Committed YAML configuration belongs under `configs/`. These files must be
safe to commit, reviewable in Git, and limited to reproducible settings such as
retrieval thresholds, indexing batch sizes, validation rules, benchmark
configuration, corpus registry metadata, and non-secret provider/model defaults.

Local runtime overrides and secrets belong in an uncommitted `.env`.
`.env.example` documents variable names only. Use `.env` for provider API keys,
tokens, local endpoints, service mode, and paths that select committed config
files, such as `LEGAL_QA_RETRIEVAL_CONFIG` and `LEGAL_QA_LLM_CONFIG`.

Do not put provider API keys, tokens, passwords, or other secrets in
`configs/*.yml`. Do not put large reviewable settings blocks in `.env`; `.env`
should select or override runtime values, not replace committed config.

## 11. Qdrant and External-Service Safety

Unless explicitly scoped:

- do not recreate or delete collections;
- do not upsert points;
- do not update payloads;
- do not re-index;
- do not re-embed the corpus;
- do not run real embedding inference;
- do not run real reranking inference;
- do not run full benchmark workflows;
- use Qdrant read-only for retrieval/evaluation;
- do not call OpenRouter or other LLM providers for tasks that can run offline;
- never print or serialize API keys;
- never dump environment variables;
- never write Authorization headers or tokens to reports.
- evaluation runners support authenticated Qdrant Cloud through
  `QDRANT_API_KEY`; use it only from the private environment and never pass it
  as a CLI argument;
- for local backend development, use
  `LEGAL_QA_SERVICE_MODE=fake uv run python -m uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000`;
  do not use `uv run uvicorn`;
- use `docker-compose.yml` for the fake-mode local stack; do not introduce
  alternate Compose filenames.

Secrets must come from environment variables or `.env`. Non-secret provider configuration belongs in config files.

## 12. Evaluation Rules

The existing five-case suite is a development/regression suite.

It may be used to verify:

- decision policy;
- LLM-call policy;
- fallback behavior;
- citation-ID integrity;
- secret leakage;
- answer precision regressions;
- reviewed claim-to-citation verdicts.

It must not be used to claim broad Vietnamese legal QA quality.

The frozen benchmark `v0.1.0` is the current comparative benchmark. Use the
development split for implementation and tuning. Keep the held-out split
reporting-only.

When comparing systems, keep corpus, chunking, generator, prompt,
evidence-selection policy, fallback policy, and evaluation code fixed unless a
controlled ablation explicitly changes one component.

Reranking is not part of the final adopted pipeline unless a future task
explicitly scopes a new ablation.

When refreshing official metrics, use a unique non-existing output directory
under `artifacts/reports/evaluation/`. Do not overwrite historical reports.
Do not rerun the Naive RAG baseline unless explicitly requested. Do not compare
latency across local-Qdrant and Qdrant-Cloud runs; latency comparisons require
the same runtime environment.

If model training or fine-tuning is introduced, use train/validation/test splits.

## 13. Required Workflow

### Before editing

1. Read `AGENTS.md`.
2. Read `PROJECT_CONTEXT.md`.
3. Read `.codex/context/INSTRUCTION_INDEX.md` when instruction routing matters.
4. Read `.agents/skills/SKILL_INDEX.md` and the relevant skills.
5. Inspect the relevant source, tests, configs, and docs.
6. State a short plan.
7. Identify validation commands.
8. Check `git status --short` before modifying files.

### After editing

1. Summarize changes.
2. List changed files.
3. Explain important design choices.
4. Report tests and checks.
5. Report remaining risks or limitations.
6. Confirm protected paths and secrets are clean.
7. Do not claim success when tests fail.

## 14. Standard Validation

Use relevant subsets of:

```bash
env UV_CACHE_DIR=/tmp/vnlaw-uv-cache find src scripts tests -name '*.py' -exec uv run python -m py_compile {} +

uv run pytest tests/unit -q --durations=30
uv run pytest tests/integration -q --durations=30

uv run ruff check src scripts tests
uv run ruff format --check src scripts tests

uv lock --check
git diff --check
```

For small tasks, targeted checks are acceptable first:

```bash
uv run python -m py_compile <touched-python-files>
uv run pytest <relevant-tests> -q
uv run ruff check <touched-files-or-directories>
uv run ruff format --check <touched-files-or-directories>
```

Do not reformat unrelated legacy files merely to make a broad check pass.
