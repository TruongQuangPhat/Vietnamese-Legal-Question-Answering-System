---
name: vnlaw-legal-parsing-chunking
description: Use when implementing legal hierarchy parsing, Regex/AST extraction, parent-child chunking, legal metadata schemas, cross-reference extraction, and JSONL chunk output.
---

# Legal Parsing and Parent-Child Chunking Skill

Use this skill for Vietnamese legal hierarchy extraction and parent-child chunk creation.

This skill should run after cleaning/normalization and before embedding/indexing.
Current project status: Phase 5 Legal Hierarchy Parsing is complete and
hardened. Phase 6 Parent-child Chunking is complete and validated with
`data/processed/legal_chunks.jsonl`, 34 successes, 18 successes with warnings,
0 failed laws, 40,389 chunks, 0 source-tail markers in `text`/`parent_text`,
and 180 empty/repealed chunks flagged. Phase 7 validation and Phase 7.5
semantic audit are complete with 0 hard errors and a **Go with watch items**
decision. Do not modify hierarchy/chunks or start Phase 8 work unless a
separate task is explicitly scoped. Before indexing, rerun Phase 7 and
preserve short chunks, authority phrases, parent context, citations, hashes,
source metadata, and repeal flags.

## Goal

Use the completed deterministic legal hierarchy to create and validate
schema-valid legal chunks after the parser gate has passed.

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

## Implemented Phase 6 Output

```text
data/processed/legal_chunks.jsonl
artifacts/reports/chunking/chunking_report.json
artifacts/reports/chunking/full_corpus_validation_report.json
```

Validated result:

```text
34 laws successful
18 laws successful with warnings
0 failed laws
40,389 chunks
1,322 article chunks
20,643 clause chunks
18,424 point chunks
180 empty/repealed chunks flagged
0 source-tail markers in text
0 source-tail markers in parent_text
0 duplicate chunk IDs
0 bad JSONL lines
0 selection-rule issues
0 chunk invariant issues
```

Official command:

```bash
uv run python scripts/corpus/chunk_legal_corpus.py \
  --input-dir data/interim \
  --output data/processed/legal_chunks.jsonl \
  --report artifacts/reports/chunking/chunking_report.json \
  --overwrite \
  --verbose \
  --no-color
```

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

- child chunk = Article, Clause, or Point according to legal hierarchy;
- parent context = full Article;
- vector embedding should use `text`;
- LLM context should use `parent_text` plus metadata;
- chunk IDs must be deterministic and use Phase 5 `node_id`.

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
scripts/corpus/parse_legal_hierarchy.py
src/services/legal_parsing_service.py
src/processing/legal_parser.py
tests/unit/processing/test_legal_parser.py

Phase 6 implemented:
LegalChunk
LegalChunker
LegalChunkValidator
ChunkingService
scripts/corpus/chunk_legal_corpus.py
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
- JSONL rerun is deterministic for `data/processed/legal_chunks.jsonl`.
- Parser tests cover at least three law templates.
- Edge cases include Article, Clause, Point, Roman numerals, and Vietnamese `đ`.

## Do Not

- Do not use arbitrary character splitting.
- Do not collapse Article/Clause/Point hierarchy.
- Do not drop parent Article context.
- Do not fabricate cross-reference targets.
- Do not emit chunks that fail schema validation.
- Do not mix parser logic with embedding or vector store logic.
