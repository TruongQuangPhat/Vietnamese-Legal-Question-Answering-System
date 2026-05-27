---
name: vnlaw-data-ingestion
description: Use for registry-driven legal crawling, raw source storage, source metadata, batch ingestion, retry/rate-limit policy, and Phase 1 ingestion pipeline implementation for VnLaw-QA.
---

# Data Ingestion Skill

Use this skill when implementing, reviewing, or debugging legal data ingestion.

The preferred ingestion workflow is registry-driven:

```text
config/laws/corpus_registry.yml
  → async crawler
  → raw artifact storage
  → metadata.json
  → cleaning/normalization
  → legal parsing
  → parent-child chunking
  → processed JSONL
  → verification
```

For Phase 1, focus only on reliable corpus acquisition, raw storage, parsing, chunking, and JSONL validation.

Do not jump into embedding, Qdrant, Neo4j, Advanced RAG, or GraphRAG until the parsed corpus is reliable.

## Trusted Source

Only crawl:

```text
https://thuvienphapluat.vn
```

Do not crawl other domains unless explicitly approved.

Prefer VBHN documents when available. If no VBHN exists, preserve original law and amendment chronology with effective-date metadata.

## Expected Files

```text
config/laws/corpus_registry.yml

src/ingestion/crawler.py
src/ingestion/parsers/html_parser.py
src/ingestion/parsers/attachment_parser.py
src/ingestion/parsers/legal_parser.py
src/ingestion/chunkers.py
src/ingestion/pipeline.py

data/raw/{law_id}/main.html
data/raw/{law_id}/metadata.json
data/raw/{law_id}/attachments/
data/processed/{law_id}.jsonl

tests/unit/ingestion/
tests/integration/test_ingestion_pipeline.py
```

## Corpus Registry

The crawler must read crawl targets from:

```text
config/laws/corpus_registry.yml
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

The crawler must support:

- crawl all `pending` laws;
- crawl by tier;
- crawl by group;
- crawl by explicit `law_id`;
- crawl from a temporary approved URL list;
- continue after individual target failures;
- report a final crawl summary.

## Raw Storage Contract

Every crawled law must be stored under:

```text
data/raw/{law_id}/
```

Recommended layout:

```text
data/raw/{law_id}/
├── main.html
├── metadata.json
├── pages/
└── attachments/
```

Always save the raw artifact before parsing.

If the legal content is embedded in PDF/DOC/DOCX, save both the landing HTML and the attachment. If attachment parsing is not implemented, mark the target as `manual_review`.

## Metadata Contract

Every law must have:

```text
data/raw/{law_id}/metadata.json
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

- Use async I/O.
- Use conservative rate limiting.
- Default delay: 2 seconds per host.
- Default batch concurrency: 2.
- Absolute max concurrency: 3 unless explicitly approved.
- Use retries with exponential backoff.
- Use a valid User-Agent.
- Validate source domain before crawling.
- Store raw HTML/PDF/DOC/DOCX before parsing.
- Compute content hash for every raw artifact.
- Record actionable failure metadata.
- Never use `except Exception: pass`.

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

- Use Pydantic models at data boundaries.
- Keep crawler, parser, chunker, embedder, vector store, and graph store separate.
- Do not create a god class that performs crawling, parsing, embedding, and ingestion together.
- Public classes and functions must have Google-style docstrings.
- Docstrings must explain purpose, args, returns, raises, side effects, and traceability assumptions.

## Commands

Crawl one law for debugging:

```bash
uv run python scripts/crawl_raw_corpus.py \
  --url "https://thuvienphapluat.vn/..." \
  --law-id "LDD_VBHN" \
  --output data/raw/
```

Crawl all pending laws:

```bash
uv run python scripts/crawl_raw_corpus.py \
  --registry config/laws/corpus_registry.yml \
  --output data/raw \
  --only-status pending \
  --concurrency 2 \
  --delay-seconds 2 \
  --retry 3
```

Crawl specific laws:

```bash
uv run python scripts/crawl_raw_corpus.py \
  --registry config/laws/corpus_registry.yml \
  --law-ids HP_2013 BLDS_2015 LDD_VBHN \
  --output data/raw
```

Run raw corpus audit:

```bash
uv run python scripts/audit_raw_corpus.py \
  --registry config/laws/corpus_registry.yml \
  --raw-dir data/raw \
  --output data/reports/raw_corpus_audit.json
```

Run cleaning & normalization:

```bash
uv run python scripts/clean_raw_corpus.py \
  --raw-dir data/raw \
  --output-dir data/interim \
  --report data/reports/cleaning_report.json
```

## Definition of Done

- [ ] `corpus_registry.yml` exists and contains Phase 1 targets.
- [ ] Batch crawler supports registry-driven crawling.
- [ ] Single-law crawling still works for debugging.
- [ ] Every crawled law has raw artifacts and `metadata.json`.
- [ ] Every raw artifact has a content hash.
- [ ] Failed crawls are traceable and actionable.
- [ ] Attachment-based documents are handled or marked `manual_review`.
- [ ] Processed JSONL validates against `LegalChunkNode`.
- [ ] No arbitrary character splitting is used.
- [ ] Article count matches source within ±2%.
- [ ] Parser/chunker tests cover at least three law templates.

## Do Not

- Do not crawl unapproved sources.
- Do not hardcode corpus URLs in Python source code.
- Do not parse directly from network responses.
- Do not skip raw source storage.
- Do not suppress crawler/parser errors.
- Do not overwrite raw or processed artifacts without traceability.
- Do not mix crawler, parser, embedding, vector DB, and graph DB logic in one class.