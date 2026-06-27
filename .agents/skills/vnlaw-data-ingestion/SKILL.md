---
name: vnlaw-data-ingestion
description: Use for registry-driven legal crawling, raw source storage, source metadata, batch ingestion, retry/rate-limit policy, raw corpus audit, and ingestion maintenance for VnLaw-QA.
---

# Data Ingestion Skill

Use this skill when maintaining, reviewing, or debugging legal data ingestion and raw corpus acquisition.

The preferred ingestion workflow is registry-driven:

```text
configs/laws/corpus_registry.yml
  → async crawler
  → raw artifact storage
  → metadata.json
  → raw corpus audit
  → cleaning/normalization
  → legal parsing
  → parent-child chunking
  → processed JSONL
  → embedding/indexing readiness
```

## Current Status

The registry-driven ingestion workflow is implemented for the current 52-document Vietnamese legal corpus. Downstream cleaning, legal parsing, parent-child chunking, processed JSONL validation, embedding/indexing, retrieval, and strict generation evaluation have also been completed.

Use this skill for maintenance, debugging, audit, or regression fixes in crawling and raw artifact handling. Do not expand ingestion behavior unless a concrete raw-corpus defect is proven with direct examples, traceable metadata, and tests.

Raw corpus paths are protected. Do not modify `data/raw/**`, `data/interim/**`, `data/reports/**`, or `data/processed/legal_chunks.jsonl` unless the user explicitly scopes that operation.

Workflow-level integration tests for corpus processing exist under:

```text
tests/integration/corpus/
```

## Trusted Source

Only crawl:

```text
https://thuvienphapluat.vn
```

Do not crawl other domains unless explicitly approved.

Prefer VBHN documents when available. If no VBHN exists, preserve original law and amendment chronology with effective-date metadata when available.

## Expected Files

```text
configs/laws/corpus_registry.yml

src/ingestion/crawler.py
src/ingestion/audit.py
src/ingestion/registry.py
src/ingestion/storage.py
src/services/crawl_service.py
src/services/raw_audit_service.py
scripts/corpus/crawl_raw_corpus.py
scripts/corpus/audit_raw_corpus.py

data/raw/{law_id}/latest/main.html
data/raw/{law_id}/latest/metadata.json
data/raw/{law_id}/crawls/{timestamp}/
data/raw/{law_id}/attachments/

tests/unit/ingestion/
tests/unit/ingestion/test_crawler.py
tests/unit/ingestion/test_audit.py
tests/unit/services/test_crawl_service.py
tests/unit/services/test_raw_audit_service.py
tests/integration/corpus/
```

## Corpus Registry

The crawler must read crawl targets from:

```text
configs/laws/corpus_registry.yml
```

Minimum registry fields:

```yaml
corpus:
  - law_id: "LDD_VBHN"
    name: "Luật Đất đai (VBHN 2025)"
    tier: 2
    group: "Đất đai, BĐS, Xây dựng & Môi trường"
    source_domain: "thuvienphapluat.vn"
    source_type: "html"   # html | pdf | doc | docx | mixed | unknown
    url: "https://thuvienphapluat.vn/..."
    status: "pending"    # pending | crawling | crawled | parsed | ingested | failed | manual_review
    priority: "high"
    notes: null
```

The crawler should support:

* crawl all `pending` laws;
* crawl by tier;
* crawl by group;
* crawl by explicit `law_id`;
* crawl from a temporary approved URL list;
* continue after individual target failures;
* report a final crawl summary.

Do not hardcode corpus URLs in Python source code.

## Raw Storage Contract

Every crawled law must be stored under:

```text
data/raw/{law_id}/
```

Implemented layout:

```text
data/raw/{law_id}/
├── latest/
│   ├── main.html
│   └── metadata.json
└── crawls/
    └── {timestamp}/
        ├── main.html
        └── metadata.json
```

Always save the raw artifact before parsing.

If the legal content is embedded in PDF/DOC/DOCX, save both the landing HTML and the attachment. If attachment parsing is not implemented, mark the target as `manual_review`.

## Metadata Contract

Every law must have:

```text
data/raw/{law_id}/latest/metadata.json
```

Metadata must include at least:

