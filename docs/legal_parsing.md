# Legal Hierarchy Parsing System

## Overview

The Legal Hierarchy Parsing phase analyzes cleaned Vietnamese legal text and extracts the structured hierarchy: Phần → Chương → Mục → Điều → Khoản → Điểm. The output is a tree of legal nodes, each representing a distinct legal unit with its text, numbering, and positional offsets.

Parsing is the foundation for parent-child chunking. Accurate hierarchy extraction ensures citations remain traceable and legal structure is preserved throughout the RAG pipeline.

## Quick Start

**Intended CLI** (design phase, not yet implemented):

```bash
uv run python scripts/parse_legal_hierarchy.py \
  --input-dir data/interim \
  --output-dir data/interim \
  --report artifacts/reports/parsing/legal_parsing_report.json \
  --law-ids LDD_VBHN BLDS_2015
```

**Expected workflow**:
1. Input: `data/interim/{law_id}/normalized.json`
2. Output: `data/interim/{law_id}/hierarchy.json` (tree structure)
3. The hierarchy JSON feeds into the chunker.

**Expected implementation boundary**:
- `scripts/parse_legal_hierarchy.py`: CLI, argparse, console summaries, exit codes.
- `src/services/legal_parsing_service.py`: batch orchestration and report building.
- `src/processing/legal_parser.py`: reusable parser/domain logic.
- `tests/unit/processing/test_legal_parser.py`: focused parser tests.

## Architecture

```
┌──────────────────────┐
│  Normalized Legal    │
│  Text                │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Heading             │
│  Recognizer          │
│  (regex patterns)    │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Span                 │
│  Segmenter            │
│  (assign levels)      │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Hierarchy            │
│  Builder              │
│  (parent-child links) │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Legal Tree           │
│  Validator            │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  LegalDocumentNode    │
│  Tree (JSON)          │
└──────────────────────┘
```

## Components

### 1. Heading Recognizer

**Goal**: Detect legal hierarchy markers using regex patterns.

**Patterns** (Vietnamese):
- `^(Phần\s+[IVXLCDM0-9]+)` → Part
- `^(Chương\s+[IVXLCDM0-9]+)` → Chapter
- `^(Mục\s+[IVXLCDM0-9]+)` → Section
- `^(Điều\s+\d+)(\s*\.\s*.*)?` → Article (optional title after number)
- `^(Khoản\s+(\d+|[a-z]|\(.*?\))\b` → Clause
- `^(Điểm\s+([a-z]|\(.*?\))\b` → Point

**Process**:
- Iterate through text line by line.
- For each line, test against patterns.
- Record: `level` (enum), `number` (extracted number/letter), `title` (rest of line for Articles), `start_offset`, `end_offset`.

**Notes**:
- Regex-only is insufficient alone; it identifies spans but does not build the parent-child tree.
- Parser handles edge cases: missing levels, unusual numbering, multi-line headings.

### 2. Span Segmenter

**Goal**: Convert recognized headings into segments with assigned hierarchy levels.

**Algorithm**:
- Sort detected headings by `start_offset`.
- For each heading, the span extends from its `start_offset` to the next heading's `start_offset` (or EOF).
- Assign each span a `level` based on heading type.
- Build flat list of `LegalNode` objects with:
  - `level`: "part" | "chapter" | "section" | "article" | "clause" | "point"
  - `number`: extracted number (e.g., "1", "I", "a")
  - `title`: for Articles, the title text after "Điều N."
  - `text`: full text content of the span
  - `start_offset`, `end_offset`: character positions in normalized text
  - `parent_id`: to be filled by Hierarchy Builder

### 3. Hierarchy Builder

**Goal**: Construct parent-child relationships to form a tree.

**Rules**:
- Root is either the whole document or the first "Part" if present.
- Each node's parent is the nearest preceding node with a higher level in the hierarchy order: part > chapter > section > article > clause > point.
- Example: a "clause" node's parent is the most recent "article" node that precedes it.
- An "article" with no preceding "section" or "chapter" attaches to the nearest "part" or root.

**Data structure**:
```python
class LegalNode:
    node_id: str
    level: str
    number: str
    title: str | None
    text: str
    start_offset: int
    end_offset: int
    parent_id: str | None
    children: list[str]  # list of node_ids
```

