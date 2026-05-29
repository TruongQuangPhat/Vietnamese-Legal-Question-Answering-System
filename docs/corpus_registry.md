# Legal Corpus Registry System

## Overview

The Legal Corpus Registry is the single source of truth for which Vietnamese legal documents are included in the VnLaw-QA system. It defines the exact scope of trusted sources (exclusively from `thuvienphapluat.vn`) and provides all metadata needed for crawling, parsing, and retrieval.

The registry enables:
- **Deterministic corpus selection** — exactly 52 law documents are tracked.
- **Traceability** — every chunk links back to a registry `law_id`.
- **Lifecycle management** — `crawl_status` tracks pending, crawled, failed, or manual review.
- **Legal metadata** — `effective_date`, `expiry_date`, `status` support time-aware retrieval.
- **Prioritization** — `priority` and `tier` guide processing order.

Registry and raw artifacts maintain a strict 1:1 correspondence: 52 `law_id` entries match 52 directories in `data/raw/`.

## Quick Start

The registry is a YAML file at `configs/laws/corpus_registry.yml`.

```yaml
# Example entry
- law_id: "BLDS_2015"
  name: "Bộ luật Dân sự 2015"
  tier: 1
  group: "Bộ luật cốt lõi"
  domain_tags: ["dân sự", "hợp đồng", "tài sản"]
  status: "active"
  source_domain: "thuvienphapluat.vn"
  source_type: "html"
  url: "https://thuvienphapluat.vn/van-ban/Quyen-dan-su/Bo-luat-dan-su-2015-296215.aspx"
  effective_date: "2015-07-01"
  expiry_date: null
  crawl_status: "crawled"
  priority: "critical"
  notes: "VBHN 2023 exists, use consolidated version"
```

**Editing the registry**:
- Add new laws with unique `law_id`.
- Set `crawl_status: "pending"` for new entries to be crawled.
- Never change `law_id` after crawling begins.
- Validate with Pydantic before commit.

## Architecture

```
┌──────────────────────┐
│  Corpus Design       │
│  (52 law selection)  │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Registry Schema     │
│  (YAML + Pydantic)   │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Crawl Lifecycle     │
│  (pending→crawled)   │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Downstream          │
│  Traceability        │
│  (law_id propagation)│
└──────────────────────┘
```

## Components

### 1. Registry Entry Schema

Each entry is validated against a Pydantic model with the following fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `law_id` | string | Yes | Unique identifier (e.g., `BLDS_2015`, `LDD_2024`). Must be stable across versions. |
| `name` | string | Yes | Official Vietnamese law name (e.g., "Bộ luật Dân sự 2015"). |
| `tier` | integer | Yes | Legal hierarchy level: 0=Constitution, 1=Core Codes, 2=Laws, 3=Decrees, etc. |
| `group` | string | Yes | Logical grouping (e.g., "Bộ luật cốt lõi", "Luật chuyên ngành"). |
| `domain_tags` | list[str] | No | Topic tags for future filtering/search (e.g., ["dân sự", "hợp đồng"]). |
| `status` | LegalStatus | No | `active`, `planned`, `inactive`, `amended`, `replaced`. Reflects current legal effect. |
| `source_domain` | string | Yes | Must contain `thuvienphapluat.vn` (trusted source policy). |
| `source_type` | SourceType | Yes | `html`, `pdf`, `doc`, `docx`, `mixed`. Primary format for ingestion. |
| `url` | string | Conditional | Required if `crawl_status` is `pending`. URL to crawl. |
| `effective_date` | string | No | Date when law became effective. Format: `YYYY-MM-DD`. |
| `expiry_date` | string | No | Date when law expires or was repealed. Null if still active. |
| `crawl_status` | CrawlStatus | No | `pending`, `crawled`, `failed`, `manual_review`. Lifecycle state. |
| `priority` | Priority | No | `critical`, `high`, `medium`, `low`. Determines processing order. |
| `notes` | string | No | Human notes (e.g., "VBHN 2023 exists", "Amended by Law XYZ"). |

**Status semantics**:
- `active`: Currently in force.
- `amended`: Modified by later law; original may still have partial effect.
- `replaced`: Fully superseded; keep for historical reference only.
- `inactive`: No longer applicable.
- `planned`: Not yet released; placeholder for future corpus expansion.

