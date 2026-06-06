# VnLaw-QA — Claude Code Project Instructions

This repository implements **VnLaw-QA**, a Vietnamese legal question-answering system that evolves from **Naive RAG → Advanced RAG → GraphRAG**. Claude must follow these instructions for every coding, design, review, documentation, and evaluation task in this repository.

## 1. Mission and Non-Negotiable Legal Accuracy

VnLaw-QA answers Vietnamese legal questions with strict legal grounding. It must:

- Answer only from the trusted corpus.
- Cite legal sources at the level of **Point → Clause → Article → Law → Year / consolidated version**.
- Resolve the legally effective version of a document based on the query date.
- Clearly state that the system supports legal research and **does not replace professional legal counsel**.
- Never fabricate laws, articles, clauses, points, penalties, procedures, or citations.

Required citation style in generated answers:

```text
According to Clause {X}, Article {Y}, {Law Name} {Year or Consolidated Version}: "{quoted legal content}"
```

If confidence is below the configured threshold, default `0.75`, the system must fall back:

```text
I could not find a specific regulation for this issue in the current legal corpus. Please check thuvienphapluat.vn directly or consult a qualified lawyer.
```

## 2. Trusted Data Source Rule

The only default trusted source is:

```text
https://thuvienphapluat.vn
```

Do not add another data source unless the task explicitly asks for it and the change is documented as an approved architectural decision.

Prefer **VBHN** consolidated documents when available. If no VBHN exists, crawl and represent the original document and amendments in chronological order with accurate `effective_date`, `expiry_date`, and status metadata.

## 3. Architecture Roadmap

The project roadmap is:

1. **Semantic Ingestion and Metadata**
   - crawl legal pages,
   - clean and normalize Vietnamese legal text,
   - parse hierarchy,
   - create parent-child chunks,
   - embed with dense and sparse representations,
   - store in Qdrant and Neo4j with strict metadata.

2. **Naive RAG Baseline**
   - single retriever baseline,
   - simple prompt,
   - strict citations,
   - fallback behavior,
   - golden QA baseline.

3. **Advanced RAG**
   - hybrid dense + sparse retrieval,
   - Reciprocal Rank Fusion,
   - cross-encoder reranking,
   - time-aware law filtering,
   - query rewriting / decomposition where needed,
   - context packing with citation anchors.

4. **GraphRAG and Multi-Agent Retrieval**
   - Neo4j legal graph,
   - cross-reference traversal,
   - vector explorer,
   - graph explorer,
   - web/latest-law checker only when explicitly approved,
   - orchestrator that merges evidence without hallucination.

5. **Fine-Tuning and MLOps**
   - legal QA synthetic data,
   - QLoRA / local model serving where appropriate,
   - RAGAS evaluation gates,
   - CI/CD, Docker, monitoring, safety, and release workflows.

Current project state:

```text
Phases 0-5 are complete.
Phase 5 Legal Hierarchy Parsing is complete and hardened:
  52 hierarchy.json outputs
  0 parser failures
  0 validator failures
  0 RED/ORANGE audit cases
  0 source-tail leakage nodes

Next phase:
  Phase 6 — Parent-child Chunking over data/interim/{LAW_ID}/hierarchy.json
```

Do not redo crawling, cleaning, or hierarchy parsing unless a proven blocker
exists. Do not jump to embedding, indexing, retrieval, RAG, Advanced RAG,
GraphRAG, API, or deployment before Phase 6 chunk quality is validated.

## 4. Expected Repository Layout

Use this as the canonical structure unless a task explicitly changes it:

```text
VnLaw-QA/
├── configs/
│   ├── laws/
│   ├── sources/
│   ├── ingestion/
│   ├── processing/
│   ├── indexing/
│   ├── retrieval/
│   ├── generation/
│   └── evaluation/
├── data/
│   ├── raw/          # immutable raw legal evidence
│   ├── interim/      # normalized and parsed intermediate artifacts
│   ├── processed/    # future chunked/index-ready corpus artifacts
│   ├── indexes/
│   └── eval/
├── artifacts/
│   ├── reports/
│   │   ├── crawling/
│   │   ├── audit/
│   │   ├── cleaning/
│   │   ├── parsing/
│   │   ├── chunking/
│   │   ├── indexing/
│   │   ├── retrieval/
│   │   ├── generation/
│   │   └── evaluation/
│   ├── traces/
│   │   ├── crawling/
│   │   ├── audit/
│   │   ├── cleaning/
│   │   ├── parsing/
│   │   ├── retrieval/
│   │   └── generation/
│   ├── runs/
│   │   ├── experiments/
│   │   ├── benchmarks/
│   │   └── evaluations/
│   ├── metrics/
│   │   ├── indexing/
│   │   ├── retrieval/
│   │   ├── generation/
│   │   └── evaluation/
│   └── logs/
├── src/
│   ├── core/
│   ├── ingestion/
│   ├── processing/
│   ├── indexing/
│   ├── retrieval/
│   ├── generation/
│   ├── services/
│   ├── api/
│   ├── evaluation/
│   ├── monitoring/
│   └── security/
├── scripts/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── regression/
│   └── fixtures/
├── docs/
├── docker/
├── deployment/
├── monitoring/
└── .github/workflows/
```

