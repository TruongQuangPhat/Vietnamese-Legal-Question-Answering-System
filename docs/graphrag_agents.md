# GraphRAG & Agentic Legal Reasoning

## Overview

GraphRAG extends the retrieval pipeline by introducing a legal knowledge graph and agent orchestration. This phase enables multi-hop reasoning across related legal provisions (e.g., following cross-references between articles, tracing amendment chains). It is implemented **only after** Naive RAG and Advanced RAG are stable and meet quality thresholds.

GraphRAG is not a replacement for vector retrieval; it augments it with explicit legal relationships encoded in a graph database (Neo4j). An agent orchestrator routes queries, combines evidence, and validates synthesized answers.

## Quick Start

**Intended system behavior** (design phase, not yet implemented):

```bash
# Start Neo4j and load legal graph
docker-compose up neo4j
uv run python -m src.graphrag.build --input data/processed --output neo4j_import/

# Run agent-based QA
curl -X POST "http://localhost:8000/api/v1/graph_qa" \
  -H "Content-Type: application/json" \
  -d '{"query": "Quan hệ giữa Luật Đất đai 2024 và Nghị định 123/2025/NĐ-CP?"}'
```

## Architecture

```
┌──────────────────────┐
│  Processed Legal     │
│  Tree (hierarchy)    │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Graph Node          │
│  Builder             │
│  (Law, Article,      │
│   Clause, Point,     │
│   Entity, etc.)      │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Legal Edge          │
│  Extractor           │
│  (BELONGS_TO,        │
│   REFERENCES,        │
│   AMENDS,            │
│   SUPERSEDES,        │
│   DEFINES,           │
│   RELATED_TO)        │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Neo4j Graph         │
│  Store               │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Graph               │
│  Retriever           │
│  (traversal)         │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Agent               │
│  Orchestrator        │
│  (router, merger,    │
│   validator)         │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Multi-hop Evidence  │
│  Pack                │
└──────────────────────┘
```

## Components

### 1. Graph Node Builder

**Goal**: Create node entities from legal hierarchy and additional NLP extraction.

**Node types**:
- `Law`: metadata (law_id, name, type, status, dates)
- `Article`: Điều (links to Law, contains Clause/Point)
- `Clause`: Khoản
- `Point`: Điểm
- `Entity`: organizations, people, places (extracted via NER)
- `Procedure`: legal processes (e.g., "đăng ký quyền sử dụng đất")
- `Penalty`: punishments, fines, imprisonment terms

**Properties** (common):
- `id`: unique node ID (same as chunk_id for Article/Clause/Point)
- `law_id`, `law_name`
- `text`: content (for Article/Clause/Point); description for others
- `source_url`, `effective_date`, `legal_status`

**Process**:
- Iterate through all `LegalNode` objects from parser.
- Create corresponding graph nodes with consistent IDs.
- Additional entity nodes via NER on legal text (optional, future).

### 2. Legal Edge Extractor

**Goal**: Define relationships between nodes.

**Edge types**:

| Type | Direction | Meaning |
|------|-----------|---------|
| `BELONGS_TO` | child → parent | Clause/Point → Article; Article → Law |
| `REFERENCES` | Article A → Article B | Article cites another article (internal or external) |
| `AMENDS` | New Law → Old Law | Newer law amends older |
| `SUPERSEDES` | New → Old | New fully replaces old |
| `DEFINES` | Law → Entity/Concept | Law defines a term |
| `RELATED_TO` | Node A ↔ Node B | Semantic similarity (from embedding) |

**Extraction**:
- `BELONGS_TO`: automatic from hierarchy tree.
- `REFERENCES`: regex patterns detecting "theo quy định tại Điều X", reference to other laws.
- `AMENDS` / `SUPERSEDES`: from registry `status` field and amendment metadata.
- `DEFINES`: heuristic: Article contains "trong luật này, ... là ..."
- `RELATED_TO`: computed from vector similarity between node embeddings (thresholded).

### 3. Neo4j Graph Store

**Goal**: Persist graph with performant traversal queries.

**Setup**:
- Neo4j database with constraints: `UNIQUE (n:Law {law_id})`, `UNIQUE (n:Article {id})`, etc.
- Indexes on `law_id`, `effective_date`, `legal_status`.
- Import via `neo4j-admin import` for bulk load or Cypher `CREATE` for incremental.

**Cypher schema**:
```cypher
CREATE CONSTRAINT article_id_unique IF NOT EXISTS FOR (a:Article) REQUIRE a.id IS UNIQUE;
CREATE INDEX article_effective_date IF NOT EXISTS FOR (a:Article) ON (a.effective_date);
```

