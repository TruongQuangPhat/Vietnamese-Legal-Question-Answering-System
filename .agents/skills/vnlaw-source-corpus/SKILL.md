---
name: vnlaw-source-corpus
description: Use when adding, validating, crawling, prioritizing, or versioning Vietnamese legal data sources, corpus registry entries, trusted source metadata, and raw corpus maintenance.
---

# Source Corpus and Legal Data Registry Skill

Use this skill for trusted source selection, crawl planning, corpus registry tasks, and legal source metadata maintenance.

## Current Status

The current corpus is registry-driven and contains 52 Vietnamese legal documents from the trusted source. The processed corpus currently has 40,389 validated legal chunks.

Use this skill for maintenance, validation, review, or explicitly scoped corpus expansion. Do not modify the corpus registry, crawl new sources, or mutate protected corpus artifacts unless the user explicitly scopes that task.

Protected paths include:

```text
data/raw/**
data/interim/**
data/reports/**
data/processed/legal_chunks.jsonl
```

## Trusted Source

Default trusted source:

```text
https://thuvienphapluat.vn
```

Do not crawl from other sources unless explicitly approved and documented.

## VBHN First Strategy

Prefer VBHN documents because they consolidate amendments into one legal text and reduce version-management complexity.

When VBHN exists:

```text
Use the latest applicable VBHN version.
```

When no VBHN exists:

```text
1. Crawl the original law.
2. Crawl amendments chronologically when explicitly scoped.
3. Record effective and expiry dates when available.
4. Preserve version metadata for future or separately scoped time-aware validity handling.
```

Do not claim query-time legal validity resolution unless a time-aware workflow is explicitly implemented and evaluated.

## Law ID Naming Convention

Use:

```text
{ACRONYM}_VBHN
```

for consolidated documents, and:

```text
{ACRONYM}_{YEAR}
```

for original laws with no amendment or complete replacement laws.

Examples:

```text
BLHS_VBHN
LDD_VBHN
BLDS_2015
LVL_2025
```

## Corpus Registry Location

Use:

```text
configs/laws/corpus_registry.yml
```

This file is the source of truth for crawl targets and legal metadata.

Do not hardcode corpus URLs in Python source code.

## Corpus Registry Entry

Recommended fields:

```yaml
law_id: "LDD_VBHN"
name: "Luật Đất đai (VBHN 2025)"
tier: 2
group: "Đất đai, BĐS, Xây dựng & Môi trường"
domain_tags: ["đất đai", "bất động sản"]
status: "active"
source_domain: "thuvienphapluat.vn"
source_type: "html"
source_url: "https://thuvienphapluat.vn/..."
effective_date: "YYYY-MM-DD"
expiry_date: null
crawl_status: "pending"
priority: "high"
notes: ""
```

Preserve enough metadata for downstream legal hierarchy parsing, citation traceability, retrieval filters, and future validity handling.

## Crawl Status Values

Recommended values:

```text
pending
crawling
crawled
parsed
ingested
verified
failed
manual_review
```

Use `manual_review` for unusual pages, missing URLs, ambiguous legal versions, or documents embedded as PDF/DOC/DOCX when parser support is incomplete.

## Crawl Safety

* Respect rate limiting.
* Use a clear User-Agent.
* Validate source domain before crawling.
* Cache raw artifacts under `data/raw/{law_id}/latest/`.
* Preserve timestamped snapshots under `data/raw/{law_id}/crawls/{timestamp}/` when refreshed.
* Never overwrite raw source without timestamp/hash traceability.
* Preserve source URL and parser/version metadata in downstream outputs.
* Do not run real crawling unless explicitly scoped.

## Verification

For each added or modified law:

* verify URL is from trusted source;
* verify Law ID follows naming convention;
* verify source metadata is complete;
* verify raw artifact storage is traceable;
* verify article count against source within acceptable tolerance when parsing is involved;
* verify hierarchy extraction when parsing is involved;
* add or update parser/chunking tests for representative structures when the change affects downstream processing.

Prefer small fixtures and `tmp_path` for tests. Do not use real crawl outputs in routine tests unless explicitly scoped.

## Do Not

* Do not add unapproved sources.
* Do not use vague Law IDs.
* Do not mix original law and VBHN without version metadata.
* Do not omit effective-date metadata when it is available.
* Do not hardcode corpus URLs in Python source code.
* Do not modify protected corpus artifacts unless explicitly scoped.
* Do not run real crawling, cleaning, parsing, chunking, embedding, or indexing as routine validation.