**Priority semantics**:
- `critical`: Core civil/criminal codes; process first.
- `high`: Frequently referenced laws.
- `medium`: Standard laws.
- `low`: Obscure or rarely used laws.

### 2. Tier Design

Tiers encode legal hierarchy importance:
- **Tier 0**: Constitution — highest authority, foundational.
- **Tier 1**: Core Codes — Bộ luật cốt lõi (Civil, Criminal, Procedure, etc.).
- **Tier 2**: Ordinary Laws — Luật chuyên ngành (Land, Tax, Labor, etc.).
- **Tier 3+**: Decrees, Ordinances, Regulations (may be added later).

Tier is used for prioritization in crawling and indexing, not for legal validity.

### 3. Domain Grouping

The `group` field organizes laws into logical collections:
- "Bộ luật cốt lõi"
- "Luật chuyên ngành"
- "Luật về hành chính"
- "Luật kinh tế"

This aids in corpus subset selection for specialized QA deployments.

### 4. Crawl Lifecycle Management

**Initial state**: New entries have `crawl_status: "pending"` and `url` set.

**After successful crawl**:
- `crawl_status` → `"crawled"`
- Raw artifact stored at `data/raw/{law_id}/latest/`
- `url` retained for traceability.

**On failure**:
- `crawl_status` → `"failed"`
- Error logged; may be retried manually.

**Manual review**:
- `crawl_status: "manual_review"` for edge cases (captcha, login required, ambiguous content).
- Requires human decision before proceeding.

The crawler respects `crawl_status` and skips already-crawled entries unless `--force` is used.

### 5. Trusted Source Policy

All entries must have `source_domain` containing `thuvienphapluat.vn`. This is enforced at registry validation and crawl time. No exceptions.

`source_type` indicates the primary format; the crawler adapts accordingly. Currently, `html` is the primary format.

### 6. Downstream Traceability

The `law_id` flows through the entire pipeline:
- Raw artifact directory: `data/raw/{law_id}/`
- Chunk `metadata["law_id"]`
- Qdrant payload `law_id`
- Final answer citations reference `law_name` and hierarchical numbers.

This ensures every retrieved chunk can be traced back to its registry entry.

## Pipeline Execution Flow

1. **Corpus design** — decide which 52 laws to include; populate registry entries.
2. **Registry entry creation** — add YAML entries with unique `law_id` and required fields.
3. **Target selection** — crawler reads registry, filters by `crawl_status`, tier, priority.
4. **Crawl execution** — download artifacts, store in `data/raw/{law_id}/latest/`, update `crawl_status`.
5. **Audit validation** — verify raw artifacts match registry (see `docs/raw_corpus_audit.md`).
6. **Downstream processing** — parsing, chunking, embedding all use `law_id` as anchor.

## Data Models / Output Schema

### Registry YAML Structure

```yaml
- law_id: "LDD_2024"
  name: "Luật Đất đai 2024"
  tier: 2
  group: "Luật chuyên ngành"
  domain_tags: ["đất đai", "bất động sản", "quy hoạch"]
  status: "active"
  source_domain: "thuvienphapluat.vn"
  source_type: "html"
  url: "https://thuvienphapluat.vn/..."
  effective_date: "2025-01-01"
  expiry_date: null
  crawl_status: "crawled"
  priority: "critical"
  notes: "Consolidated VBHN 2025"
```

### Pydantic Validation Model

```python
from typing import Literal

LegalStatus = Literal["active", "planned", "inactive", "amended", "replaced"]
CrawlStatus = Literal["pending", "crawled", "failed", "manual_review"]
Priority = Literal["critical", "high", "medium", "low"]
SourceType = Literal["html", "pdf", "doc", "docx", "mixed"]

class CorpusEntry(BaseModel):
    law_id: str = Field(pattern=r"^[A-Z_]+_\d{4}$")  # e.g., BLDS_2015
    name: str
    tier: int = Field(ge=0)
    group: str
    domain_tags: list[str] = []
    status: LegalStatus
    source_domain: str
    source_type: SourceType
    url: str | None = None
    effective_date: str | None = None  # YYYY-MM-DD
    expiry_date: str | None = None
    crawl_status: CrawlStatus = "pending"
    priority: Priority = "medium"
    notes: str | None = None
```