### 4. Graph Retriever

**Goal**: Retrieve related provisions via graph traversal, complementing vector retrieval.

**Query patterns**:
- **Direct reference**: Given retrieved Article A, follow `REFERENCES` edges → fetch referenced Articles B, C.
- **Amendment chain**: Follow `AMENDS`/`SUPERSEDES` to find current version.
- **Definition lookup**: If query mentions a term, follow `DEFINES` to authoritative definition.
- **Multi-hop**: Traverse up to depth 2 (e.g., Clause → Article → Law → other Articles in same Law).

**Process**:
1. Start from seed nodes (retrieved by vector search).
2. Run Cypher query to traverse specified edge types.
3. Collect additional Article/Clause/Point nodes.
4. Merge with vector-retrieved nodes, deduplicate.
5. Rank by combination of vector score + graph centrality.

**Output**: Extended set of relevant chunks for context packing.

### 5. Agent Orchestrator

**Goal**: Coordinate multiple retrievers and validation steps.

**Agents**:

| Agent | Responsibility |
|-------|-----------------|
| Intent Router | Classify query: needs graph traversal? pure retrieval? |
| Vector Retriever | Perform initial hybrid search (from Advanced RAG) |
| Graph Retriever | Execute graph traversal based on intent |
| Citation Validator | Verify answer citations exist in retrieved context |
| Answer Verifier | Cross-check answer consistency across evidence sources |

**Orchestration flow**:
1. Query → Intent Router decides `"graph_required"` vs `"vector_only"`.
2. If graph required → run Vector Retriever (top-20) → run Graph Retriever (expand to top-50).
3. Context Packing merges evidence from both sources, with citation anchors.
4. LLM Generation (same as Naive RAG but with enriched context).
5. Citation Validator and Answer Verifier run sequentially; if either fails, trigger fallback.
6. Return answer or fallback with reason.

**Fallback triggers**:
- No retrieved chunks after merging.
- Citation validator finds unsupported claims.
- Answer verifier detects contradiction between evidence and answer.

### 6. Multi-hop Evidence Pack

**Goal**: Present merged context to LLM in a structured, traceable way.

**Format**:
```
[Source: Vector retrieval, Score: 0.92]
[Citation: Luật Đất đai 2024, Điều 123, Khoản 2, Điểm c]
Nội dung của Điểm c...

[Source: Graph traversal, Relation: REFERENCES]
[Citation: Luật Đất đai 2024, Điều 124, Khoản 1]
Nội dung của Điều 124...
```

This transparency helps LLM understand provenance and aids citation validator.

## Pipeline Execution Flow

1. Build graph from legal hierarchy and cross-references → Neo4j.
2. Index vector store (already done from Advanced RAG).
3. For QA query:
   - Intent Router classifies.
   - Vector Retriever fetches initial top-k.
   - If graph needed, Graph Retriever traverses from seed nodes.
   - Merge results, deduplicate, sort by relevance.
   - Pack context with source labels.
   - Generate answer via LLM.
   - Validate citations and verify consistency.
   - Return answer or fallback.

## Data Models / Output Schema

### Graph Node Labels (Neo4j)

```cypher
(:Law {law_id, name, type, status, effective_date, expiry_date})
(:Article {id, law_id, number, title, text, effective_date})
(:Clause {id, article_id, number, text})
(:Point {id, clause_id, number, text})
(:Entity {id, name, type, description})
(:Procedure {id, name, steps})
(:Penalty {id, article_id, description, fine_amount, imprisonment_months})
```

### Graph Edge Types

```cypher
(:Clause)-[:BELONGS_TO]->(:Article)
(:Article)-[:BELONGS_TO]->(:Law)
(:Article)-[:REFERENCES {type: "internal"|"external"}]->(:Article)
(:Law)-[:AMENDS {amending_law_id}]->(:Law)
(:Law)-[:SUPERSEDES]->(:Law)
(:Law)-[:DEFINES {term}]->(:Entity)
(:Article)-[:RELATED_TO {similarity_score}]->(:Article)
```

### Agent Decision Log

For debugging, log agent decisions:
```json
{
  "query": "...",
  "intent": "graph_required",
  "vector_retrieved_count": 15,
  "graph_expanded_count": 8,
  "final_chunk_count": 22,
  "validation_passed": true,
  "fallback": false
}
```

## CLI Reference

### Graph Build Command

```bash
uv run python -m src.graphrag.build \
  --input data/processed \
  --neo4j-uri bolt://localhost:7687 \
  --user neo4j \
  --password secret
```

### Graph QA Command

