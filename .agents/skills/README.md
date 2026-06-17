# VnLaw-QA Repository Skills

These are repository-scoped active skills for coding assistants working on
VnLaw-QA.

| Skill folder | Skill name | Short trigger / description | Related phase |
|---|---|---|---|
| `vnlaw-project-charter` | `vnlaw-project-charter` | Mission, scope, trusted corpus, roadmap, architecture decisions, phase priorities | Project charter/context |
| `vnlaw-project-structure` | `vnlaw-project-structure` | Repository layout, module boundaries, project organization | Project structure |
| `vnlaw-source-corpus` | `vnlaw-source-corpus` | Corpus registry entries, source validation, crawl prioritization, legal source versioning | Source corpus |
| `vnlaw-data-ingestion` | `vnlaw-data-ingestion` | Registry-driven crawling, raw artifacts, metadata, retries, rate limits | Data ingestion |
| `vnlaw-cleaning-normalization` | `vnlaw-cleaning-normalization` | Vietnamese legal text cleanup, Unicode normalization, whitespace, HTML cleanup | Cleaning and normalization |
| `vnlaw-legal-parsing-chunking` | `vnlaw-legal-parsing-chunking` | Legal hierarchy parsing, parent-child chunks, schemas, JSONL output | Legal parsing and chunking |
| `vnlaw-embedding-indexing` | `vnlaw-embedding-indexing` | Embedding legal chunks, dense/sparse vectors, Qdrant payloads and verification | Embedding/indexing |
| `vnlaw-retrieval-search-reranking` | `vnlaw-retrieval-search-reranking` | Qdrant search, hybrid retrieval, filters, RRF, reranking, thresholds | Retrieval/search/reranking |
| `vnlaw-naive-rag` | `vnlaw-naive-rag` | First RAG baseline, simple retrieval, strict citations, fallback, baseline evaluation | Naive RAG |
| `vnlaw-advanced-rag` | `vnlaw-advanced-rag` | Hybrid retrieval, reranking, query decomposition, context packing, confidence scoring | Advanced RAG |
| `vnlaw-graphrag-agents` | `vnlaw-graphrag-agents` | Neo4j graph schema, cross-reference traversal, agent orchestration | GraphRAG/agents |
| `vnlaw-context-engineering` | `vnlaw-context-engineering` | Prompt design, evidence packets, citation anchors, answer format, fallback behavior | Context engineering |
| `vnlaw-llm-generation` | `vnlaw-llm-generation` | LLM client wrappers, provider abstraction, answer formatting, citation validation | LLM generation |
| `vnlaw-legal-accuracy` | `vnlaw-legal-accuracy` | Legal answer safety, citations, validity dates, confidence fallback, hallucination prevention | Legal accuracy |
| `vnlaw-api-backend` | `vnlaw-api-backend` | FastAPI routes, schemas, dependencies, tracing, timeouts, backend tests | API backend |
| `vnlaw-docstrings-documentation` | `vnlaw-docstrings-documentation` | Google-style docstrings, README/API/architecture/developer documentation | Documentation |
| `vnlaw-oop-code-quality` | `vnlaw-oop-code-quality` | Python OOP, type hints, dependency injection, service boundaries, errors, logging | Code quality |
| `vnlaw-evaluation-cicd` | `vnlaw-evaluation-cicd` | RAGAS, golden QA, metrics, CI/CD gates, Docker checks, release readiness | Evaluation/CI/CD |
| `vnlaw-security-secrets` | `vnlaw-security-secrets` | Secrets, PII-safe logging, API security, DB exposure, Docker security | Security/secrets |
| `vnlaw-workflow-review` | `vnlaw-workflow-review` | Task planning, review, git diff review, branch discipline, commit readiness | Workflow review |

Use `SKILL_INDEX.md` for task-to-skill routing.
