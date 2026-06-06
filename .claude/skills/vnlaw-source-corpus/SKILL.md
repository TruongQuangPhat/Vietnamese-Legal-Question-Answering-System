---
name: vnlaw-source-corpus
description: Use when adding, validating, crawling, prioritizing, or versioning Vietnamese legal data sources and corpus registry entries.
allowed-tools: Read, Grep, Glob, LS, Bash, Edit, MultiEdit, Write
---

# Source Corpus and Legal Data Registry Skill

Use this skill for source, crawl, and corpus registry tasks.

## Trusted Source

Default trusted source:

```text
https://thuvienphapluat.vn
```

Do not crawl from other sources unless explicitly approved and documented.

## VBHN First Strategy

Prefer VBHN documents because they consolidate amendments into one legal text.

When VBHN exists:

```text
Use the latest applicable VBHN version.
```

When no VBHN exists:

```text
1. Crawl the original law.
2. Crawl amendments chronologically.
3. Record effective and expiry dates.
4. Resolve applicable version at query time.
```

## Law ID Naming Convention

Consolidated documents:

```text
{ACRONYM}_VBHN
```

Original laws (no amendment or complete replacement):

```text
{ACRONYM}_{YEAR}
```

Examples:

```text
BLHS_VBHN    # Bộ luật Hình sự - VBHN
LDD_VBHN     # Luật Đất đai - VBHN
BLDS_2015    # Bộ luật Dân sự 2015 (original)
LVL_2025     # Luật Viên chức 2025 (original)
```

## Corpus Registry Location

```text
configs/laws/corpus_registry.yml
```

This file is the source of truth for crawl targets and legal metadata.

## Corpus Registry Entry

```yaml
law_id: "LDD_VBHN"
name: "Luật Đất đai (VBHN 2025)"
tier: 2
group: "Đất đai, BĐS, Xây dựng & Môi trường"
domain_tags: ["đất đai", "bất động sản"]
status: "active"
source_domain: "thuvienphapluat.vn"
source_type: "html"              # html | pdf | doc | docx | mixed | unknown
source_url: "https://thuvienphapluat.vn/..."
effective_date: "YYYY-MM-DD"
expiry_date: null
crawl_status: "pending"          # pending | crawling | crawled | parsed | ingested | failed | manual_review
priority: "high"                 # critical | high | medium | low
notes: ""
```

## Crawl Status Values

```text
pending → crawling → crawled → parsed → ingested → verified
                                                      ↘ failed / manual_review
```

Use `manual_review` for unusual pages, missing URLs, or documents embedded as PDF/DOC/DOCX when parser support is incomplete.

## Crawl Safety

- Respect rate limiting (2s per host default).
- Use a clear User-Agent.
- Cache raw artifacts under `data/raw/{law_id}/`.
- Never overwrite raw source without timestamp/hash traceability.
- Preserve source URL and parser version in every processed node.

## Verification

For each added law:

- verify URL is from trusted source;
- verify Law ID follows naming convention;
- verify article count against source within +/-2%;
- verify hierarchy extraction;
- verify metadata completeness.

## Do Not

- Do not add unapproved sources.
- Do not use vague Law IDs.
- Do not mix original law and VBHN without version metadata.
- Do not omit effective-date metadata when available.
- Do not hardcode corpus URLs in Python source code.