```bash
uv run python -m src.graphrag.qa \
  --query "Quan hệ giữa Điều 123 và Điều 124?" \
  --qdrant-url http://localhost:6333 \
  --neo4j-uri bolt://localhost:7687
```

## Testing

**Unit tests**:
- `test_graph_node_builder()`: correct node types and properties from hierarchy.
- `test_edge_extraction_references()`: `REFERENCES` edges detected from text patterns.
- `test_neo4j_constraints()`: unique IDs enforced.
- `test_agent_router()`: query classification accurate.

**Integration tests**:
- Build graph for a small law (50 articles) → Neo4j node/edge counts match expectations.
- Graph traversal query: given Article A, retrieve all referenced Articles → correct.
- End-to-end GraphRAG QA: multi-hop question answered with citations from both vector and graph sources.

## Error Handling

- **Graph build failure**: Invalid hierarchy → log and abort; fix parser output.
- **Neo4j connection failure**: Retry with backoff; abort after N attempts.
- **Traversal timeout**: Limit graph traversal depth and result count; fallback to vector-only.
- **Agent deadlock**: Timeout per agent (e.g., 2s); if timeout, use partial results or fallback.
- **Inconsistent evidence**: Answer verifier finds contradiction → fallback with "conflicting sources" message.

All errors structured with `query_id` for tracing.

## Troubleshooting

| Issue | Possible Cause | How to Check | Recommended Fix |
|-------|----------------|--------------|-----------------|
| Graph traversal returns too many nodes | Depth too high or no filtering | Count retrieved nodes | Limit depth to 2; add similarity threshold |
| Missing `REFERENCES` edges | Pattern extraction failed | Manual Cypher query count | Improve regex patterns; consider NLP-based relation extraction |
| Agent loops (infinite) | Router repeatedly calls same agent | Check decision log | Add maximum iteration limit (e.g., 3 hops) |
| GraphRAG slower than vector-only | Traversal overhead | Profile time per stage | Cache traversal results; prune low-score edges |
| Contradictory answer from LLM | Evidence from vector and graph conflict | Inspect context pack sources | Improve answer verifier; weight graph higher for legal relationships |
| Neo4j import fails | CSV format error | Check Neo4j import logs | Validate node/edge CSV format; ensure required columns |

## Best Practices

- **Graph after stable RAG** — do not implement GraphRAG until retrieval quality is high; graph adds complexity.
- **Limit traversal depth** — legal graphs can have long chains; depth > 2 often unnecessary and hurts latency.
- **Cache graph results** — traverse results for common seed nodes can be cached.
- **Keep evidence provenance** — label context pack with "source: vector" vs "source: graph" for verifier.
- **Monitor graph health** — track graph size (nodes, edges), traversal latency, hit rate.
- **Version graph schema** — changes to node/edge types require migration; keep backward compatibility.

## Changelog

### Version 0.1 (2026-05-21)

- Created initial GraphRAG & agentic reasoning documentation.
- Defined graph nodes (Law, Article, Clause, Point, Entity, Procedure, Penalty) and edges (BELONGS_TO, REFERENCES, AMENDS, SUPERSEDES, DEFINES, RELATED_TO).
- Outlined agent orchestrator with intent router, retrievers, validators, verifier.
- Specified multi-hop evidence packing with source labels.
- Provided Neo4j schema examples and traversal patterns.
- Documented risks of premature agent implementation and testing strategy.

## Related Documentation

| Document | Status | Description |
|----------|--------|-------------|
| `docs/project_phase_journal.md` | Existing | Project phase journal and pipeline notes |
| `docs/project_setup.md` | Implemented | Environment setup and coding standards |
| `docs/corpus_registry.md` | Implemented | Corpus registry schema and design |
| `docs/raw_corpus_audit.md` | Designed | Raw artifact audit procedure |
| `docs/cleaning_normalization.md` | Existing | HTML-to-text and Unicode normalization |
| `docs/legal_parsing.md` | Existing | Legal hierarchy parsing algorithm |
| `docs/parent_child_chunking.md` | Existing | Parent-child chunking design |
| `docs/processed_jsonl.md` | Existing | JSONL export schema and validation |
| `docs/embedding_indexing.md` | Future extension | Embedding model and Qdrant indexing |
| `docs/naive_rag.md` | Future extension | Baseline RAG implementation |
| `docs/advanced_rag.md` | Future extension | Hybrid retrieval, reranking, time-aware filtering |
| `docs/evaluation.md` | Future extension | Evaluation metrics, golden QA dataset, CI gates |
| `docs/api_deployment.md` | Future extension | FastAPI endpoints, Docker deployment, security |
| `docs/mlops_maintenance.md` | Future extension | Corpus updates, index refresh, monitoring, runbooks |
