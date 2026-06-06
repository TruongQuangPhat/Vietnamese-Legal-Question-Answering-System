---
name: vnlaw-graphrag-agents
description: Use when implementing GraphRAG, Neo4j schema, cross-reference extraction, legal graph traversal, routing, and multi-agent retrieval orchestration.
---

# GraphRAG and Agent Orchestration Skill

Use this skill for graph-based legal retrieval and multi-hop legal evidence discovery.

Use GraphRAG only after Naive RAG and Advanced RAG are working.
Current project status: GraphRAG and agent orchestration are future phases. Do
not create graph, agent, or Neo4j modules until Naive RAG and Advanced RAG
gates have passed.

## Goal

Support questions that require:

- cross-references;
- amendments;
- supersession;
- legal validity relationships;
- multi-hop evidence;
- procedure or penalty chains.

GraphRAG must expand evidence, not replace legal text citation.

## Expected Future Files

```text
src/retrieval/graph_store.py
src/ingestion/graph_extractor.py
src/retrieval/router.py
src/retrieval/vector_explorer.py
src/retrieval/graph_explorer.py
src/services/retrieval_orchestration_service.py
tests/unit/retrieval/test_graph_store.py
tests/unit/retrieval/
artifacts/reports/retrieval/
artifacts/traces/retrieval/
artifacts/metrics/retrieval/
```

## Neo4j Node Types

Use at least:

```text
Law
Article
Clause
Entity
```

Optional:

```text
Point
Procedure
Penalty
Organization
Concept
```

## Edge Types

Use at least:

```text
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

```cypher
CREATE CONSTRAINT law_id IF NOT EXISTS
FOR (l:Law) REQUIRE l.law_id IS UNIQUE;

CREATE CONSTRAINT article_id IF NOT EXISTS
FOR (a:Article) REQUIRE a.article_id IS UNIQUE;
```

Never build unsafe Cypher strings from raw user input.

## Cross-Reference Extraction

Extract references such as:

```text
Điều 79 của Luật này
Khoản 2 Điều này
Điều 145 của Bộ luật Tố tụng hình sự
```

Each reference must preserve:

```text
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

```text
exact_article_lookup
semantic_legal_question
cross_reference_question
version_validity_question
procedure_question
insufficient_context
```

### Vector Explorer

Retrieves legal evidence from Qdrant.

### Graph Explorer

Expands related legal evidence through Neo4j relationships.

### Orchestrator

Merges vector and graph evidence, removes duplicates, preserves citation anchors, and refuses unsupported answers.

## OOP and Docstring Rules

Expected components:

```text
GraphStore
Neo4jGraphStore
CrossReferenceExtractor
IntentRouter
VectorExplorer
GraphExplorer
AgentOrchestrator
```

Rules:

- Use typed graph node/edge models.
- Keep graph extraction separate from graph traversal.
- Keep routing separate from answer generation.
- Public classes/functions must have Google-style docstrings.
- Docstrings must explain graph assumptions and unresolved reference behavior.

## Verification

- Cross-reference extraction works on known examples.
- Graph edges never point to fabricated article IDs.
- Graph retrieval returns legal text or resolvable evidence.
- Graph expansion improves recall without lowering citation precision.
- Router classification accuracy is measured on a test set.

## Do Not

- Do not let agents invent graph edges.
- Do not answer from graph metadata alone if legal text is missing.
- Do not use graph traversal as a replacement for citation evidence.
- Do not build unsafe Cypher strings from raw input.
- Do not add multi-agent orchestration before retrieval quality is stable.
