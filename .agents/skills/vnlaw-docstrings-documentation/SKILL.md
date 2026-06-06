---
name: vnlaw-docstrings-documentation
description: Use when adding or reviewing Google-style docstrings, README content, API docs, architecture docs, comments, and developer documentation for VnLaw-QA.
---

# Docstrings and Documentation Skill

Use this skill whenever writing or reviewing code documentation, developer docs, API docs, architecture docs, or inline comments.

## Mandatory Docstring Coverage

Every public or non-trivial item must have a useful Google-style docstring:

- public class;
- public function;
- public method;
- Pydantic model;
- FastAPI endpoint;
- parser/chunker component;
- retrieval/reranking component;
- GraphRAG component;
- evaluation script;
- non-trivial algorithm.

## Docstring Requirements

Good docstrings must explain:

- purpose;
- arguments;
- return value;
- raised exceptions;
- side effects;
- legal assumptions;
- RAG/retrieval assumptions;
- examples when helpful.

Use Google-style docstrings:

```python
async def search(
    self,
    query: str,
    query_date: date | None,
    top_k: int,
) -> list[LegalCandidate]:
    """Search legal documents with time-aware hybrid retrieval.

    Args:
        query: Vietnamese legal question or search expression.
        query_date: Date used to resolve the effective law version. If omitted,
            the service uses the current date.
        top_k: Maximum number of candidates returned after fusion.

    Returns:
        Ranked legal candidates with law metadata, hierarchy, source URL, and
        retrieval scores.

    Raises:
        VectorSearchError: If Qdrant search fails.
        InvalidQueryError: If the query is empty or unsafe.

    Legal assumptions:
        Returned candidates are evidence nodes, not legal advice. They must pass
        citation validation and confidence checks before answer generation.
    """
```

## Comments

Use comments to explain **why**, not what the code already says.

Good:

```python
# Keep the whole Article as parent context because isolated Clauses often omit
# definitions or conditions needed for legal interpretation.
```

Bad:

```python
# Increment i by 1.
i += 1
```

## Documentation Files

Maintain:

```text
README.md
PROJECT_CONTEXT.md
AGENTS.md
docs/end_to_end_pipeline.md
docs/project_phase_journal.md
docs/raw_data_crawling.md
docs/raw_corpus_audit.md
docs/cleaning_normalization.md
docs/legal_parsing.md
docs/parent_child_chunking.md
docs/processed_jsonl.md
docs/naive_rag.md
docs/advanced_rag.md
docs/graphrag_agents.md
docs/evaluation.md
docs/api_deployment.md
docs/mlops_maintenance.md
```

Minimum expectations:

- `README.md`: setup, quickstart, commands, API example.
- `PROJECT_CONTEXT.md`: current phase, completed phases, next tasks.
- `docs/end_to_end_pipeline.md`: system architecture and data flow.
- `docs/project_phase_journal.md`: chronological implementation notebook.
- `docs/raw_data_crawling.md`, `docs/raw_corpus_audit.md`, and
  `docs/cleaning_normalization.md`: implemented ingestion phases.
- `docs/legal_parsing.md`: current Phase 5 parser design.
- `docs/naive_rag.md`, `docs/advanced_rag.md`, and `docs/graphrag_agents.md`: future retrieval strategy.
- `docs/evaluation.md`: RAGAS, legal metrics, golden datasets.
- `docs/api_deployment.md`: request/response schemas, deployment, and security.

## Review Checklist

- [ ] Public APIs have useful Google-style docstrings.
- [ ] Docstrings mention legal/RAG assumptions where relevant.
- [ ] Examples are accurate and executable.
- [ ] README commands are current.
- [ ] Architecture docs match the codebase.
- [ ] Documentation does not invent features.
- [ ] Comments explain reasoning, not syntax.
- [ ] No secrets, tokens, or private URLs are documented accidentally.

## Do Not

- Do not write vague docstrings such as “process data”.
- Do not document behavior that the code does not implement.
- Do not use comments to restate obvious code.
- Do not omit legal assumptions in parser, retrieval, citation, or generation code.
- Do not leave stale setup commands in README.
