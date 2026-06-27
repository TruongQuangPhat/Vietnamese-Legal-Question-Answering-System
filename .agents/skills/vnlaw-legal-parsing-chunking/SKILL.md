---
name: vnlaw-legal-parsing-chunking
description: Use when maintaining or debugging Vietnamese legal hierarchy parsing, regex/AST extraction, parent-child chunking, legal metadata schemas, cross-reference extraction, and processed JSONL chunk output.
---

# Legal Parsing and Parent-Child Chunking Skill

Use this skill for Vietnamese legal hierarchy extraction, parent-child chunk creation, and processed JSONL validation.

This skill runs after cleaning/normalization and before embedding/indexing.

## Current Status

Legal hierarchy parsing, parent-child chunking, processed JSONL validation, and semantic audit are implemented and validated for the current corpus.

Current processed chunk state:

```text
processed JSONL = data/processed/legal_chunks.jsonl
valid chunks = 40,389
failed laws = 0
duplicate chunk IDs = 0
bad JSONL lines = 0
hard validation errors = 0
```

Chunking results include:

```text
34 laws successful
18 laws successful with warnings
1,322 article chunks
20,643 clause chunks
18,424 point chunks
180 empty/repealed chunks flagged
0 source-tail markers in text
0 source-tail markers in parent_text
0 selection-rule issues
0 chunk invariant issues
```

Use this skill for maintenance, debugging, regression fixes, or schema review. Do not modify hierarchy output, regenerate chunks, or overwrite `data/processed/legal_chunks.jsonl` unless the user explicitly scopes that operation.

Protected paths include:

```text
data/raw/**
data/interim/**
data/reports/**
data/processed/legal_chunks.jsonl
```

Workflow-level integration tests for corpus processing now exist under:

```text
tests/integration/corpus/
```

## Goal

Use the deterministic legal hierarchy to create and validate schema-valid legal chunks.

```text
data/interim/{LAW_ID}/hierarchy.json
  → load validated hierarchy
  → parent-child chunks
  → LegalChunk JSONL
  → validation
```

## Legal Hierarchy

Always preserve:

```text
Part → Chapter → Section → Article → Clause → Point
```

Vietnamese labels:

```text
Phần → Chương → Mục → Điều → Khoản → Điểm
```

Do not flatten hierarchy into plain text chunks.

## Parser Strategy

Use regex as a first-pass recognizer, then build a structured AST-like hierarchy.

Representative patterns:

```python
PATTERNS = {
    "phan": re.compile(r"^PHẦN\s+(THỨ\s+)?([IVXLC]+|\d+|[A-Z]+)\s*[:\.]?\s*(.+)?$", re.MULTILINE),
    "chuong": re.compile(r"^CHƯƠNG\s+(THỨ\s+)?([IVXLC]+|\d+)\s*[:\.]?\s*(.+)?$", re.MULTILINE),
    "muc": re.compile(r"^MỤC\s+(\d+|[A-Z]+)\s*[:\.]?\s*(.+)?$", re.MULTILINE),
    "dieu": re.compile(r"^Điều\s+(\d+[a-z]?)\.\s*(.+)?$", re.MULTILINE),
    "khoan": re.compile(r"^(\d+)\.\s+(.+)", re.MULTILINE),
    "diem": re.compile(r"^([a-zđ])\)\s+(.+)", re.MULTILINE),
}
```

Regex patterns are not enough by themselves. The final output must be a validated hierarchy.

## Implemented Output

```text
data/processed/legal_chunks.jsonl
artifacts/reports/chunking/chunking_report.json
artifacts/reports/chunking/full_corpus_validation_report.json
```

Chunk generation command:

```bash
uv run python scripts/corpus/chunk_legal_corpus.py \
  --input-dir data/interim \
  --output data/processed/legal_chunks.jsonl \
  --report artifacts/reports/chunking/chunking_report.json \
  --overwrite \
  --verbose \
  --no-color
```

This command writes protected processed data. Run it only when the user explicitly scopes a real chunk regeneration task.

## Required Data Fields

Every chunk must include:

```text
chunk_id
law_id
law_name
citation
hierarchy_path
text
parent_text
source_node_id
parent_article_node_id
offsets
hashes
metadata
```

Use Pydantic V2 models at external boundaries.

## Parent-Child Chunking

Rules:

* child chunk = Article, Clause, or Point according to legal hierarchy;
* parent context = full Article;
* vector embedding should use citable child `text`;
* LLM context may use `parent_text` as auxiliary context;
* parent context is not directly citable;
* chunk IDs must be deterministic and based on stable parser/source node metadata.

Never split legal text by arbitrary character windows.

## Cross-References

Extract references such as:

```text
theo Điều 79 của Luật này
Điều 145 của Bộ luật Tố tụng hình sự
Khoản 2 Điều này
```

Represent references with:

```text
ref_id
ref_type
ref_relation
anchor_text
context_snippet
ref_metadata
resolution_status
```

If a reference cannot be resolved safely, mark it unresolved instead of guessing.

## OOP and Docstring Rules

Relevant components may include:

```text
scripts/corpus/parse_legal_hierarchy.py
src/services/legal_parsing_service.py
src/processing/legal_parser.py
tests/unit/processing/test_legal_parser.py

LegalChunk
LegalChunker
LegalChunkValidator
ChunkingService
scripts/corpus/chunk_legal_corpus.py
tests/unit/services/test_legal_parsing_service.py
tests/unit/services/test_chunking_service.py
tests/integration/corpus/test_legal_parsing_chunking_workflow.py
```

Rules:

* Keep HTML parsing, legal hierarchy parsing, chunking, and validation separate.
* Use typed models rather than raw dictionaries.
* Public classes/functions must have Google-style docstrings where project style requires it.
* Docstrings must explain hierarchy assumptions and edge cases.

## Verification

When changing parser or chunker behavior, verify:

* Article count matches source within acceptable tolerance.
* Every chunk has law metadata.
* Every chunk has hierarchy metadata.
* Every citable chunk has citation/source metadata.
* Parent-child relationship is deterministic.
* JSONL output is deterministic.
* Parser tests cover multiple law templates.
* Edge cases include Article, Clause, Point, Roman numerals, and Vietnamese `đ`.
* Short chunks, authority phrases, citations, hashes, source metadata, and repeal/status flags are preserved.

Prefer unit tests and tiny integration fixtures. Do not use or overwrite the real processed JSONL unless explicitly scoped.

## Do Not

* Do not use arbitrary character splitting.
* Do not collapse Article/Clause/Point hierarchy.
* Do not drop parent Article context.
* Do not make parent context directly citable.
* Do not fabricate cross-reference targets.
* Do not emit chunks that fail schema validation.
* Do not mix parser logic with embedding or vector store logic.
* Do not regenerate or overwrite protected chunk outputs unless explicitly scoped.
