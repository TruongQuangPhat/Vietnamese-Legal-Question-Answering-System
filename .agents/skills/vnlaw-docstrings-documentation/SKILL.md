---
name: vnlaw-docstrings-documentation
description: Use when adding or reviewing Google-style docstrings, README content, API docs, architecture docs, comments, developer documentation, and project context for VnLaw-QA.
---

# Docstrings and Documentation Skill

Use this skill whenever writing or reviewing code documentation, developer docs, API docs, architecture docs, inline comments, README content, or project context files.

Documentation should reflect the implemented system accurately without inventing features or rewriting useful component docs unnecessarily.

## Mandatory Docstring Coverage

Every public or non-trivial item should have a useful Google-style docstring:

* public class;
* public function;
* public method;
* Pydantic model;
* parser/chunker component;
* retrieval component;
* evidence selection component;
* generation/citation/fallback component;
* evaluation script;
* API endpoint, if API work is explicitly scoped;
* non-trivial algorithm.

## Docstring Requirements

Good docstrings should explain:

* purpose;
* arguments;
* return value;
* raised exceptions;
* side effects;
* legal assumptions;
* RAG/retrieval assumptions;
* fallback behavior when relevant;
* examples when helpful.

Use Google-style docstrings:

```python
async def search(
    self,
    query: str,
    top_k: int,
) -> list[LegalCandidate]:
    """Search legal chunks with the configured retrieval strategy.

    Args:
        query: Vietnamese legal question or search expression.
        top_k: Maximum number of candidates returned after retrieval/fusion.

    Returns:
        Ranked legal candidates with legal metadata, hierarchy, source URL,
        citation information, and retrieval scores.

    Raises:
        RetrievalError: If the retrieval backend fails.
        InvalidQueryError: If the query is empty or unsafe.

    Legal assumptions:
        Returned candidates are evidence candidates, not legal advice. They must
        pass evidence selection, citation validation, and fallback checks before
        answer generation can be treated as supported.
    """
```

Avoid documenting future-only behavior as current behavior. For example, do not describe time-aware filtering, reranking, GraphRAG, or API deployment as adopted unless that task is explicitly implemented and evaluated.

## Comments

Use comments to explain **why**, not what the code already says.

Good:

```python
# Keep the whole Article as auxiliary parent context because isolated Clauses
# often omit definitions or conditions needed for legal interpretation.
```

Bad:

```python
# Increment i by 1.
i += 1
```

## Documentation Files

Maintain project documentation such as:

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
docs/embedding_indexing.md
docs/naive_rag.md
docs/advanced_rag.md
docs/graphrag_agents.md
docs/evaluation.md
docs/api_deployment.md
docs/mlops_maintenance.md
```

Minimum expectations:

* `README.md`: professional project overview, architecture, setup, common commands, current results, safety scope, limitations.
* `PROJECT_CONTEXT.md`: current implemented system state, protected paths, safety invariants, final evaluated workflows, and operational boundaries.
* `AGENTS.md`: stable contributor rules, protected paths, safe validation commands, and no-secrets/no-real-service boundaries.
* `docs/end_to_end_pipeline.md`: current system architecture and data flow.
* `docs/raw_data_crawling.md`, `docs/raw_corpus_audit.md`, and `docs/cleaning_normalization.md`: ingestion and corpus processing documentation.
* `docs/legal_parsing.md`, `docs/parent_child_chunking.md`, and `docs/processed_jsonl.md`: legal hierarchy parsing, chunking, and processed JSONL contracts.
* `docs/embedding_indexing.md`: BGE-M3/Qdrant indexing behavior and dense vector contract.
* `docs/naive_rag.md`: baseline RAG behavior, not the final best system.
* `docs/advanced_rag.md`: final adopted Advanced RAG retrieval and strict generation evaluation.
* `docs/evaluation.md`: benchmark, metrics, splits, limitations, and evaluation workflows.
* `docs/graphrag_agents.md`, `docs/api_deployment.md`, and `docs/mlops_maintenance.md`: future/planned documentation unless those systems are explicitly implemented.

## Current Documentation Facts

Where relevant, documentation should reflect:

```text
- Corpus: 52 Vietnamese legal documents.
- Processed chunks: 40,389 legal chunks.
- Embedding model: BAAI/bge-m3.
- Dense vector name: dense.
- Dense vector dimension: 1024.
- Qdrant collection: vnlaw_chunks_bgem3_v1_full.
- Benchmark v0.1.0: 128 queries.
- Development split: 85 queries.
- Held-out test split: 43 queries.
- Held-out test is reporting-only.
- Final adopted retrieval: coverage_aware_quota.
- Reranking was evaluated but not adopted.
- Final strict generation uses citation ID guard and answerability fallback guard.
- Parent context is auxiliary only and not directly citable.
- Integration tests exist for corpus, retrieval, and evaluation workflows.
```

Do not overload every doc with all metrics. Put detailed results in `README.md`, `docs/advanced_rag.md`, `docs/evaluation.md`, and `PROJECT_CONTEXT.md`.

## Documentation Update Rules

When updating docs:

* preserve useful technical detail;
* patch stale facts in place;
* add a short "Current status" section when helpful;
* avoid replacing detailed component docs with short summaries;
* avoid turning README or context files into phase trackers;
* mark future/planned docs clearly instead of deleting useful design notes;
* do not claim API, GraphRAG, time-aware filtering, or reranking is adopted unless explicitly implemented and evaluated;
* do not document behavior that the code does not implement;
* do not include secrets, tokens, private URLs, or real credentials.

README may be rewritten more substantially when needed, but docs and skills should usually be updated with targeted patches.

## Review Checklist

* [ ] Public APIs have useful Google-style docstrings.
* [ ] Docstrings mention legal/RAG assumptions where relevant.
* [ ] Examples are accurate and match implemented behavior.
* [ ] README commands are current.
* [ ] Architecture docs match the codebase.
* [ ] Documentation does not invent features.
* [ ] Future/planned features are clearly labeled.
* [ ] Naive RAG is described as baseline, not final best system.
* [ ] Advanced RAG is described as implemented/evaluated, not future-only.
* [ ] Reranking is described as evaluated but not adopted.
* [ ] Parent context is described as auxiliary only.
* [ ] Comments explain reasoning, not syntax.
* [ ] No secrets, tokens, or private URLs are documented accidentally.

## Do Not

* Do not write vague docstrings such as “process data”.
* Do not document behavior that the code does not implement.
* Do not describe future-only features as current features.
* Do not use comments to restate obvious code.
* Do not omit legal assumptions in parser, retrieval, citation, or generation code.
* Do not leave stale setup commands in README.
* Do not rewrite all docs or skills wholesale when a targeted patch is enough.
* Do not drastically shorten detailed documentation without explicit approval.
