---
name: vnlaw-graphrag-agents
description: Use when implementing GraphRAG, Neo4j schema, cross-reference extraction, legal graph traversal, routing, and multi-agent retrieval orchestration.
allowed-tools: Read, Grep, Glob, LS, Bash, Edit, MultiEdit, Write
---

# GraphRAG and Agent Orchestration Skill

Use this skill for graph-based legal retrieval and multi-hop legal evidence discovery (Phase 11).

**Prerequisites**: Phase 9 (Naive RAG) and Phase 10 (Advanced RAG) must be stable.

## Goal

Support questions that require:

- cross-references;
- amendments;
- supersession;
- legal validity relationships;
- multi-hop evidence;
- procedure or penalty chains.

GraphRAG must expand evidence, not replace legal text citation.

## Expected Files

```text
src/retrieval/graph_store.py        # Neo4j operations
src/ingestion/graph_extractor.py    # cross-reference extraction from chunks
src/agents/router.py                # intent classification
src/agents/vector_explorer.py       # Qdrant evidence retrieval
src/agents/graph_explorer.py        # Neo4j traversal
src/agents/orchestrator.py          # multi-agent evidence merging
tests/unit/retrieval/test_graph_store.py
tests/unit/agents/
```

## Neo4j Node Types

Use at minimum:

```text
Law, Article, Clause, Entity
```

Optional:

```text
Point, Procedure, Penalty, Organization, Concept
```

## Edge Types

Use at minimum:

```text
BELONGS_TO, REFERENCES, AMENDS, SUPERSEDES, RELATED_TO, DEFINES, MENTIONS
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

Extract references from parsed legal text:

```text
"theo Điều 79 của Luật này"
"Khoản 2 Điều này"
"Điều 145 của Bộ luật Tố tụng hình sự"
```

Each reference must preserve:

```text
anchor_text, context_snippet
source_article_id, target_article_id (if resolved)
ref_type, ref_relation, confidence
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
GraphStore              # Protocol for graph operations
Neo4jGraphStore         # Neo4j implementation
CrossReferenceExtractor # reference extraction from chunks
IntentRouter            # query intent classification
VectorExplorer          # Qdrant retrieval agent
GraphExplorer           # Neo4j traversal agent
AgentOrchestrator       # multi-agent evidence merging
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