### Registry Summary

The registry file itself should contain exactly 52 top-level list entries. A validation script checks:
- All `law_id` values are unique.
- All required fields are present.
- `source_domain` includes `thuvienphapluat.vn`.
- `crawl_status` values are valid.
- No duplicate entries.

## CLI Reference

### Intended CLI (deprecated)
The following module-based commands are deprecated. Registry validation now occurs automatically during the Crawling and Audit phases.

```bash
# Use official scripts instead:
# uv run python scripts/crawl_raw_corpus.py ...
# uv run python scripts/audit_raw_corpus.py ...
```


## Testing

**Unit tests** for `CorpusEntry` Pydantic model:
- Valid entry with all fields passes.
- Missing `law_id` raises `ValidationError`.
- Invalid `effective_date` format raises `ValidationError`.
- Invalid `tier` (negative) raises `ValidationError`.

**Integration test**:
- Load entire `corpus_registry.yml` → list of 52 valid entries.
- Count check: `len(entries) == 52`.
- All `law_id` unique.
- All entries with `crawl_status="crawled"` have corresponding `data/raw/{law_id}/` directory.

## Error Handling

- **Invalid YAML syntax**: `yaml.YAMLError` raised; fix YAML formatting.
- **Pydantic validation failure**: `ValidationError` with field-level errors; correct entry fields.
- **Missing registry file**: `FileNotFoundError`; ensure `configs/laws/corpus_registry.yml` exists.
- **Duplicate law_id**: Raise `DuplicateLawIdError` with conflicting IDs listed.
- **source_domain mismatch**: Raise `TrustedDomainError` if any entry lacks `thuvienphapluat.vn`.

All errors are logged with structured context.

## Troubleshooting

| Issue | Possible Cause | How to Check | Recommended Fix |
|-------|----------------|--------------|-----------------|
| Crawler skips a law I added | `crawl_status` not `pending` | Inspect registry entry | Set `crawl_status: "pending"` for new laws |
| Validation fails on `effective_date` | Wrong date format | Check date string | Use `YYYY-MM-DD` format |
| Duplicate `law_id` error | Two entries share same ID | Check error message | Assign unique `law_id` |
| `url` field missing for pending entry | Registry incomplete | Look for `url: null` | Add valid `thuvienphapluat.vn` URL |
| Crawler rejects source_domain | Domain not trusted | Verify `source_domain` value | Must contain `thuvienphapluat.vn` exactly |
| Registry loads 0 entries | Wrong file path or empty YAML | Check `configs/laws/corpus_registry.yml` exists and has content | Fix path or add entries |

## Best Practices

- **Immutability of `law_id`** — never change after creation; downstream artifacts depend on it.
- **Descriptive names** — `name` should match official law title; avoid abbreviations.
- **Effective dates matter** — fill `effective_date` for time-aware filtering; use `null` only if truly unknown.
- **Use `notes` for context** — record VBHN references, amendment history, special handling.
- **Group logically** — consistent `group` values enable corpus subsetting.
- **Prioritize core laws** — set `priority: "critical"` for foundational codes.
- **Keep registry as source of truth** — never modify raw artifacts independently; always trace back to registry.

## Changelog

### Version 0.1 (2026-05-21)

- Created initial corpus registry documentation.
- Documented registry schema (law_id, name, tier, group, status, source_domain, source_type, url, dates, crawl_status, priority, notes).
- Explained tier design and domain grouping.
- Defined crawl lifecycle states and trusted source policy.
- Provided Pydantic validation model example.
- Added troubleshooting table for common registry issues.

## Related Documentation

| Document | Status | Description |
|----------|--------|-------------|
| `docs/project_phase_journal.md` | Existing | Project phase journal and pipeline notes |
| `docs/project_setup.md` | Implemented | Environment setup and coding standards |
| `docs/raw_corpus_audit.md` | Designed | Raw artifact audit procedure |
| `docs/legal_parsing.md` | Existing | Legal hierarchy parsing algorithm |
| `docs/parent_child_chunking.md` | Existing | Parent-child chunking design |