## 5. Python, OOP, and Architecture Standards

All production Python code must follow these standards:

- Use Python 3.11+.
- Put `from __future__ import annotations` at the top of new Python files unless there is a clear reason not to.
- Use complete type hints for public functions, public methods, class attributes, and data boundaries.
- Use Pydantic V2 for config, request models, response models, and legal chunk schemas.
- Use `async def` / `await` for I/O involving crawling, Qdrant, Neo4j, Redis, LLM calls, and API operations.
- Do not pass untyped raw dictionaries across module boundaries. Prefer Pydantic models, dataclasses for internal immutable records, or typed protocols.
- Use clear OOP boundaries:
  - `BaseCrawler` / crawler implementations,
  - `BaseLegalParser` / parser implementations,
  - `BaseChunker` / chunker implementations,
  - `BaseEmbedder` / embedding implementations,
  - `BaseVectorStore` / Qdrant implementation,
  - `BaseGraphStore` / Neo4j implementation,
  - `BaseReranker` / reranker implementation,
  - `BaseLLMClient` / LLM provider implementation,
  - `BaseAgent` / retrieval or reasoning agents.
- Prefer dependency injection. Do not instantiate infrastructure clients deep inside business logic.
- Keep classes small and single-purpose. Avoid god classes such as `RAGSystem`, `PipelineManager`, or `AgentManager` that mix ingestion, retrieval, generation, evaluation, API, and deployment.
- Keep FastAPI route handlers thin. Business logic belongs in service classes or use-case functions.
- Use custom exceptions and structured logging.

## 6. Docstring and Documentation Standards

Every public class, public function, public method, Pydantic model, API endpoint, non-trivial algorithm, and legal/RAG pipeline component must have a clear **Google-style docstring**.

Docstrings must explain:

- purpose,
- arguments,
- return value,
- raised exceptions,
- side effects,
- legal assumptions,
- retrieval assumptions,
- examples when helpful.

Do not write vague docstrings like `Process data` or `Handle query`. Explain the domain meaning and the invariant being preserved.

## 7. Error Handling, Logging, and Security

- Never use `except Exception: pass` in production code.
- Catch specific exceptions, log with `structlog`, and raise a custom exception with context.
- Never hardcode API keys, passwords, tokens, or connection strings.
- Read secrets from `.env` through `pydantic-settings`.
- Do not log raw user legal questions in production because they may contain PII.
- Sanitize all Cypher query inputs to avoid Neo4j injection.
- Never expose Neo4j, Redis, or Qdrant insecurely in production.
- Use `request_id`, `user_id` when available, timestamps, and structured JSON logs.

## 8. Data and Chunking Rules

Legal chunks must preserve Vietnamese legal hierarchy:

```text
Part → Chapter → Section → Article → Clause → Point
```

Use parent-child chunking:

- child unit: Clause or Point,
- parent unit: Article,
- embedding content: child content,
- LLM context: parent article content.

Never split legal documents by arbitrary character count or token windows if that breaks legal clauses or points.

## 9. Required Development Workflow

Before editing code:

1. Read the relevant skill.
2. Inspect relevant files.
3. Restate the task.
4. Propose a short plan.
5. Identify files likely to change.
6. Identify tests or checks to run.

After editing:

1. Summarize the changes.
2. List changed files.
3. Explain important design choices.
4. Report tests/checks run.
5. Report remaining risks.

Preferred checks before commit:

```bash
uv run ruff check src tests
uv run ruff format src tests
uv run mypy src
uv run pytest tests/unit -v
```

Run narrower tests first for small tasks; run broader tests before PR/merge.

## 10. Skill Usage

Use the project skills in `.claude/skills/` whenever relevant. They are the source of truth for task-specific behavior.

Common invocations:

```text
/vnlaw-project-charter
/vnlaw-legal-accuracy
/vnlaw-oop-code-quality
/vnlaw-docstrings-documentation
/vnlaw-data-ingestion
/vnlaw-legal-parsing-chunking
/vnlaw-naive-rag
/vnlaw-advanced-rag
/vnlaw-graphrag-agents
/vnlaw-evaluation-cicd
/vnlaw-workflow-review
```

## Project Context and Documentation

Before making changes, read `PROJECT_CONTEXT.md` and the relevant documentation under `docs/`.

`PROJECT_CONTEXT.md` is the source of truth for the current project status, completed phases, current phase, next immediate tasks, and out-of-scope work.

The `docs/` directory contains phase-specific technical documentation and should be consulted before modifying related modules.
