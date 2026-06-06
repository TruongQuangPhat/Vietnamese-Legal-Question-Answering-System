---
name: vnlaw-legal-parsing-chunking
description: Use when implementing legal hierarchy parsing, Regex/AST extraction, parent-child chunking, legal metadata schemas, cross-reference extraction, and JSONL chunk output.
allowed-tools: Read, Grep, Glob, LS, Bash, Edit, MultiEdit, Write
---

# Legal Parsing and Parent-Child Chunking Skill

Use this skill for Vietnamese legal hierarchy extraction (Phase 5) and parent-child chunking (Phase 6).

This skill runs after cleaning/normalization (Phase 4) and before embedding/indexing (Phase 8).

Current project status: Phase 5 Legal Hierarchy Parsing is complete and
hardened with 52/52 hierarchy outputs, 0 parser failures, 0 validator failures,
0 RED/ORANGE audit cases, and 0 source-tail leakage nodes. Phase 6
Parent-child Chunking is next and not yet implemented. Use
`data/interim/{LAW_ID}/hierarchy.json` as the Phase 6 input.

## Phase 5 — Legal Hierarchy Parsing

### Goal

Convert normalized legal text into a validated, deterministic legal hierarchy tree.

```text
normalized.json
→ heading recognition (regex)
→ span segmentation
→ hierarchy tree building
→ tree validation
→ hierarchy.json
```

### Legal Hierarchy Levels

Always preserve:

```text
Phần → Chương → Mục → Điều → Khoản → Điểm
```

Corresponding `LegalNodeLevel` enum values:

```text
PART → CHAPTER → SECTION → ARTICLE → CLAUSE → POINT
```

Do not flatten hierarchy into plain text chunks.

### Parser Strategy

Use regex as a first-pass recognizer, then build a structured tree.

```python
PATTERNS = {
    "phan":    re.compile(r"^Phần\s+(Thứ\s+)?([IVXLCDM0-9]+)\s*[:.]?\s*(.+)?$", re.MULTILINE),
    "chuong":  re.compile(r"^Chương\s+(Thứ\s+)?([IVXLCDM0-9]+)\s*[:.]?\s*(.+)?$", re.MULTILINE),
    "muc":     re.compile(r"^Mục\s+(\d+|[A-Z]+)\s*[:.]?\s*(.+)?$", re.MULTILINE),
    "dieu":    re.compile(r"^Điều\s+(\d+[a-z]?)\.\s*(.+)?$", re.MULTILINE),
    "khoan":   re.compile(r"^(\d+)\.\s+(.+)", re.MULTILINE),
    "diem":    re.compile(r"^([a-zđ])\)\s+(.+)", re.MULTILINE),
}
```

Regex patterns are a recognizer, not a parser. The hierarchy builder creates the actual tree structure.

### Tree Structure

Output is a flat list of `LegalNode` objects linked by `node_id` / `parent_id` / `children`:

```json
{
  "schema_version": "1.0",
  "parser_version": "v0.1.0",
  "cleaner_version": "v0.8.0",
  "law_id": "LDD_VBHN",
  "source_file": "data/interim/LDD_VBHN/normalized.json",
  "root_node_id": "LDD_VBHN__root",
  "metadata": { "law_name", "source_url", "source_domain", ... },
  "warnings": [],
  "nodes": [
    {
      "node_id": "LDD_VBHN__root",
      "level": "law",
      "number": null,
      "title": null,
      "text": "...",
      "start_offset": 0,
      "end_offset": 12345,
      "parent_id": null,
      "children": ["LDD_VBHN__root__chapter_I", ...],
      "metadata": {}
    },
    {
      "node_id": "LDD_VBHN__root__chapter_I__article_4",
      "level": "article",
      "number": "4",
      "title": "Người sử dụng đất",
      "text": "Điều 4. Người sử dụng đất\n1. Tổ chức trong nước gồm:\na) ...",
      "start_offset": 11600,
      "end_offset": 13220,
      "parent_id": "LDD_VBHN__root__chapter_I",
      "children": ["...__clause_1", "...__clause_2"],
      "metadata": {
        "heading_text": "Điều 4. Người sử dụng đất",
        "heading_start_offset": 11600,
        "heading_end_offset": 11625,
        "line_number": 61,
        "recognition_classification": "certain"
      }
    }
  ]
}
```

**Critical design**: `text` on a parent node is the **full concatenated text including all descendants**. An article node's `text` contains its heading plus all clause text plus all point text. This is intentional — parent text is used for LLM context without reparsing.

### Node ID Convention

Deterministic, underscore-joined path:

```text
{law_id}__root                                              # Law root
{law_id}__root__chapter_I                                   # Chapter
{law_id}__root__chapter_I__section_1                        # Section
{law_id}__root__chapter_I__article_4                        # Article
{law_id}__root__chapter_I__article_4__clause_1              # Clause
{law_id}__root__chapter_I__article_4__clause_1__point_a     # Point
```

Collision resolution appends `__occurrence_2`, `__occurrence_3`, etc.

### Parser Components

