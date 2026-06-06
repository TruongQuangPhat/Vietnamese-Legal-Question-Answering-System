---
name: vnlaw-data-ingestion
description: Use for registry-driven legal crawling, raw source storage, source metadata, batch ingestion, retry/rate-limit policy, and Phase 1 ingestion pipeline implementation for VnLaw-QA.
allowed-tools: Read, Grep, Glob, LS, Bash, Edit, MultiEdit, Write
---

# Data Ingestion Skill

Use this skill when implementing, reviewing, or debugging legal data ingestion (Phases 1-4).

The preferred ingestion workflow is registry-driven:

```text
configs/laws/corpus_registry.yml
→ async crawler (Phase 2)
→ raw artifact storage (data/raw/)
→ metadata.json
→ cleaning/normalization (Phase 4)
→ legal parsing (Phase 5)
→ parent-child chunking (Phase 6)
→ processed JSONL (Phase 7)
→ verification
```

For Phase 1-4, focus only on reliable corpus acquisition, raw storage,
cleaning, and normalization. Phases 1-5 are complete; Phase 6 Parent-child
Chunking is next and consumes `data/interim/{LAW_ID}/hierarchy.json`.

Do not rerun crawling or cleaning unless explicitly requested. Do not jump into
embedding, Qdrant, Neo4j, Advanced RAG, or GraphRAG until Phase 6 chunking and
processed JSONL validation pass.

## Trusted Source

Only crawl:

```text
https://thuvienphapluat.vn
```

Do not crawl other domains unless explicitly approved.

Prefer VBHN documents when available. If no VBHN exists, preserve original law and amendment chronology with effective-date metadata.

## Expected Files (Current Project Layout)

```text
configs/laws/corpus_registry.yml

src/ingestion/crawler.py
src/ingestion/audit.py
src/ingestion/cleaning.py
src/ingestion/cleaning_diagnostics.py
src/ingestion/models.py
src/ingestion/registry.py
src/ingestion/selector.py
src/ingestion/storage.py
src/ingestion/rate_limiter.py
src/services/crawl_service.py
src/services/raw_audit_service.py
src/services/cleaning_service.py
src/services/cleaning_quality_audit_service.py

data/raw/{law_id}/latest/main.html
data/raw/{law_id}/latest/metadata.json
data/interim/{law_id}/normalized.json
data/interim/{law_id}/cleaned.txt

scripts/crawl_raw_corpus.py
scripts/audit_raw_corpus.py
scripts/clean_raw_corpus.py
scripts/audit_cleaning_quality.py

tests/unit/ingestion/
tests/unit/services/test_crawl_service.py
tests/unit/services/test_raw_audit_service.py
tests/unit/services/test_cleaning_service.py
tests/unit/services/test_cleaning_quality_audit_service.py
```

## Corpus Registry

The crawler reads crawl targets from:

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
    domain_tags: ["đất đai", "bất động sản"]
    status: "active"
    source_domain: "thuvienphapluat.vn"
    source_type: "html"          # html | pdf | doc | docx | mixed | unknown
    url: "https://thuvienphapluat.vn/..."
    effective_date: "YYYY-MM-DD"
    expiry_date: null
    crawl_status: "pending"      # pending | crawling | crawled | parsed | ingested | failed | manual_review
    priority: "high"             # critical | high | medium | low
    notes: ""
