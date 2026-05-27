---
name: vnlaw-docstrings-documentation
description: Use when adding or reviewing Google-style docstrings, README content, API docs, architecture docs, comments, and developer documentation for VnLaw-QA.
allowed-tools: Read, Grep, Glob, LS, Bash, Edit, MultiEdit, Write
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
docs/architecture.md
docs/ingestion.md
docs/retrieval.md
docs/evaluation.md
docs/security.md
docs/api.md
```

Minimum expectations:

- `README.md`: setup, quickstart, commands, API example.
- `docs/architecture.md`: system architecture and data flow.
- `docs/ingestion.md`: source registry, crawler, parser, chunking notes.
- `docs/retrieval.md`: Naive RAG, Advanced RAG, reranking, GraphRAG strategy.
- `docs/evaluation.md`: RAGAS, legal metrics, golden datasets.
- `docs/security.md`: secrets, PII, logging, deployment safety.
- `docs/api.md`: request/response schemas and endpoint examples.

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