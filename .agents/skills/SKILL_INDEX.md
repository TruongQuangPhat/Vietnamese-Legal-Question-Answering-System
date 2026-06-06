# VnLaw-QA Codex Skill Index

Use this index before modifying domain-specific code or documentation. The
skills in `.agents/skills/` are the primary Codex-discovered repo skills.

| Task type | Read these skills |
|---|---|
| Mission, roadmap, current priorities | `vnlaw-project-charter` |
| Repository layout or module ownership | `vnlaw-project-structure`, `vnlaw-oop-code-quality` |
| Corpus registry or legal source changes | `vnlaw-source-corpus`, `vnlaw-data-ingestion` |
| Crawling or raw artifact handling | `vnlaw-data-ingestion`, `vnlaw-source-corpus`, `vnlaw-security-secrets` |
| Cleaning HTML or normalizing Vietnamese legal text | `vnlaw-cleaning-normalization`, `vnlaw-legal-accuracy` |
| Cleaning quality audit/improvement | `vnlaw-cleaning-normalization`, `vnlaw-evaluation-cicd`, `vnlaw-legal-accuracy` |
| Legal hierarchy parsing or chunk creation | `vnlaw-legal-parsing-chunking`, `vnlaw-legal-accuracy` |
| Embedding chunks or configuring Qdrant | `vnlaw-embedding-indexing`, `vnlaw-retrieval-search-reranking` |
| Search, filters, fusion, or reranking | `vnlaw-retrieval-search-reranking`, `vnlaw-legal-accuracy` |
| First QA baseline | `vnlaw-naive-rag`, `vnlaw-context-engineering`, `vnlaw-llm-generation`, `vnlaw-legal-accuracy` |
| Advanced RAG | `vnlaw-advanced-rag`, `vnlaw-retrieval-search-reranking`, `vnlaw-context-engineering`, `vnlaw-legal-accuracy` |
| Graph traversal or multi-agent retrieval | `vnlaw-graphrag-agents`, `vnlaw-legal-accuracy` |
| Prompting, evidence packets, answer format | `vnlaw-context-engineering`, `vnlaw-llm-generation`, `vnlaw-legal-accuracy` |
| Public legal answer behavior | `vnlaw-legal-accuracy`, `vnlaw-llm-generation`, `vnlaw-context-engineering` |
| FastAPI/backend service work | `vnlaw-api-backend`, `vnlaw-oop-code-quality`, `vnlaw-security-secrets` |
| Tests, metrics, release gates, CI | `vnlaw-evaluation-cicd`, `vnlaw-workflow-review` |
| Secrets, PII, logs, DB exposure, Docker security | `vnlaw-security-secrets` |
| Documentation or docstrings | `vnlaw-docstrings-documentation`, `vnlaw-oop-code-quality` |

## Phase Discipline

Current status is defined in `.codex/context/PROJECT_CONTEXT.md`. Crawling,
raw corpus audit, Phase 4 Cleaning & Normalization, and Phase 5 Legal
Hierarchy Parsing are implemented and validated. Phase 6 Parent-child Chunking
is next and not yet implemented. Embedding, indexing, RAG, Advanced RAG, and
GraphRAG must wait until chunking output quality is validated.

Do not implement future phases early. If a task crosses phase boundaries, read
`vnlaw-workflow-review` and surface the boundary before changing code.
