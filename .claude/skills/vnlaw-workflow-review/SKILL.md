---
name: vnlaw-workflow-review
description: Use for daily development workflow, task planning, code review, git diff review, branch discipline, commit readiness, and Claude-controlled implementation steps.
allowed-tools: Read, Grep, Glob, LS, Bash, Edit, MultiEdit, Write
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

Before editing, Claude must return:

```text
Task restatement:
Relevant skill(s):
Files to inspect:
Plan:
Files likely to change:
Tests/checks to run:
Risks:
```

## Implementation Workflow

1. Inspect relevant files.
2. Make minimal changes.
3. Preserve public APIs unless explicitly asked.
4. Add or update tests.
5. Run targeted checks.
6. Summarize changed files, diff intent, tests, and risks.

## Review Workflow

Use:

```bash
git status
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
accidental file changes
```

## Pre-Commit Checklist

- [ ] All public functions/classes have type hints.
- [ ] Required docstrings exist.
- [ ] No `except Exception: pass`.
- [ ] No hardcoded secrets.
- [ ] Unit tests added or updated.
- [ ] `ruff` passes.
- [ ] `mypy` passes for touched modules where practical.
- [ ] Metadata is complete for ingestion-related changes.
- [ ] Legal citation behavior is preserved.
- [ ] No unrelated files are changed.

## Recommended Checks

```bash
uv run ruff check src tests
uv run ruff format src tests
uv run mypy src
uv run pytest tests/unit -v
```

Run narrower checks first when the task is small.

Ask before running expensive full-corpus ingestion, model training, or long evaluation jobs.

## Commit Format

Use Conventional Commits:

```text
feat(ingestion): add registry-driven crawler
fix(retrieval): handle empty sparse retrieval results
docs(api): document QA endpoint schema
test(parser): add clause extraction edge cases
perf(generation): reduce prompt context overhead
```

## Claude Response Format After Changes

After implementation, return:

```text
Summary:
Files changed:
Tests run:
Result:
Risks:
Follow-up recommendations:
```

## Do Not

- Do not edit unrelated files.
- Do not run expensive commands without approval.
- Do not skip tests silently.
- Do not commit generated artifacts unless requested.
- Do not hide failing checks.
- Do not make broad refactors during a narrow bug fix.