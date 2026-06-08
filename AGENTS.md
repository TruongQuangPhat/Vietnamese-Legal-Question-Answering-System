# VnLaw-QA Codex Instructions

## 1. Mission and Legal Accuracy

- VnLaw-QA is a Vietnamese legal QA/RAG project, not a generic chatbot.
- Answer only from the trusted legal corpus.
- Never fabricate laws, articles, clauses, points, penalties, procedures, or citations.
- Preserve citation traceability down to Point / Clause / Article / Law / Year
  or consolidated version.
- Resolve legally effective document versions based on query date when that
  capability is implemented.
- State that the system supports legal research and does not replace
  professional legal counsel when relevant.
- If evidence is insufficient, use a safe fallback instead of guessing.

Required answer citation style:

```text
According to Clause {X}, Article {Y}, {Law Name} {Year or Consolidated Version}: "{quoted legal content}"
```

## 2. Trusted Source Rule

- Default trusted source: `https://thuvienphapluat.vn`.
- Prefer VBHN consolidated documents when available.
- If no VBHN exists, preserve original documents and amendments with accurate
  effective date, expiry date, and status metadata.
- Do not add new data sources unless explicitly requested and documented as an
  approved architectural decision.

## 3. Current Architecture

- `scripts/` = CLI entrypoints, `argparse`, terminal summaries, and exit codes.
- `src/services/` = pipeline orchestration and report building; no `argparse`.
- `src/ingestion/` = reusable ingestion/domain logic such as crawler, audit,
  cleaning, registry, storage, and models.
- `data/raw/` = immutable raw crawl artifacts unless explicitly asked.
- `data/interim/` = derived corpus artifacts.
- `artifacts/reports/<phase>/` = generated reports and diagnostics grouped by
  pipeline phase.
- Preserve Vietnamese legal hierarchy: Phần / Chương / Mục / Điều / Khoản / Điểm.

## 4. Current Phase Status

- Registry-driven crawling is implemented.
- Raw corpus audit is implemented.
- Phase 4 Cleaning & Normalization is complete/gate-ready.
- Cleaned corpus outputs exist for 52/52 legal documents under `data/interim/`.
- Encoded TVPL footer/watermark artifacts are removed from cleaned outputs.
- Article metrics distinguish article references from real article headings.
- Phase 5 Legal Hierarchy Parsing is complete and hardened with 52/52
  generated `hierarchy.json` outputs, 0 failed documents, 0 validator
  failures, 0 RED/ORANGE audit cases, and 0 source-tail leakage nodes.
- Phase 6 Parent-child Chunking is complete and validated.
- Chunk output exists at `data/processed/legal_chunks.jsonl`.
- Chunking report exists at `artifacts/reports/chunking/chunking_report.json`.
- Phase 6 full-corpus result after hardening: 34 successes, 18 successes with
  warnings, 0 failures, 40,389 chunks, 0 duplicate chunk IDs, 0 bad JSONL
  lines, 0 source-tail markers in `text`, 0 source-tail markers in
  `parent_text`, and 180 empty/repealed chunks flagged.
- Embedding/RAG/Advanced RAG/GraphRAG has not started.
- The next phase is Phase 7 Processed JSONL Validation / embedding-readiness
  checks over `data/processed/legal_chunks.jsonl`.
- Do not jump ahead to embedding, RAG, Advanced RAG, or GraphRAG before the
  processed JSONL validation gate passes.

## 5. Official Commands

Use `uv run` for Python commands.

```bash
uv run python scripts/crawl_raw_corpus.py --help
uv run python scripts/audit_raw_corpus.py --help
uv run python scripts/clean_raw_corpus.py --help
uv run python scripts/audit_cleaning_quality.py --help
uv run python scripts/parse_legal_hierarchy.py --help
uv run python scripts/chunk_legal_corpus.py --help
uv run pytest tests/unit/ingestion -q
```

Run only `--help` for crawl/clean commands unless explicitly asked to execute
the pipeline.

## 6. Python/OOP Standards

- Use Python 3.11+.
- Add `from __future__ import annotations` to new Python files unless there is a
  clear reason not to.
- Use complete type hints for public functions, public methods, class
  attributes, and data boundaries.