```text
LegalHeadingRecognizer    → regex heading detection
LegalSpanSegmenter        → heading-to-source-span conversion
LegalHierarchyBuilder     → tree construction from segments
LegalTreeValidator        → tree integrity validation
LegalParser               → per-document parser facade
```

## Phase 6 — Parent-Child Chunking

Status: Next phase, not implemented yet.

### Goal

Convert the validated hierarchy tree into citation-traceable child chunks for embedding, with Article-level parent context for the LLM.

```text
hierarchy.json
→ load hierarchy document
→ index nodes by node_id
→ for each article: create parent chunk
→ for each clause/point under article: create child chunk
→ write chunks.jsonl
→ validate
→ write chunking_report.json
```

### Chunk ID Convention

```text
{law_id}__article_{N}__clause_{M}__point_{X}    # Point-level chunk
{law_id}__article_{N}__clause_{M}                # Clause-level chunk (no points)
{law_id}__article_{N}                             # Article-level chunk (no clauses)
```

### Citation Format

Vietnamese, never English:

```text
Luật {law_name}, Điều {article_number}, Khoản {clause_number}, Điểm {point_label}
```

Omit `Khoản`/`Điểm` segments when absent. Minimum: `"Luật ..., Điều N"`.

### Canonical Chunk Schema

```python
class HierarchyPath(BaseModel):
    part: str | None
    chapter: str | None
    section: str | None
    article: str                    # Required
    clause: str | None
    point: str | None

class LegalChunk(BaseModel):
    chunk_id: str
    law_id: str
    law_name: str
    law_type: str                   # "vbhn" | "original"
    legal_status: str               # "active" | "amended" | "replaced"
    level: str                      # "article" | "clause" | "point"
    article_number: str
    article_title: str | None
    clause_number: str | None
    point_label: str | None
    hierarchy_path: HierarchyPath
    text: str                       # Child text (clause or point body)
    parent_id: str                  # e.g. "{law_id}__article_{N}"
    parent_text: str                # Full article text (from parent node)
    citation: str                   # Vietnamese citation
    source_url: str
    source_domain: str
    source_type: str
    issued_date: str | None
    effective_date: str | None
    expiry_date: str | None
    text_hash: str                  # SHA-256 of `text`
    metadata: dict[str, Any]        # parser_version, chunker_version, raw_artifact_path
```

### Parent-Child Rules

- **Child unit** = leaf node (`level="clause"` or `"point"`).
- **Parent context** = the full Article node `text` (includes all descendants).
- **Article with no clauses**: the article itself becomes a child chunk at `level="article"`.
- **Article with clauses**: each clause becomes a child chunk; if clauses have points, each point becomes a child chunk (not the clause).
- **Embedding target**: child `text`.
- **LLM context**: `parent_text` + metadata.

### Hierarchy Path Builder

Build from the node's ancestry chain by walking `parent_id` references:

```python
# For a point node: walk up to find containing article, chapter, etc.
ancestors = {node.node_id: node for node in document.nodes}
path = HierarchyPath(
    part=ancestors.get(part_node_id).number if part_node_id else None,
    chapter=ancestors.get(chapter_node_id).number if chapter_node_id else None,
    section=ancestors.get(section_node_id).number if section_node_id else None,
    article=article_node.number,     # Required
    clause=clause_node.number if clause_node_id else None,
    point=point_node.number if point_node_id else None,
)
```

### Metadata Propagation

Attach from `LegalHierarchyDocument.metadata` and `LegalNode.metadata`:

```text
law_id, law_name, law_type, legal_status
source_url, source_domain, source_type
issued_date, effective_date, expiry_date
parser_version, chunker_version, raw_artifact_path
```

### Chunk Validator Rules

1. `chunk_id` is unique across all chunks.
2. `text` is non-empty after stripping.
3. `parent_id` references an existing article node in the hierarchy.
4. `citation` matches `r"^Luật .+, Điều \d+(, Khoản \d+(, Điểm [a-z])?)?$"`.
5. `hierarchy_path.article` is non-empty.
6. `text_hash` matches `sha256(text)`.
7. `source_url` is a valid URL.

### OOP and Code Quality Rules

Expected components:

```text
LegalChunker           → hierarchy-to-chunk conversion
LegalChunkValidator    → chunk schema + invariant validation
ChunkingService        → batch orchestration + report building
ProcessedChunk         → Pydantic model for validated chunks (Phase 7)
```

Rules:

- Keep parsing, chunking, and JSONL export in separate modules.
- Use typed models rather than raw dictionaries at module boundaries.
- Public classes/functions must have Google-style docstrings.
- Docstrings must explain hierarchy assumptions and edge cases.

### Verification

- Article count in chunks matches hierarchy within tolerance.
- Every chunk has law metadata, hierarchy metadata, source URL.
- Parent-child relationship is deterministic (same input → same chunk IDs).
- Parser/chunker tests cover at least three law templates.
- Edge cases include: titleless articles, articles without clauses, Vietnamese `đ`, Roman numerals.

### Do Not

- Do not use arbitrary character splitting.
- Do not collapse Article/Clause/Point hierarchy.
- Do not drop parent Article context.
- Do not fabricate cross-reference targets in chunks.
- Do not emit chunks that fail schema validation.
- Do not mix parser logic with embedding or vector store logic.
