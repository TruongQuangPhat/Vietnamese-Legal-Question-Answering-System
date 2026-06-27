---

name: vnlaw-naive-rag
description: Use when maintaining, debugging, or extending the Naive RAG baseline, including simple retrieval, evidence packing, strict legal prompting, citation validation, fallback handling, and baseline evaluation.
---

# Naive RAG Baseline Skill

Use this skill when working on the baseline legal QA/RAG pipeline.

Naive RAG is no longer a future-only plan. It is the baseline system used for comparison against Advanced RAG. The current best evaluated workflow uses coverage-aware hybrid retrieval and strict generation with an answerability fallback guard, but Naive RAG remains important as a simple, reproducible baseline.

## Goal

Maintain a simple and safe legal QA pipeline:

```text
query
  → baseline retrieval
  → evidence selection / context packing
  → strict legal QA prompt
  → LLM generation
  → citation validation
  → fallback if unsupported
  → baseline evaluation
```

## Baseline Role

Naive RAG should be kept simple and reliable.

Use it to:

* provide a reproducible baseline for later retrieval/generation improvements;
* test strict legal prompting and citation validation;
* verify fallback behavior when evidence is insufficient;
* compare against Advanced RAG and strict generation workflows.

Do not use Naive RAG as the final best system if the task is about reporting current benchmark results. For current final metrics, refer to Advanced RAG / strict generation evaluation documentation.

## Retrieval Guidance

Keep baseline retrieval simple:

```text
dense retrieval or simple retrieval strategy
top-k evidence candidates
evidence selection
strict prompt context
```

Avoid adding complex reranking, query decomposition, graph traversal, multi-agent orchestration, or benchmark-specific policy into the Naive RAG baseline.

## Prompt Requirements

The LLM must be instructed to:

* answer only from provided evidence;
* cite every legal claim using selected citation IDs;
* preserve Article/Clause/Point hierarchy when available;
* say it cannot find enough legal basis when context is insufficient;
* avoid professional legal advice;
* not use model memory as legal evidence.

## Citation and Fallback Requirements

Fallback is required when:

```text
retrieval returns no useful evidence
selected evidence is empty
evidence is unsafe or parent-context-only
required citation metadata is missing
citation validation fails
the question is outside the current corpus
the evidence is insufficient to answer safely
```

Parent context may be included as auxiliary context, but it must not be treated as directly citable evidence.

## Evaluation Guidance

Naive RAG evaluation should remain reproducible and comparable.

When changing Naive RAG behavior:

* keep benchmark inputs unchanged;
* do not tune on held-out test;
* report decision accuracy, answer rate, safe fallback rate, citation validity, evidence coverage, and case pass rate when available;
* compare results against the latest Advanced RAG / strict generation workflow only as a baseline comparison;
* do not overwrite official evaluation artifacts unless explicitly asked.

## Implementation Boundaries

When working on this skill:

* keep retrieval, evidence selection, prompting, generation, citation validation, and fallback policy separated;
* use typed models for candidates, evidence packets, citations, and responses;
* preserve legal hierarchy metadata;
* keep public classes/functions documented with Google-style docstrings where project style requires it;
* use tests with mocks/fakes for LLMs, retrievers, and external services.

## Do Not

* Do not over-engineer the baseline.
* Do not add GraphRAG or agent orchestration to Naive RAG.
* Do not make parent context directly citable.
* Do not allow uncited legal claims.
* Do not fabricate laws, articles, clauses, points, dates, penalties, or citations.
* Do not use model memory as legal evidence.
* Do not skip citation validation.
* Do not call real LLMs, Qdrant, embeddings, or full benchmark pipelines unless the user explicitly scopes that run.