- Use Pydantic V2 for configs/schema boundaries where appropriate.
- Use `async def` / `await` for I/O involving crawling, vector stores, graph
  stores, Redis, LLM calls, HTTP clients, and API operations.
- Do not pass untyped raw dictionaries across module boundaries; prefer
  Pydantic models, dataclasses, or typed protocols.
- Keep clear service/domain boundaries.
- Prefer dependency injection; do not instantiate infrastructure clients deep
  inside business logic.
- Keep classes small and single-purpose.
- Avoid god classes that mix ingestion, retrieval, generation, evaluation, API,
  and deployment.
- Use custom exceptions and structured logging.

## 7. Documentation and Docstrings

- Use Google-style docstrings for public classes, public functions, public
  methods, Pydantic models, API endpoints, non-trivial algorithms, and legal/RAG
  pipeline components.
- Explain purpose, arguments, return values, raised exceptions, side effects,
  legal assumptions, and retrieval assumptions.
- Avoid vague docstrings such as `Process data` or `Handle query`.

## 8. Security and Logging

- Never hardcode API keys, passwords, tokens, connection strings, or credentials.
- Do not copy `.env`, secrets, tokens, credentials, or local-only settings into
  Codex instruction mirrors.
- Read secrets from `.env` through `pydantic-settings`.
- Do not log raw user legal questions in production; they may contain PII.
- Sanitize external query inputs, including Cypher inputs.
- Use structured logs with request/user identifiers when available.
- Never use `except Exception: pass` in production code.
- Do not expose Neo4j, Redis, or Qdrant insecurely in production.

## 9. Data and Chunking Rules

- Preserve legal hierarchy: Part -> Chapter -> Section -> Article -> Clause -> Point.
- Parent-child chunking uses:
  - child unit = Clause or Point
  - parent unit = Article
  - embedding content = child content
  - LLM context = parent article content
- Phase 6 output is a single corpus-level JSONL file:
  `data/processed/legal_chunks.jsonl`.
- Phase 8 embedding/indexing should embed `text` only; keep `parent_text` as
  Article context payload for retrieval/generation.
- Phase 6 hardening treats VBHN/source-law certification tail as excluded
  hierarchy content and flags `(được bãi bỏ)` source units in metadata.
- Never split legal text by arbitrary character or token windows if doing so
  breaks clauses, points, or legal meaning.
- Do not mutate `data/raw/`; write derived artifacts to separate directories.

## 10. Required Workflow

Before editing:

1. Read `AGENTS.md`.
2. Read `.codex/context/INSTRUCTION_INDEX.md` if relevant.
3. Read `PROJECT_CONTEXT.md`.
4. Read the relevant `.agents` skill.
5. Inspect relevant files.
6. State a short plan.
7. Identify tests/checks to run.

After editing:

1. Summarize changes.
2. List changed files.
3. Explain important design choices.
4. Report tests/checks run.
5. Report remaining risks.

## 11. Skill and Context Locations

- Active Codex repo skills: `.agents/skills/<skill-name>/SKILL.md`.
- Codex context/reference: `.codex/context/`.
- Inactive skill mirror/reference: `.codex/context/skills_mirror/*/SKILL.mirror.md`
  if present.
- Claude original skills: `.claude/skills/`.
- Do not delete, rename, move, overwrite, or modify Claude files unless
  explicitly asked.
- `.codex/skills` should not be used as an active skill folder in this repo.

## 12. Do-Not-List / Do-Not-Touch Rules

- Do not list `.git`, `.venv`, `.mypy_cache`, `.ruff_cache`, `.pytest_cache`,
  `__pycache__`, or huge generated folders.
- Do not mutate `data/raw/`.
- Do not modify `data/interim/` or generated `artifacts/` outputs unless explicitly asked.
- Do not modify `data/processed/legal_chunks.jsonl` unless explicitly rerunning
  the Phase 6 chunking command.
- `data/reports/` is a historical/protected path only; active reports belong under
  `artifacts/reports/{phase}/`.
- Do not run full crawl, audit, or cleaning commands unless explicitly requested.
- Do not proceed to embedding/RAG before the processed JSONL validation gate is solid.
- Do not delete `.claude/`, `.claude/skills/`, Claude settings files,
  `CLAUDE.md`, or `PROJECT_CONTEXT.md`.