```

The crawler must support:

- crawl all `pending` laws;
- crawl by tier;
- crawl by group;
- crawl by explicit `law_id`;
- continue after individual target failures;
- report a final crawl summary.

## Raw Storage Contract

Every crawled law is stored under:

```text
data/raw/{law_id}/latest/main.html
data/raw/{law_id}/latest/metadata.json
```

Always save the raw artifact before parsing.

If the legal content is embedded in PDF/DOC/DOCX, save both the landing HTML and the attachment. If attachment parsing is not implemented, mark the target as `manual_review`.

## Metadata Contract

Every law must have:

```text
data/raw/{law_id}/latest/metadata.json
```

Metadata must include:

```text
law_id, name, tier, source_domain, source_type, url
crawl_status, http_status, crawled_at, content_hash
crawler_version, parser_hint, effective_date, expiry_date
attachment_paths, error_message
```

Do not overwrite raw artifacts without traceability or content-hash history.

## Cleaning Output Contract

Every cleaned law produces:

```text
data/interim/{law_id}/normalized.json   # Required: cleaned text + metadata + markers
data/interim/{law_id}/cleaned.txt       # Optional: human-readable debug artifact
```

The `normalized.json` contains: `law_id`, `law_name`, `source_url`, `source_domain`, `source_type`, `raw_artifact_path`, `normalized_text`, `text_stats`, `markers` (article counts, heading metrics), `warnings`, `metadata` (cleaner_version), `candidate_info`.

## Crawler Rules

- Use async I/O (aiohttp or httpx).
- Use conservative rate limiting (default 2 seconds per host).
- Default batch concurrency: 2. Absolute max: 3 unless explicitly approved.
- Use retries with exponential backoff (capped at 30s).
- Use a valid User-Agent (`VnLaw-QA-Crawler/1.0.0`).
- Validate source domain before crawling.
- Store raw HTML before parsing.
- Compute SHA-256 content hash for every raw artifact.
- Record actionable failure metadata.
- Never use `except Exception: pass`.

## OOP and Code Quality Rules

Use clear object-oriented boundaries.

Recommended components:

```text
CrawlTarget                # Pydantic model for registry entries
CrawlResult                # dataclass for crawl outcomes
CrawlSelection             # dataclass for filtered target sets
BaseCrawler                # abstract base crawler
ThuvienPhapLuatCrawler    # TVPL-specific crawler implementation
CorpusRegistryLoader       # YAML registry loader
RawArtifactStore           # file-based raw artifact storage
CrawlTargetSelector        # target filtering logic
RateLimiter                # per-host rate limiting
NormalizedArtifact         # Pydantic model for cleaned output
LegalMarkersSummary        # dataclass for article/clause detection metrics
```

Rules:

- Use Pydantic models at data boundaries.
- Keep crawler, cleaner, parser, chunker, embedder, vector store, and graph store separate.
- Do not create a god class that performs crawling, parsing, embedding, and ingestion together.
- Public classes and functions must have Google-style docstrings.
- Docstrings must explain purpose, args, returns, raises, side effects, and traceability assumptions.

## Commands

Crawl one law for debugging:

```bash
uv run python scripts/crawl_raw_corpus.py \
  --url "https://thuvienphapluat.vn/..." \
  --law-id "LDD_VBHN" \
  --output data/raw
```

Crawl all pending laws:

```bash
uv run python scripts/crawl_raw_corpus.py \
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
uv run python scripts/crawl_raw_corpus.py \
  --registry configs/laws/corpus_registry.yml \
  --law-ids HP_2013 BLDS_2015 LDD_VBHN \
  --output data/raw
```

Audit raw corpus:

```bash
uv run python scripts/audit_raw_corpus.py \
  --registry configs/laws/corpus_registry.yml \
  --raw-dir data/raw \
  --output artifacts/reports/audit/raw_corpus_audit.json
```

Clean and normalize corpus:

```bash
uv run python scripts/clean_raw_corpus.py \
  --raw-dir data/raw \
  --output-dir data/interim \
  --report artifacts/reports/cleaning/cleaning_report.json
```

Optional debug text output:

```bash
uv run python scripts/clean_raw_corpus.py \
  --raw-dir data/raw \
  --output-dir data/interim \
  --report artifacts/reports/cleaning/cleaning_report.json \
  --write-txt
```

Cleaning quality audit:

```bash
uv run python scripts/audit_cleaning_quality.py \
  --interim-dir data/interim \
  --report artifacts/reports/cleaning/cleaning_quality_audit.json
```

## Definition of Done

- [ ] `corpus_registry.yml` exists and contains Phase 1 targets.
- [ ] Batch crawler supports registry-driven crawling.
- [ ] Single-law crawling still works for debugging.
- [ ] Every crawled law has raw artifacts and `metadata.json`.
- [ ] Every raw artifact has a content hash.
- [ ] Failed crawls are traceable and actionable.
- [ ] Attachment-based documents are handled or marked `manual_review`.
- [ ] 52/52 laws cleaned to `normalized.json` with no critical failures.
- [ ] Article markers and legal hierarchy are preserved.
- [ ] Known encoded artifacts (TVPL watermarks) are removed.
- [ ] No arbitrary character splitting is used.
- [ ] Cleaner output is UTF-8 valid.

## Do Not

- Do not crawl unapproved sources.
- Do not hardcode corpus URLs in Python source code.
- Do not parse directly from network responses.
- Do not skip raw source storage.
- Do not suppress crawler/parser errors.
- Do not overwrite raw or interim artifacts without traceability.
- Do not mix crawler, parser, embedding, vector DB, and graph DB logic in one class.
- Do not redo ingestion phases when working on Phase 6 unless a proven
  chunking-blocking source artifact defect is identified.
