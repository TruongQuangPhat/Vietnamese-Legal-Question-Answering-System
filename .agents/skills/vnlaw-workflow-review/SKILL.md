---
name: vnlaw-workflow-review
description: Use for daily development workflow, task planning, code review, git diff review, branch discipline, commit readiness, protected path checks, and Codex-controlled implementation steps.
---

# Workflow and Review Skill

Use this skill when starting, implementing, or reviewing a task.

## Start-of-Task Workflow

Recommended branch workflow:

```bash
git checkout develop
git pull origin develop
git checkout -b feature/<short-task-name>
```

Before editing, Codex should identify:

```text
Task restatement:
Relevant skill(s):
Files to inspect:
Plan:
Files likely to change:
Tests/checks to run:
Protected paths to avoid:
Risks:
```

Start from repository root and inspect the current state:

```bash
git status --short
git diff --stat
```

## Implementation Workflow

1. Inspect relevant files.
2. Make minimal, scoped changes.
3. Preserve public APIs unless explicitly asked.
4. Add or update tests when behavior changes.
5. Run targeted checks first.
6. Run broader safe validation before commit readiness.
7. Summarize changed files, diff intent, tests, and risks.

Use mocks, fakes, tiny fixtures, and `tmp_path` for routine tests involving Qdrant, LLM providers, embedding models, rerankers, or evaluation artifacts.

## Review Workflow

Use:

```bash
git status --short
git diff --stat
git diff
```

Review for:

```text
legal correctness
OOP design
type hints
docstrings
tests
security
retrieval quality
citation handling
fallback behavior
artifact safety
protected path changes
accidental file changes
```

## Protected Paths

Do not modify these unless the user explicitly scopes the operation:

```text
data/raw/**
data/interim/**
data/reports/**
data/processed/legal_chunks.jsonl
data/eval/**
artifacts/reports/evaluation/**
```

Check protected paths before commit readiness:

```bash
git diff --name-only -- \
  data/raw \
  data/interim \
  data/reports \
  data/processed/legal_chunks.jsonl \
  data/eval

git diff --name-only -- artifacts/reports/evaluation
```

Expected output is usually empty unless the user explicitly scoped data or official evaluation artifact changes.

## Pre-Commit Checklist

* [ ] Scope is narrow and matches the task.
* [ ] Public functions/classes have type hints where practical.
* [ ] Required docstrings exist.
* [ ] No `except Exception: pass`.
* [ ] No hardcoded secrets.
* [ ] No real credentials or private tokens in code, tests, docs, or reports.
* [ ] Unit tests added or updated when behavior changes.
* [ ] Integration tests added or updated when workflow behavior changes.
* [ ] Ruff passes.
* [ ] Format check passes.
* [ ] `uv lock --check` passes.
* [ ] `mypy` passes only if configured or explicitly scoped.
* [ ] Legal citation behavior is preserved.
* [ ] Fallback behavior is preserved.
* [ ] Protected paths are not modified unless explicitly scoped.
* [ ] Official evaluation artifacts are not modified unless explicitly scoped.
* [ ] No unrelated files are changed.

## Recommended Safe Checks

Run narrower checks first when the task is small.

Safe full validation:

```bash
env UV_CACHE_DIR=/tmp/vnlaw-uv-cache find src scripts tests -name '*.py' -exec uv run python -m py_compile {} +

uv run pytest tests/unit -q --durations=30
uv run pytest tests/integration -q --durations=30

uv run ruff check src scripts tests
uv run ruff format --check src scripts tests

uv lock --check
git diff --check
```

Use `mypy` only if it is configured or explicitly scoped:

```bash
uv run mypy src
```

## Expensive or Real-Service Commands

Ask before running:

```text
real crawling
real cleaning/parsing/chunking over the full corpus
real Qdrant writes
re-embedding
re-indexing
collection recreate/delete/upsert
real LLM/OpenRouter/Gemini/API calls
real embedding model inference
real reranking inference
full benchmark evaluation
long evaluation jobs
Docker/deployment jobs
```

Do not expose secrets in logs, prompts, reports, or terminal output.

## Commit Format

Use Conventional Commits:

```text
feat(ingestion): add registry-driven crawler
fix(retrieval): handle empty sparse retrieval results
docs(api): document QA endpoint schema
test(parser): add clause extraction edge cases
perf(generation): reduce prompt context overhead
```

Prefer separate commits for separate concerns:

```text
fix(...)
test(...)
docs(...)
eval(...)
```

Do not commit unless the user explicitly asks or the task explicitly allows it.

## Codex Response Format After Changes

After implementation, return:

```text
Summary:
Files changed:
Tests run:
Result:
Protected path checks:
Official artifact checks:
Risks:
Follow-up recommendations:
Recommended commit message:
```

## Do Not

* Do not edit unrelated files.
* Do not run expensive commands without approval.
* Do not run real-service workflows unless explicitly scoped.
* Do not skip tests silently.
* Do not hide failing checks.
* Do not commit generated artifacts unless requested.
* Do not modify protected paths unless explicitly scoped.
* Do not overwrite official evaluation artifacts unless explicitly scoped.
* Do not make broad refactors during a narrow bug fix.
