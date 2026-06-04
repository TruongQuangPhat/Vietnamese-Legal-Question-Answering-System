---
name: vnlaw-legal-parsing-chunking
description: Use when implementing legal hierarchy parsing, Regex/AST extraction, parent-child chunking, legal metadata schemas, cross-reference extraction, and JSONL chunk output.
---

# Legal Parsing and Parent-Child Chunking Skill

Use this skill for Vietnamese legal hierarchy extraction and chunk creation.

This skill should run after cleaning/normalization and before embedding/indexing.
Current project status: Phase 5 is Legal Hierarchy Parsing. Implement and
validate hierarchy parsing before starting parent-child chunking.

## Goal

Convert normalized legal text into deterministic legal hierarchy first, then
schema-valid legal chunks after the parser gate passes.

```text
data/interim/{LAW_ID}/normalized.json
  → hierarchy recognition
  → AST-like legal structure
  → hierarchy.json validation
  → parent-child chunks
  → cross-reference extraction
  → LegalChunkNode JSONL
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

## Required Data Fields

Every chunk must include:

```text
chunk_id
law_metadata
hierarchy
content
parent_content
cross_references
chunk_metadata
source_info
```

Use Pydantic V2 models at external boundaries.

## Parent-Child Chunking

Rules:

- child chunk = Clause or Point;
- parent context = full Article;
- vector embedding uses child `content`;
- LLM context uses `parent_content` plus metadata;
- chunk IDs must be deterministic when possible.

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

Expected components:

```text
scripts/parse_legal_hierarchy.py
src/services/legal_parsing_service.py
src/processing/legal_parser.py
tests/unit/processing/test_legal_parser.py

future after parser gate:
ParentChildChunker
CrossReferenceExtractor
LegalChunkValidator
```

Rules:

- Keep HTML parsing, legal hierarchy parsing, chunking, and validation separate.
- Use typed models rather than raw dictionaries.
- Public classes/functions must have Google-style docstrings.
- Docstrings must explain hierarchy assumptions and edge cases.

## Verification

- Article count matches source within ±2%.
- Every chunk has law metadata.
- Every chunk has hierarchy metadata.
- Every chunk has source URL and crawl timestamp.
- Parent-child relationship is deterministic.
- Parser tests cover at least three law templates.
- Edge cases include Article, Clause, Point, Roman numerals, and Vietnamese `đ`.

## Do Not

- Do not use arbitrary character splitting.
- Do not collapse Article/Clause/Point hierarchy.
- Do not drop parent Article context.
- Do not fabricate cross-reference targets.
- Do not emit chunks that fail schema validation.
- Do not mix parser logic with embedding or vector store logic.
