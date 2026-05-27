---
name: vnlaw-project-charter
description: Use when Claude needs the overall VnLaw-QA mission, product scope, trusted legal corpus, roadmap, architecture decisions, phase plan, or implementation priorities.
allowed-tools: Read, Grep, Glob, LS, Bash, Edit, MultiEdit, Write
---

# VnLaw-QA Project Charter Skill

Use this skill to orient major work in the repository.

This skill defines the mission, architecture direction, trusted corpus policy, and implementation priority.

## Mission

VnLaw-QA is a Vietnamese legal question-answering system.

The system must answer legal questions in Vietnamese with:

- strict grounding in retrieved legal documents;
- correct Article, Clause, Point, Law Name, and law version;
- time-aware legal validity;
- explicit citations;
- fallback when evidence is insufficient;
- a clear note that the system does not replace qualified legal advice.

## Target Users

```text
citizens
small businesses
law students
paralegals
```

The system provides legal research support, not professional legal representation.

## Primary Architecture Roadmap

Implement in this order:

### 1. Naive RAG Baseline

```text
single retriever
simple context packing
strict citation prompt
fallback behavior
golden QA baseline
```

### 2. Advanced RAG

```text
dense + sparse hybrid search
Reciprocal Rank Fusion
cross-encoder reranking
time-aware legal filtering
query decomposition where useful
context packing
citation validation
```

### 3. GraphRAG

```text
Neo4j legal graph
cross-reference traversal
Law / Article / Clause / Entity nodes
REFERENCES / AMENDS / SUPERSEDES / BELONGS_TO edges
vector explorer + graph explorer + orchestrator
```

### 4. Fine-Tuning and MLOps

```text
synthetic legal QA if justified
QLoRA only after retrieval quality is stable
vLLM serving
CI/CD
monitoring
safety gates
```

## Core Architecture Decisions

- Use Qdrant for dense/sparse vector search.
- Use Neo4j for cross-reference and legal graph traversal.
- Use parent-child chunking: index Clause/Point-level child nodes, provide Article-level parent context to the LLM.
- Use BGE-M3-style dense+sparse embeddings where appropriate.
- Use cross-encoder reranking before final context selection.
- Use RAGAS plus legal-specific metrics for evaluation.
- Use FastAPI for API serving.
- Use Pydantic V2 for schemas and configuration.

## Trusted Corpus Rule

Default trusted source:

```text
https://thuvienphapluat.vn
```

Do not add other sources without explicit approval and documentation.

## Corpus Priority

Resolve legal conflicts using:

```text
Tier 0: Constitution
Tier 1: Core Codes
Tier 2: Essential Law Groups
Tier 3: Decrees and Circulars
```

Prefer consolidated VBHN versions when available.

## Planning Output

When this skill is used for planning, return:

```text
Project understanding:
Relevant phase:
Relevant modules:
Recommended implementation path:
Risks:
Tests/evaluation required:
Files likely to change:
```

## Do Not

- Do not start with GraphRAG before Naive RAG works.
- Do not start fine-tuning before retrieval and citation validation are stable.
- Do not add unapproved legal sources.
- Do not ignore legal validity dates.
- Do not optimize architecture before the parser and corpus are reliable.