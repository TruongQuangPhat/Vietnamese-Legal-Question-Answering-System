pull # VnLaw-QA Codex Skills

These are the primary Codex-discovered repo skills for VnLaw-QA. They are
mirrored from the Claude skill set and adapted only where needed for Codex
wording and frontmatter.

| Skill folder | Skill name | Short trigger / description | Related phase | Mirrored from Claude |
|---|---|---|---|---|
| `vnlaw-project-charter` | `vnlaw-project-charter` | Mission, scope, trusted corpus, roadmap, architecture decisions, phase priorities | Project charter/context | Yes |
| `vnlaw-project-structure` | `vnlaw-project-structure` | Repository layout, module boundaries, project organization | Project structure | Yes |
| `vnlaw-source-corpus` | `vnlaw-source-corpus` | Corpus registry entries, source validation, crawl prioritization, legal source versioning | Source corpus | Yes |
| `vnlaw-data-ingestion` | `vnlaw-data-ingestion` | Registry-driven crawling, raw artifacts, metadata, retries, rate limits | Data ingestion | Yes |
| `vnlaw-cleaning-normalization` | `vnlaw-cleaning-normalization` | Vietnamese legal text cleanup, Unicode normalization, whitespace, HTML cleanup | Cleaning and normalization | Yes |
| `vnlaw-legal-parsing-chunking` | `vnlaw-legal-parsing-chunking` | Legal hierarchy parsing, parent-child chunks, schemas, JSONL output | Legal parsing and chunking | Yes |
| `vnlaw-embedding-indexing` | `vnlaw-embedding-indexing` | Embedding legal chunks, dense/sparse vectors, Qdrant payloads and verification | Embedding/indexing | Yes |
| `vnlaw-retrieval-search-reranking` | `vnlaw-retrieval-search-reranking` | Qdrant search, hybrid retrieval, filters, RRF, reranking, thresholds | Retrieval/search/reranking | Yes |
| `vnlaw-naive-rag` | `vnlaw-naive-rag` | First RAG baseline, simple retrieval, strict citations, fallback, baseline evaluation | Naive RAG | Yes |
| `vnlaw-advanced-rag` | `vnlaw-advanced-rag` | Hybrid retrieval, reranking, query decomposition, context packing, confidence scoring | Advanced RAG | Yes |
| `vnlaw-graphrag-agents` | `vnlaw-graphrag-agents` | Neo4j graph schema, cross-reference traversal, agent orchestration | GraphRAG/agents | Yes |
| `vnlaw-context-engineering` | `vnlaw-context-engineering` | Prompt design, evidence packets, citation anchors, answer format, fallback behavior | Context engineering | Yes |
| `vnlaw-llm-generation` | `vnlaw-llm-generation` | LLM client wrappers, provider abstraction, answer formatting, citation validation | LLM generation | Yes |
| `vnlaw-legal-accuracy` | `vnlaw-legal-accuracy` | Legal answer safety, citations, validity dates, confidence fallback, hallucination prevention | Legal accuracy | Yes |
| `vnlaw-api-backend` | `vnlaw-api-backend` | FastAPI routes, schemas, dependencies, tracing, timeouts, backend tests | API backend | Yes |
| `vnlaw-docstrings-documentation` | `vnlaw-docstrings-documentation` | Google-style docstrings, README/API/architecture/developer documentation | Documentation | Yes |
| `vnlaw-oop-code-quality` | `vnlaw-oop-code-quality` | Python OOP, type hints, dependency injection, service boundaries, errors, logging | Code quality | Yes |
| `vnlaw-evaluation-cicd` | `vnlaw-evaluation-cicd` | RAGAS, golden QA, metrics, CI/CD gates, Docker checks, release readiness | Evaluation/CI/CD | Yes |
| `vnlaw-security-secrets` | `vnlaw-security-secrets` | Secrets, PII-safe logging, API security, DB exposure, Docker security | Security/secrets | Yes |
| `vnlaw-workflow-review` | `vnlaw-workflow-review` | Task planning, review, git diff review, branch discipline, commit readiness | Workflow review | Yes |

Use `SKILL_INDEX.md` for task-to-skill routing.
