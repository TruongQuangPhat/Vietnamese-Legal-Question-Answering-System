# VnLaw-QA Repository Skills

These are repository-scoped active skills for coding assistants working on VnLaw-QA.

Use `SKILL_INDEX.md` for task-to-skill routing. This README is a compact overview of available skills and their intended scope.

| Skill folder                       | Skill name                         | Short trigger / description                                                                                                             | Scope / status                                 |
| ---------------------------------- | ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------- |
| `vnlaw-project-charter`            | `vnlaw-project-charter`            | Mission, scope, trusted corpus, current architecture, implementation priorities, and safety boundaries                                  | Current project orientation                    |
| `vnlaw-project-structure`          | `vnlaw-project-structure`          | Repository layout, module boundaries, protected paths, and project organization                                                         | Current structure + future-scoped areas        |
| `vnlaw-source-corpus`              | `vnlaw-source-corpus`              | Corpus registry entries, trusted source validation, crawl prioritization, and legal source versioning                                   | Current corpus maintenance                     |
| `vnlaw-data-ingestion`             | `vnlaw-data-ingestion`             | Registry-driven crawling, raw artifacts, metadata, retries, rate limits, and raw corpus audit                                           | Implemented; maintenance/debugging             |
| `vnlaw-cleaning-normalization`     | `vnlaw-cleaning-normalization`     | Vietnamese legal text cleanup, Unicode normalization, whitespace normalization, and HTML cleanup                                        | Implemented; maintenance/regression            |
| `vnlaw-legal-parsing-chunking`     | `vnlaw-legal-parsing-chunking`     | Legal hierarchy parsing, parent-child chunks, schemas, cross-references, and processed JSONL output                                     | Implemented; protected outputs                 |
| `vnlaw-embedding-indexing`         | `vnlaw-embedding-indexing`         | BGE-M3 dense embedding, Qdrant dense indexing, payload design, and indexing verification                                                | Implemented; real indexing only when scoped    |
| `vnlaw-retrieval-search-reranking` | `vnlaw-retrieval-search-reranking` | Qdrant dense retrieval, local BM25 sparse retrieval, RRF, coverage-aware quota, controlled reranking ablations, and retrieval metrics   | Implemented retrieval; reranking not adopted   |
| `vnlaw-naive-rag`                  | `vnlaw-naive-rag`                  | Naive RAG baseline, simple retrieval, strict citations, fallback, and baseline evaluation                                               | Implemented baseline                           |
| `vnlaw-advanced-rag`               | `vnlaw-advanced-rag`               | Coverage-aware hybrid retrieval, evidence selection, strict citation validation, answerability fallback guard, and controlled ablations | Implemented/evaluated final RAG workflow       |
| `vnlaw-graphrag-agents`            | `vnlaw-graphrag-agents`            | Neo4j graph schema, cross-reference traversal, routing, and agent orchestration                                                         | Future/separately scoped                       |
| `vnlaw-context-engineering`        | `vnlaw-context-engineering`        | Prompt design, evidence packets, citation anchors, answer format, and fallback behavior                                                 | Implemented; maintain prompt/evidence behavior |
| `vnlaw-llm-generation`             | `vnlaw-llm-generation`             | LLM client wrappers, provider abstraction, answer formatting, citation ID validation, and hallucination prevention                      | Implemented; real LLM calls only when scoped   |
| `vnlaw-legal-accuracy`             | `vnlaw-legal-accuracy`             | Legal answer safety, citations, hierarchy, evidence sufficiency, fallback, and hallucination prevention                                 | Highest-priority safety skill                  |
| `vnlaw-api-backend`                | `vnlaw-api-backend`                | FastAPI routes, schemas, dependencies, tracing, timeouts, and backend tests                                                             | Future/separately scoped                       |
| `vnlaw-docstrings-documentation`   | `vnlaw-docstrings-documentation`   | Google-style docstrings, README, architecture docs, developer docs, and project context                                                 | Current documentation guidance                 |
| `vnlaw-oop-code-quality`           | `vnlaw-oop-code-quality`           | Python OOP, type hints, dependency injection, service boundaries, errors, logging, and maintainability                                  | General code quality                           |
| `vnlaw-evaluation-cicd`            | `vnlaw-evaluation-cicd`            | Benchmark metrics, retrieval/generation evaluation, citation/fallback checks, CI gates, and artifact contracts                          | Implemented evaluation; CI/CD guidance         |
| `vnlaw-security-secrets`           | `vnlaw-security-secrets`           | Secrets, PII-safe logging, API security, DB exposure, protected paths, and safe agent operations                                        | Security/safety guidance                       |
| `vnlaw-workflow-review`            | `vnlaw-workflow-review`            | Task planning, review, git diff review, branch discipline, protected path checks, and commit readiness                                  | Daily workflow/review                          |

Core current-state reminders:

* Current corpus: 52 Vietnamese legal documents and 40,389 processed chunks.
* Current dense index: BGE-M3, Qdrant collection `vnlaw_chunks_bgem3_v1_full`, vector name `dense`, dimension 1024.
* Current adopted retrieval: local BM25 sparse retrieval + Qdrant dense retrieval + RRF + `coverage_aware_quota`.
* Reranking was evaluated but not adopted.
* Current strict generation workflow uses citation ID guard and answerability fallback guard.
* GraphRAG, API/backend, time-aware filtering, production deployment, and fine-tuning are future or separately scoped.
* Do not mutate protected corpus, benchmark, or official evaluation artifacts unless explicitly scoped.
