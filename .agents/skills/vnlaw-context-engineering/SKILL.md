---
name: vnlaw-context-engineering
description: Use for legal prompt design, evidence/context packing, evidence ordering, citation anchors, answer structure, fallback behavior, and hallucination prevention in Vietnamese legal QA.
---

# Context Engineering Skill

Use this skill to maintain, review, or extend prompts, evidence packets, answer formats, and fallback behavior for Vietnamese legal QA.

Current project status: context engineering for QA is implemented as part of the legal RAG workflow. Evidence packing, strict legal prompting, citation validation, and fallback control are no longer future-only tasks. The current best evaluated workflow uses coverage-aware hybrid retrieval, citable child evidence selection, strict generation, citation ID guard, and answerability fallback guard.

## Objectives

* Maximize legal faithfulness.
* Keep citations traceable.
* Preserve citation anchors.
* Provide enough auxiliary parent context without making parent context directly citable.
* Prevent hallucination.
* Make fallback behavior explicit.
* Preserve legal hierarchy when available.
* Avoid unsupported legal advice.

## Evidence Packet Format

Each selected evidence packet should be citation-ready and include:

```text
[Evidence {i}]
Evidence ID: {chunk_id}
Law: {law_name}
Law ID: {law_id}
Hierarchy: {Part > Chapter > Section > Article > Clause > Point}
Citation: {citation}
Source URL: {source_url}
Retrieval Score: {retrieval_score}

Citable child excerpt:
{child_text}

Auxiliary parent context:
{parent_context}
```

Optional fields may include:

```text
version_or_vbhn
effective_date
expiry_date
retrieval_source
fusion_score
rerank_score  # only for controlled reranking ablations
```

Parent context is auxiliary only. It must not be treated as directly citable evidence.

## Prompt Rules

The generation prompt must instruct the model to:

* use only provided selected evidence;
* cite every legal claim using valid evidence IDs;
* never invent laws, articles, clauses, points, penalties, dates, or citations;
* preserve Article/Clause/Point hierarchy when available;
* distinguish cited legal basis from explanation;
* fallback when evidence is insufficient, unsafe, indirect, parent-only, or missing citation metadata;
* avoid professional legal advice beyond the cited documents;
* not use model memory as legal evidence.

## Query Processing Techniques

Use only when clearly helpful and separately scoped:

* query normalization;
* legal term preservation;
* exact article detection;
* legal reference extraction;
* lightweight query expansion;
* query decomposition for multi-part questions.

Do not apply query rewriting if it removes important legal terms or changes legal meaning.

Date extraction and time-aware filtering are future/separately scoped unless explicitly implemented and evaluated.

## Evidence Ordering

Prefer ordering by:

1. direct exact citation or article/clause/point match;
2. required evidence coverage;
3. lexical match for legal terms and article references;
4. dense semantic relevance;
5. source/legal hierarchy completeness;
6. parent-child completeness;
7. auxiliary cross-reference support.

Do not prioritize rerank score in the adopted pipeline. Rerank score is only relevant for controlled reranking ablations.

## Context Budget Policy

When context is too large:

1. keep citable child evidence first;
2. keep exact article/clause/point matches;
3. keep parent context only for the selected child evidence;
4. drop low-score unrelated chunks;
5. preserve citation IDs and source URLs;
6. never summarize away citation anchors.

## Answer Format

Default answer format:

```text
Legal issue:
Applicable legal basis:
Answer:
Sources:
Limitations:
```

For insufficient evidence, use fallback instead of guessing:

```text
I could not find sufficient legal basis in the provided corpus to answer this safely.
```

## Expected Components

Use the repository’s current structure. Relevant components may include:

```text
Evidence packet / EvidenceBundle models
Context packing utilities
Legal prompt builder
Answer formatter
Citation guard / citation validator
Fallback policy
Strict generation evaluation workflow
```

Do not create new prompt/context modules unless the task explicitly scopes implementation work.

## OOP and Docstring Rules

Expected components may include:

```text
ContextPacker
LegalPromptBuilder
CitationAnchorBuilder
AnswerFormatter
FallbackPolicy
CitationGuard
```

Rules:

* Keep prompt construction separate from retrieval and LLM client logic.
* Use typed evidence packet models.
* Public classes/functions must have Google-style docstrings where project style requires it.
* Docstrings must explain legal assumptions, citation requirements, and fallback behavior.

## Evaluation Notes

When changing context packing or prompts:

* use fake LLM/retriever tests for unit and integration coverage;
* do not call real LLMs unless explicitly scoped;
* do not tune on held-out test;
* track citation validity, fallback behavior, evidence coverage, decision accuracy, and case pass rate where available;
* compare against the latest strict generation evaluation only when running a scoped evaluation task.

## Do Not

* Do not stuff too many unrelated chunks.
* Do not make parent context directly citable.
* Do not mix expired and active laws without explicit time-aware support.
* Do not hide low confidence.
* Do not summarize away citation anchors.
* Do not let the final answer cite evidence that was not selected.
* Do not rewrite queries in a way that changes legal meaning.
* Do not use reranking or time-aware filtering as adopted behavior unless separately scoped and evaluated.
* Do not call real LLM/Qdrant/embedding/reranking/full benchmark workflows unless explicitly requested.
