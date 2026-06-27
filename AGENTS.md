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
- `src/retrieval/` — dense/sparse retrieval, fusion, evidence construction and selection, RAG generation, evaluation, manual review export, and offline quality gate.
- `src/services/` — orchestration where a service boundary already exists.
- `src/evaluation/` — frozen benchmark schemas, metrics, strict generation evaluation, and offline diagnostics.
- `src/api/`, `src/monitoring/`, `src/security/` — future or separately scoped functionality.

Use the existing repository layout rather than introducing parallel abstractions.

## 5. Current Project Status

The Naive RAG baseline is closed with known limitations. The final adopted
evaluated workflow uses coverage-aware hybrid retrieval and strict generation
with citation and answerability fallback guards.

Current durable state:

- 52 legal documents are registered, crawled, audited, cleaned, parsed, and chunked.
- `data/processed/legal_chunks.jsonl` contains 40,389 validated chunks.
- Qdrant collection `vnlaw_chunks_bgem3_v1_full` contains 40,389 BGE-M3 dense vectors.
- Dense retrieval, local BM25 sparse retrieval, fixed RRF fusion, coverage-aware quota retrieval, evidence safety/selection, fallback-aware generation, strict citation guard, answerability fallback guard, repeatable generation evaluation, evidence previews, manual claim-to-citation review, prompt precision hardening, and offline diagnostics are implemented.
- The current offline gate status is `quality_gate_passed`.
- The five-case suite is a small regression baseline, not a held-out benchmark proving broad Vietnamese legal QA quality.
- Frozen benchmark `v0.1.0` contains 128 queries: 85 development and 43 held-out reporting-only cases.
- Final adopted retrieval is `coverage_aware_quota`.
- Reranking was evaluated but not adopted.
- Final strict generation all-split metrics include decision accuracy `0.875`, safe fallback rate `1.000`, citation ID validity `1.000`, retrieval errors `0`, and generation errors `0`.

See `PROJECT_CONTEXT.md`, `docs/advanced_rag.md`, `docs/evaluation.md`, and
`docs/naive_rag.md` for current status and technical details.

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

## 10. Qdrant and External-Service Safety

Unless explicitly scoped:

- do not recreate or delete collections;
- do not upsert points;
- do not update payloads;
- do not re-index;
- use Qdrant read-only for retrieval/evaluation;
- do not call OpenRouter for tasks that can run offline;
- never print or serialize API keys;
- never dump environment variables;
- never write Authorization headers or tokens to reports.

Secrets must come from environment variables or `.env`. Non-secret provider configuration belongs in config files.

## 11. Evaluation Rules

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

If model training or fine-tuning is introduced, use train/validation/test splits.

## 12. Required Workflow

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

## 13. Standard Validation

Use relevant subsets of:

```bash
uv run python -m py_compile <touched-python-files>
uv run pytest <relevant-tests> -q
uv run ruff check src scripts tests
uv run ruff format --check <touched-files-or-directories>
uv lock --check
git diff --check
```

Do not reformat unrelated legacy files merely to make a broad check pass.

## 14. Do Not Do Without Explicit Scope

- Do not mutate protected corpus paths.
- Do not re-index Qdrant.
- Do not bypass evidence selection or fallback gates.
- Do not let parent context become directly citable evidence.
- Do not weaken quality-gate thresholds to force a pass.
- Do not invent legal expectations for new evaluation cases.
- Do not implement GraphRAG, agents, API, UI, deployment, fine-tuning, or MLOps as part of an unrelated task.
- Do not introduce phase-labelled implementation names.
- Do not create duplicate context mirrors.
- Do not copy secrets or local settings into repository instructions.