**Output**: Tree with root node containing all others; serialize to JSON with nested children or flat list with `parent_id`.

### 4. Legal Tree Validator

**Goal**: Verify tree integrity before downstream use.

**Checks**:
- All expected levels exist? At minimum, all "Điều" (articles) must be found.
- No orphan nodes: every non-root node has a `parent_id` that exists.
- No cycles: parent chain terminates at root.
- No overlapping spans: `start_offset`/`end_offset` ranges do not overlap between siblings.
- Article numbers are unique within their parent (e.g., no duplicate "Điều 1" in same chapter).
- Clause/Point numbers follow expected patterns.

**Failure handling**:
- Validation error raises `ParsingError` with details.
- Downstream chunking cannot proceed until parser fixes are applied.

## Pipeline Execution Flow

1. Load `normalized.json` for a given `law_id`.
2. Run Heading Recognizer → produce list of heading matches.
3. Run Span Segmenter → assign text spans and levels.
4. Run Hierarchy Builder → link nodes into tree.
5. Run Legal Tree Validator → ensure correctness.
6. Write `hierarchy.json` with full tree and metadata.

## Data Models / Output Schema

### Legal Node Model

```python
from typing import Literal, Optional

Level = Literal["part", "chapter", "section", "article", "clause", "point"]

class LegalNode(BaseModel):
    node_id: str  # e.g., "LDD_VBHN__article_123"
    level: Level
    number: str  # e.g., "123", "I", "a"
    title: Optional[str] = None  # only for article level
    text: str  # full text content of this node's span
    start_offset: int  # char offset in normalized_text
    end_offset: int  # exclusive
    parent_id: Optional[str] = None
    children: list[str] = []  # child node_ids
    metadata: dict = {}  # parser version, confidence?
```

### Hierarchy JSON File (`hierarchy.json`)

```json
{
  "law_id": "LDD_VBHN",
  "source_file": "data/interim/LDD_VBHN/normalized.json",
  "parser_version": "v0.1",
  "root_node_id": "LDD_VBHN__root",
  "nodes": [
    {
      "node_id": "LDD_VBHN__part_1",
      "level": "part",
      "number": "I",
      "title": null,
      "text": "Phần I...\nĐiều 1...",
      "start_offset": 0,
      "end_offset": 5432,
      "parent_id": null,
      "children": ["LDD_VBHN__chapter_1", "LDD_VBHN__article_5"],
      "metadata": {}
    },
    {
      "node_id": "LDD_VBHN__article_1",
      "level": "article",
      "number": "1",
      "title": "Điều 1. Tên điều luật",
      "text": "Điều 1. Tên điều luật\nNội dung của điều luật...",
      "start_offset": 120,
      "end_offset": 456,
      "parent_id": "LDD_VBHN__part_1",
      "children": ["LDD_VBHN__clause_1_1", "LDD_VBHN__clause_1_2"],
      "metadata": {}
    },
    {
      "node_id": "LDD_VBHN__clause_1_1",
      "level": "clause",
      "number": "1",
      "title": null,
      "text": "1. Nội dung của khoản 1...",
      "start_offset": 200,
      "end_offset": 300,
      "parent_id": "LDD_VBHN__article_1",
      "children": ["LDD_VBHN__point_1_1_a"],
      "metadata": {}
    },
    {
      "node_id": "LDD_VBHN__point_1_1_a",
      "level": "point",
      "number": "a",
      "title": null,
      "text": "a) Nội dung của điểm a...",
      "start_offset": 220,
      "end_offset": 280,
      "parent_id": "LDD_VBHN__clause_1_1",
      "children": [],
      "metadata": {}
    }
  ]
}
```

### Node ID Convention

`{law_id}__{level}_{number}` where:
- For article: `__article_{article_number}`
- For clause: `__clause_{article_number}_{clause_number}` (article prefix ensures uniqueness)
- For point: `__point_{article_number}_{clause_number}_{point_label}`

This design ensures globally unique IDs within a law.

## CLI Reference

### Intended Commands

```bash
# Parse all laws
uv run python scripts/parse_legal_hierarchy.py \
  --input-dir data/interim \
  --output-dir data/interim \
  --report artifacts/reports/parsing/legal_parsing_report.json

# Parse specific laws
uv run python scripts/parse_legal_hierarchy.py \
  --law-ids BLDS_2015 LDD_VBHN \
  --input-dir data/interim \
  --output-dir data/interim

# Validate existing hierarchy file
uv run python scripts/parse_legal_hierarchy.py \
  --validate data/interim/LDD_VBHN/hierarchy.json
```

