# Codex Instruction Index

This file is an instruction router. It is not a duplicate project context and
must not become a second source of truth.

## 1. Read Order

Codex should read repository instructions in this order:

1. `AGENTS.md`
2. `PROJECT_CONTEXT.md`
3. `.codex/context/INSTRUCTION_INDEX.md`
4. `.agents/skills/SKILL_INDEX.md`
5. Relevant `.agents/skills/<skill-name>/SKILL.md`
6. Relevant source, tests, configs, and documentation

## 2. Canonical Sources

| Location | Role | Authority |
| --- | --- | --- |
| `AGENTS.md` | Repository-wide coding, legal accuracy, safety, workflow, naming, and validation rules | Canonical rules |
| `PROJECT_CONTEXT.md` | Current architecture, final evaluated state, limitations, protected paths, and workflow boundaries | Canonical project state |
| `.agents/skills/SKILL_INDEX.md` | Task-to-skill routing | Canonical skill router |
| `.agents/skills/<skill-name>/SKILL.md` | Task-specific repository guidance | Canonical for that skill |
| `README.md` | Public project overview, setup, commands, and current results | Durable overview |
| `docs/advanced_rag.md` | Final adopted coverage-aware retrieval and strict generation evaluation details | Durable component doc |
| `docs/evaluation.md` | Benchmark protocol, metrics, split policy, and final evaluation contract | Durable component doc |
| `docs/embedding_indexing.md` | BGE-M3/Qdrant index contract | Durable component doc |
| `docs/naive_rag.md` | Dense Naive RAG baseline reference | Durable component doc |
| `docs/parent_child_chunking.md` | Parent-child chunking contract | Durable component doc |
| `docs/processed_jsonl.md` | Processed chunk JSONL contract | Durable component doc |

Historical journal or roadmap documents are useful for provenance, but they are
not authoritative when they conflict with `PROJECT_CONTEXT.md` or current
implementation.

## 3. Active Skill Policy

- Active repository skills live only under `.agents/skills/`.
- Use `.agents/skills/SKILL_INDEX.md` to select skills.
- Read only the skills relevant to the task.
- Do not create another active skill directory.
- Do not create mirrored copies of active skills under `.codex/context/`.
- Do not duplicate entire repository rules inside skill files.

## 4. Context Policy

`PROJECT_CONTEXT.md` is the only canonical current-state file.

Do not maintain manual mirrors of `AGENTS.md`, `PROJECT_CONTEXT.md`, or active
skills.

`INSTRUCTION_INDEX.md` should contain routing information only. It should not
contain detailed metric tables, duplicated roadmaps, or a second project
status.

## 5. Current Status Pointer

Current durable status:

- corpus, parent-child chunking, processed JSONL validation, and BGE-M3 dense
  Qdrant indexing are complete for 52 documents / 40,389 chunks;
- frozen benchmark `v0.1.0` has 128 queries with development and held-out
  reporting splits;
- final adopted retrieval is `coverage_aware_quota`;
- reranking was evaluated but not adopted;
- final adopted strict generation uses coverage-aware retrieval, strict
  citation guard, and answerability fallback guard;
- workflow-level integration tests exist for corpus, retrieval, and evaluation;
- API deployment, GraphRAG, time-aware filtering, and fine-tuning are not part
  of the adopted evaluated pipeline.

Read `PROJECT_CONTEXT.md` for the complete current state.

## 6. Functional Naming Policy

Roadmap labels are allowed in historical or roadmap prose only.

Implementation must use functional/domain names for:

- source and script files;
- configs and datasets;
- artifacts and tests;
- classes and functions;
- statuses and schemas;
- report metadata and CLI paths;
- public APIs.

Examples:

```text
coverage_aware_quota
strict_generation_evaluation
quality_gate_passed
validate_benchmark.py
```

## 7. Source Freshness Rules

When sources disagree, use this priority:

1. `AGENTS.md` for durable repository rules.
2. `PROJECT_CONTEXT.md` for current status and boundaries.
3. Current implementation and tests for actual behavior.
4. Functional component documentation.
5. Historical notes and generated reports.

Do not follow stale statements such as:

- retrieval has not started;
- Advanced RAG is only future work;
- reranking is part of the final adopted pipeline;
- API deployment or time-aware filtering is implemented;
- the broad benchmark has not been frozen.

## 8. Update Policy

When a task changes durable repository behavior:

- update `AGENTS.md` only if a permanent rule changes;
- update `PROJECT_CONTEXT.md` when current architecture, status, limitations,
  or boundaries change;
- update the relevant skill when task-specific guidance changes;
- update functional component docs when commands or behavior change;
- do not create a new roadmap tracker for completed work;
- do not create duplicate context mirrors.

## 9. Security and Local-State Exclusion

Never copy these into instruction files:

- `.env` contents;
- API keys;
- tokens;
- credentials;
- Authorization headers;
- machine-specific local settings;
- Qdrant storage;
- model caches.

Only environment-variable names and non-secret configuration guidance may be
documented.

## 10. Protected Paths

Unless a task explicitly scopes an official rerun, do not mutate:

```text
data/raw/
data/interim/
data/reports/
data/processed/legal_chunks.jsonl
data/eval/
artifacts/reports/evaluation/
```

Do not re-index, re-embed, call real LLM providers, or mutate Qdrant during
documentation, evaluation-policy, context-maintenance, or test-only tasks.

## 11. Required Task Start

Before editing:

1. Read `AGENTS.md`.
2. Read `PROJECT_CONTEXT.md`.
3. Select relevant skills.
4. Inspect related source, tests, configs, and docs.
5. Check `git status --short`.
6. State a short plan and validation commands.

After editing:

1. Summarize changes.
2. List changed files.
3. Report tests and checks.
4. Report remaining risks.
5. Confirm protected paths and secrets are clean.
