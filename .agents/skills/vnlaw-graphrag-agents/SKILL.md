---
name: vnlaw-graphrag-agents
description: Use when implementing future or separately scoped GraphRAG work, Neo4j schema, cross-reference extraction, legal graph traversal, routing, and multi-agent retrieval orchestration.
---

# GraphRAG and Agent Orchestration Skill

Use this skill for graph-based legal retrieval, cross-reference expansion, and multi-hop legal evidence discovery.

## Current Status

GraphRAG and agent orchestration are future or separately scoped work.

Naive RAG and Advanced RAG are already implemented/evaluated. The current adopted workflow uses coverage-aware hybrid retrieval, evidence selection, strict legal generation, citation ID guard, and answerability fallback guard.

Do not create graph, agent, router, or Neo4j modules unless the user explicitly scopes a GraphRAG/agent task.

GraphRAG must expand and organize evidence. It must not replace citation-ready legal text.

## Goal

Support questions that require:

* cross-references;
* amendments;
* supersession;
* legal validity relationships;
* multi-hop evidence;
* procedure or penalty chains.

GraphRAG should improve evidence discovery while preserving strict citation and fallback behavior.

## Expected Future Files

Use the repository’s current structure when implementation is explicitly scoped. Possible files may include:

```text id="ywp4u1"
src/retrieval/graph_store.py
src/ingestion/graph_extractor.py
src/retrieval/router.py
src/retrieval/vector_explorer.py
src/retrieval/graph_explorer.py
src/services/retrieval_orchestration_service.py

tests/unit/retrieval/test_graph_store.py
tests/unit/retrieval/test_cross_reference_extractor.py
tests/unit/retrieval/test_graph_explorer.py
tests/integration/retrieval/test_graphrag_workflow.py

artifacts/reports/retrieval/
artifacts/traces/retrieval/
artifacts/metrics/retrieval/
```

Do not create these files unless the task explicitly scopes GraphRAG implementation.

## Neo4j Node Types

Use at least:

```text id="e3bmus"
Law
Article
Clause
Entity
```

Optional:

```text id="ljm93l"
Point
Procedure
Penalty
Organization
Concept
```

## Edge Types

Use at least:

```text id="hcxocy"
BELONGS_TO
REFERENCES
AMENDS
SUPERSEDES
RELATED_TO
DEFINES
MENTIONS
```

## Constraints

Create uniqueness constraints:

```cypher id="qjryva"
CREATE CONSTRAINT law_id IF NOT EXISTS
FOR (l:Law) REQUIRE l.law_id IS UNIQUE;

CREATE CONSTRAINT article_id IF NOT EXISTS
FOR (a:Article) REQUIRE a.article_id IS UNIQUE;
```

Never build unsafe Cypher strings from raw user input.

## Cross-Reference Extraction

Extract references such as:

```text id="r2d8be"
Điều 79 của Luật này
Khoản 2 Điều này
Điều 145 của Bộ luật Tố tụng hình sự
```

Each reference must preserve:

```text id="bzmft5"
anchor_text
context_snippet
source_article_id
target_article_id if resolved
ref_type
ref_relation
confidence
```

Unresolved references must be stored as unresolved, not hallucinated.

## Agent Roles

### Intent Router

Classifies query into:

```text id="dq13f4"
exact_article_lookup
semantic_legal_question
cross_reference_question
version_validity_question
procedure_question
insufficient_context
```

### Vector Explorer

Retrieves citable legal evidence from the current retrieval system.

### Graph Explorer

Expands related evidence through graph relationships.

### Orchestrator

Merges vector and graph evidence, removes duplicates, preserves citation anchors, and refuses unsupported answers.

The orchestrator must only pass citation-ready child evidence to generation. Graph metadata alone is not sufficient legal evidence.

## Citation and Fallback Rules

GraphRAG must preserve current legal QA safety behavior:

* no trusted source -> no confident legal answer;
* no traceable citation -> fallback;
* graph edges must not become citations by themselves;
* parent context and graph metadata are auxiliary only;
* citable child legal text remains the answer source;
* unresolved references must not be guessed;
* unsupported multi-hop answers must fallback.

## OOP and Docstring Rules

Expected components:

```text id="oz1fx8"
GraphStore
Neo4jGraphStore
CrossReferenceExtractor
IntentRouter
VectorExplorer
GraphExplorer
AgentOrchestrator
```

Rules:

* Use typed graph node/edge models.
* Keep graph extraction separate from graph traversal.
* Keep routing separate from answer generation.
* Public classes/functions must have Google-style docstrings where project style requires it.
* Docstrings must explain graph assumptions, unresolved reference behavior, citation requirements, and fallback behavior.

## Verification

When GraphRAG is explicitly implemented, verify:

* cross-reference extraction works on known examples;
* graph edges never point to fabricated article IDs;
* unresolved references remain unresolved;
* graph retrieval returns legal text or resolvable evidence;
* graph expansion improves evidence coverage without lowering citation precision;
* router classification is measured on a small test set;
* tests use fake graph stores or tiny fixtures unless real Neo4j is explicitly scoped.

## Do Not

* Do not create graph/agent/Neo4j modules unless explicitly scoped.
* Do not let agents invent graph edges.
* Do not answer from graph metadata alone if citable legal text is missing.
* Do not use graph traversal as a replacement for citation evidence.
* Do not make unresolved references look resolved.
* Do not build unsafe Cypher strings from raw input.
* Do not bypass citation validation or fallback checks.
* Do not run real Neo4j, Qdrant, LLM, embedding, reranking, or full benchmark workflows unless explicitly scoped.