## Testing

**Unit tests**:
- `test_heading_recognizer()`: regex patterns detect all six levels in sample text.
- `test_hierarchy_builder()`: given flat heading list, produces valid tree with correct parent links.
- `test_article_without_clause()`: article with direct point children handled.
- `test_missing_section()`: documents without Mục level parse correctly.
- `test_unusual_numbering()`: Roman numerals, LaTeX-style patterns detected.
- `test_node_id_generation()`: IDs follow convention and are unique.

**Integration tests**:
- Parse a normalized artifact from a known law → hierarchy.json with >99% Điều detection.
- Validate tree: no cycles, all nodes have parent (except root), no overlapping spans.
- Output schema matches Pydantic model.

## Error Handling

- **No articles found**: raise `ParsingError("No Điều detected")` — likely `normalized.json` is empty or malformed.
- **Invalid hierarchy**: orphan node or cycle detected → `ValidationError` with node IDs.
- **Overlapping spans**: `ParsingError` with span details; indicates regex matched overlapping headings.
- **File errors**: `FileNotFoundError`, `IOError` logged per law; continue to next if batch processing.

All errors include `law_id` and context in structured logs.

## Troubleshooting

| Issue | Possible Cause | How to Check | Recommended Fix |
|-------|----------------|--------------|-----------------|
| Zero articles detected | Normalized text lost "Điều" markers OR regex too strict | Search "Điều" in `normalized.json`; test regex manually | Loosen regex, ensure normalization preserves headings |
| Duplicate article numbers | Same number used twice (amendment artifact) | Inspect hierarchy JSON for duplicate numbers | Keep as-is (legal reality) but flag for downstream handling |
| Orphan node (missing parent) | Hierarchy builder failed to link | Check node's `parent_id` in JSON | Review parent-linking logic; ensure levels ordered correctly |
| Overlapping spans | Regex matched heading inside previous span | Compare `start_offset`/`end_offset` of adjacent nodes | Refine regex to be more precise; anchor to line start |
| Parser fails on VBHN document | Consolidated documents have special formatting | Inspect normalized text structure | Add VBHN-specific patterns only when observed in real corpus output |
| Article title missing | Regex did not capture title after number | Look at article node `title` field | Adjust regex to capture optional title text |
| Huge article node (MBs) | Article contains hundreds of Khoản without subdivision | Check `text` length of article node | Verify parser correctly split clauses; if law truly has single massive article, accept |

## Best Practices

- **Regex is a recognizer, not a parser** — use it to find heading boundaries; hierarchy builder creates the tree.
- **Preserve offsets** — `start_offset`/`end_offset` enable traceability to normalized text for citation.
- **Validate aggressively** — fail fast on tree integrity issues; downstream depends on correct hierarchy.
- **Handle missing levels** — documents may lack "Mục" or have articles without "Khoản"; design is flexible.
- **Log statistics** — count of nodes per level, parsing time, validation errors.
- **Deterministic node IDs** — same input should produce identical node IDs every run.

## Changelog

### Version 0.1 (2026-05-21)

- Created initial legal hierarchy parsing documentation.
- Defined components: heading recognizer (regex), span segmenter, hierarchy builder, validator.
- Specified LegalNode model and hierarchy.json schema.
- Provided node ID convention with law_id prefix.
- Documented edge cases: missing levels, articles without clauses, VBHN formatting, unusual numbering.
- Added testing strategy and troubleshooting for common parsing failures.

## Related Documentation

| Document | Status | Description |
|----------|--------|-------------|
| `docs/project_phase_journal.md` | Existing | Project phase journal and pipeline notes |
| `docs/project_setup.md` | Implemented | Environment setup and coding standards |
| `docs/corpus_registry.md` | Implemented | Corpus registry schema and design |
| `docs/raw_corpus_audit.md` | Designed | Raw artifact audit procedure |
| `docs/cleaning_normalization.md` | Existing | HTML-to-text and Unicode normalization |
| `docs/parent_child_chunking.md` | Existing | Parent-child chunking design |
| `docs/processed_jsonl.md` | Existing | JSONL export schema and validation |
