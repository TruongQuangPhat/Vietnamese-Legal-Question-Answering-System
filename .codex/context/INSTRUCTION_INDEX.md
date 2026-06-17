# Codex Instruction Index

This file is an instruction router. It is not a duplicate project context and must not become a second source of truth.

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
| `PROJECT_CONTEXT.md` | Current architecture, completed work, limitations, roadmap, and next tasks | Canonical project state |
| `.agents/skills/SKILL_INDEX.md` | Task-to-skill routing | Canonical skill router |
| `.agents/skills/README.md` | Skill inventory and short descriptions | Supporting index |
| `.agents/skills/<skill-name>/SKILL.md` | Task-specific repository guidance | Canonical for that skill |
| `docs/naive_rag.md` | Completed Naive RAG technical documentation | Canonical component documentation |
| `docs/advanced_rag.md` | Advanced retrieval design notes | Reference until next-stage work is explicitly scoped |

## 3. Active Skill Policy

- Active repository skills live only under `.agents/skills/`.
- Use `.agents/skills/SKILL_INDEX.md` to select skills.
- Read only the skills relevant to the task.
- Do not create another active skill directory.
- Do not create mirrored copies of active skills under `.codex/context/`.
- Do not duplicate entire repository rules inside skill files.

## 4. Context Policy

`PROJECT_CONTEXT.md` is the only canonical project-state file.

Do not maintain manual mirrors of `AGENTS.md`, `PROJECT_CONTEXT.md`, or active
skills.

`INSTRUCTION_INDEX.md` should contain routing information only. It should not contain detailed phase metrics, duplicated roadmaps, or a second project status.

## 5. Current Status Pointer

Current durable status:

- the Naive RAG baseline is closed with known limitations;
- the offline gate status is `quality_gate_passed`;
- the current five-case suite is a regression suite, not a held-out comparative benchmark;
- the next planned work is benchmark construction with frozen development/test splits before advanced retrieval comparison.

Read `PROJECT_CONTEXT.md` for the complete current state.

## 6. Functional Naming Policy

Phase labels are allowed in documentation and roadmap descriptions only.

Implementation must use functional/domain names for:

- source and script files;
- configs and datasets;
- artifacts and tests;
- classes and functions;
- statuses and schemas;
- report metadata and CLI paths.

Examples:

```text
quality_gate.yml
manual_faithfulness_verdicts.json
evaluate_quality_gate.py
QualityGateEvaluator
quality_gate_passed
```

## 7. Source Freshness Rules

When sources disagree, use this priority:

1. `AGENTS.md` for durable repository rules.
2. `PROJECT_CONTEXT.md` for current status and roadmap.
3. Current implementation and tests for actual behavior.
4. Functional component documentation.
5. Historical notes and generated reports.

Do not follow stale statements such as:

- retrieval has not started;
- Naive RAG is still future work;
- the quality gate is still partial;
- Phase 9 closure is pending.

The current canonical context supersedes those statements.

## 8. Update Policy

When a task changes durable repository behavior:

- update `AGENTS.md` only if a permanent rule changes;
- update `PROJECT_CONTEXT.md` when current architecture, status, limitations, or roadmap changes;
- update the relevant skill when task-specific guidance changes;
- update functional component docs when commands or behavior change;
- do not create a new phase tracker for completed work;
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

Only environment-variable names and non-secret configuration guidance may be documented.

## 10. Protected Paths

Unless a task explicitly scopes an official rerun, do not mutate:

```text
data/raw/
data/interim/
data/reports/
data/processed/legal_chunks.jsonl
```

Do not re-index or mutate Qdrant during documentation, evaluation-policy, or context-maintenance tasks.

## 11. Required Task Start

Before editing:

1. Read `AGENTS.md`.
2. Read `PROJECT_CONTEXT.md`.
3. Select relevant skills.
4. Inspect related source and tests.
5. Check `git status --short`.
6. State a short plan and validation commands.

After editing:

1. Summarize changes.
2. List changed files.
3. Report tests and checks.
4. Report remaining risks.
5. Confirm protected paths and secrets are clean.