```text
law_id
name
tier
source_domain
source_type
url
crawl_status
http_status
crawled_at
content_hash
crawler_version
parser_hint
attachment_paths
error_message
```

Do not overwrite raw artifacts without traceability or content-hash history.

## Crawler Rules

* Use async I/O.
* Use conservative rate limiting.
* Default delay: 2 seconds per host.
* Default batch concurrency: 2.
* Absolute max concurrency: 3 unless explicitly approved.
* Use retries with exponential backoff.
* Use a valid User-Agent.
* Validate source domain before crawling.
* Store raw HTML/PDF/DOC/DOCX before parsing.
* Compute content hash for every raw artifact.
* Record actionable failure metadata.
* Never use `except Exception: pass`.

## OOP and Code Quality Rules

Use clear object-oriented boundaries.

Recommended components:

```text
CrawlTarget
CrawlResult
BaseCrawler
ThuvienPhapLuatCrawler
CorpusRegistryLoader
RawArtifactStore
CrawlStatusWriter
```

Rules:

* Use Pydantic models at data boundaries.
* Keep crawler, parser, chunker, embedder, vector store, and graph store separate.
* Do not create a god class that performs crawling, parsing, embedding, and ingestion together.
* Public classes and functions must have Google-style docstrings.
* Docstrings must explain purpose, args, returns, raises, side effects, and traceability assumptions.

## Commands

These commands touch protected corpus/artifact paths. Run them only when the user explicitly scopes a real corpus ingestion or audit task.

Crawl one law for debugging:

```bash
uv run python scripts/corpus/crawl_raw_corpus.py \
  --url "https://thuvienphapluat.vn/..." \
  --law-id "LDD_VBHN" \
  --output data/raw/
```

Crawl all pending laws:

```bash
uv run python scripts/corpus/crawl_raw_corpus.py \
  --registry configs/laws/corpus_registry.yml \
  --output data/raw \
  --report artifacts/reports/crawling/crawl_report.json \
  --only-status pending \
  --concurrency 2 \
  --delay-seconds 2 \
  --retry 3
```

Crawl specific laws:

```bash
uv run python scripts/corpus/crawl_raw_corpus.py \
  --registry configs/laws/corpus_registry.yml \
  --law-ids HP_2013 BLDS_2015 LDD_VBHN \
  --output data/raw
```

Run raw corpus audit:

```bash
uv run python scripts/corpus/audit_raw_corpus.py \
  --registry configs/laws/corpus_registry.yml \
  --raw-dir data/raw \
  --output artifacts/reports/audit/raw_corpus_audit.json
```

Run cleaning and normalization:

```bash
uv run python scripts/corpus/clean_raw_corpus.py \
  --raw-dir data/raw \
  --output-dir data/interim \
  --report artifacts/reports/cleaning/cleaning_report.json
```

For tests, prefer tiny fixtures, mocks/fakes, and `tmp_path` instead of real corpus paths.

## Maintenance Checklist

Use this checklist when changing ingestion behavior:

* [ ] Registry-driven crawling still works.
* [ ] Single-law crawling still works for debugging.
* [ ] Every crawled law has `latest/main.html` and `latest/metadata.json`.
* [ ] Every raw artifact has a content hash.
* [ ] Failed crawls are traceable and actionable.
* [ ] Attachment-based documents are handled or marked `manual_review`.
* [ ] Raw corpus audit reports missing/corrupt artifacts before cleaning.
* [ ] Crawler changes do not modify parser, chunker, embedding, vector DB, or graph DB logic.
* [ ] Unit tests cover the changed behavior.
* [ ] Integration tests use tiny fixtures and do not require real crawling unless explicitly scoped.

## Do Not

* Do not crawl unapproved sources.
* Do not hardcode corpus URLs in Python source code.
* Do not parse directly from network responses.
* Do not skip raw source storage.
* Do not suppress crawler/parser errors.
* Do not overwrite raw or processed artifacts without traceability.
* Do not mix crawler, parser, embedding, vector DB, and graph DB logic in one class.
* Do not modify protected corpus outputs unless explicitly scoped.
* Do not run real crawling, cleaning, or audit commands as part of routine validation.
