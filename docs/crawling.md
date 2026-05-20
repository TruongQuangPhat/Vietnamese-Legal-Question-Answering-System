# Legal Document Crawling System

## Overview

This document describes the **data crawling pipeline** for the VnLaw-QA system. The crawler fetches legal documents from trusted sources (primarily [thuvienphapluat.vn](https://thuvienphapluat.vn)), stores raw artifacts with metadata, and prepares data for subsequent parsing and ingestion stages.

## Quick Start

```bash
# Dry run first to verify selection
uv run python -m src.ingestion.cli \
  --registry config/laws/corpus_registry.yml \
  --output data/raw \
  --only-status pending \
  --dry-run

# Then crawl
uv run python -m src.ingestion.cli \
  --registry config/laws/corpus_registry.yml \
  --output data/raw \
  --only-status pending \
  --concurrency 2
```

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  YAML Registry  │────>│  Target Selector │────>│   Crawler Pool  │
│                 │     │  (filters, skip) │     │  (async, retry) │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                          │
                                                          v
┌─────────────────┐     ┌──────────────────┐     ┌────────┴────────┐
│  Data Quality   │<────│  Artifact Store  │<────│  Rate Limiter   │
│    Reports      │     │  (HTML, metadata)│     │  (throttle)     │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

## Components

### 1. Corpus Registry (`config/laws/corpus_registry.yml`)

The registry is the **source of truth** for which laws to crawl.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `law_id` | string | Yes | Unique identifier (e.g., `BLDS_2015`) |
| `name` | string | Yes | Official law name |
| `tier` | integer | Yes | Legal hierarchy (0=Constitution, 1=Core Codes, 2=Laws) |
| `group` | string | Yes | Logical grouping |
| `domain_tags` | list[str] | No | Topic tags for search |
| `status` | LegalStatus | No | `active` \| `planned` \| `inactive` \| `amended` \| `replaced` |
| `source_domain` | string | Yes | Must contain `thuvienphapluat.vn` |
| `source_type` | SourceType | Yes | `html` \| `pdf` \| `doc` \| `docx` \| `mixed` |
| `url` | str | Conditional | URL to crawl (required for `pending`) |
| `effective_date` | str | No | Format: `YYYY-MM-DD` |
| `expiry_date` | str | No | Format: `YYYY-MM-DD` |
| `crawl_status` | CrawlStatus | No | `pending` \| `crawled` \| `failed` \| `manual_review` |
| `priority` | Priority | No | `critical` \| `high` \| `medium` \| `low` |

**Example:**

```yaml
- law_id: "BLDS_2015"
  name: "Bộ luật Dân sự 2015"
  tier: 1
  group: "Bộ luật cốt lõi"
  domain_tags: ["dân sự", "hợp đồng", "tài sản"]
  status: "active"
  source_domain: "thuvienphapluat.vn"
  source_type: "html"
  url: "https://thuvienphapluat.vn/van-ban/Quyen-dan-su/Bo-luat-dan-su-2015-296215.aspx"
  crawl_status: "pending"
  priority: "critical"
```

### 2. Crawl Target Selector (`src/ingestion/selector.py`)

Filters registry entries using composable filters:

**Filter Chain (applied in order):**

1. **law_ids** - Filter by specific law identifiers
2. **tiers** - Filter by legal hierarchy tier
3. **groups** - Filter by group name
4. **priorities** - Filter by priority level
5. **only_statuses** - Filter by crawl status
6. **manual_review exclusion** - Skip unless `--include-manual-review`
7. **already-crawled skip** - Skip if metadata exists with success

**Skip Detection Logic:**

A target is skipped when ALL are true:
- `data/raw/{law_id}/latest/metadata.json` exists
- `metadata.crawl_status == "success"`
- `metadata.content_hash` is non-empty
- Expected artifact (`main.html` or attachments) exists

### 3. Crawler (`src/ingestion/crawler.py`)

`ThuvienPhapLuatCrawler` implements async HTTP crawling:

| Feature | Implementation |
|---------|----------------|
| Async I/O | `httpx.AsyncClient` with `async/await` |
| Retry logic | Exponential backoff: `2^retry_count` seconds, max 30s |
| Rate limiting | Per-host delay + global semaphore |
| Domain validation | All URLs must contain `thuvienphapluat.vn` |
| Timeout | Configurable via `crawler_timeout_seconds` |
| Concurrency | Max 3 concurrent requests |

**Crawl Flow:**

```
Target Received
       │
       v
Validate Domain ──[invalid]──> Raise TrustedDomainError
       │
       v
Acquire Rate Limit
       │
       v
HTTP GET ──[timeout/network]──> Retry with backoff
       │
       v
Check HTTP Status ──[429]──> Wait Retry-After, retry
       │
       v [200 OK]
Save HTML + Metadata
       │
       v
Return CrawlResult
```

### 4. Rate Limiter (`src/ingestion/rate_limiter.py`)

Provides per-host and global concurrency control:

- **Per-host delay**: Minimum delay between requests to same host (default: 2s)
- **Global concurrency**: Max concurrent requests across all hosts (default: 2, max: 3)
- **Thread-safe**: Uses asyncio locks for host tracking

**Usage:**

```python
async with rate_limiter.limit(host):
    response = await client.get(url)
```

### 5. Artifact Storage (`src/ingestion/storage.py`)

Manages raw artifact file output:

**Directory Structure:**

```
data/raw/
└── {LAW_ID}/
    ├── latest/
    │   ├── main.html           # Most recent HTML
    │   ├── metadata.json       # Crawl metadata
    │   └── attachments/        # PDF/DOC/DOCX (if any)
    └── crawls/
        └── {TIMESTAMP}/        # Backups from --force
            ├── main.html
            └── metadata.json
```

**metadata.json Schema:**

```json
{
  "law_id": "BLDS_2015",
  "name": "Bộ luật Dân sự 2015",
  "tier": 1,
  "group": "Bộ luật cốt lõi",
  "source_domain": "thuvienphapluat.vn",
  "source_type": "html",
  "url": "https://thuvienphapluat.vn/...",
  "crawl_status": "success",
  "http_status": 200,
  "crawled_at": "2026-05-18T10:30:00+00:00",
  "content_hash": "sha256_hex_hash",
  "crawler_version": "v1.0.0",
  "parser_hint": "tvpl_html"
}
```

**Force Refresh (`--force`):**

1. Moves `latest/` to `crawls/{TIMESTAMP}/`
2. Saves new crawl to fresh `latest/`
3. Backup preserved for rollback

## CLI Reference

### Entry Point

```bash
python -m src.ingestion.cli [OPTIONS]
```

### Commands

**Batch crawl all pending:**

```bash
uv run python -m src.ingestion.cli \
  --registry config/laws/corpus_registry.yml \
  --output data/raw \
  --only-status pending \
  --concurrency 2 \
  --delay-seconds 2 \
  --retry 3
```

**Crawl specific laws:**

```bash
uv run python -m src.ingestion.cli \
  --registry config/laws/corpus_registry.yml \
  --output data/raw \
  --law-ids BLDS_2015 HP_2013
```

**Filter by tier and priority:**

```bash
uv run python -m src.ingestion.cli \
  --registry config/laws/corpus_registry.yml \
  --output data/raw \
  --tier 1 \
  --priority critical \
  --only-status pending
```

**Dry run (no crawling):**

```bash
uv run python -m src.ingestion.cli \
  --registry config/laws/corpus_registry.yml \
  --output data/raw \
  --only-status pending \
  --dry-run
```

**Force re-crawl:**

```bash
uv run python -m src.ingestion.cli \
  --registry config/laws/corpus_registry.yml \
  --output data/raw \
  --law-ids BLDS_2015 \
  --force
```

**Debug single URL:**

```bash
uv run python -m src.ingestion.cli \
  --url "https://thuvienphapluat.vn/van-ban/..." \
  --law-id BLDS_2015 \
  --output data/raw
```

### Options Table

| Option | Description | Default |
|--------|-------------|---------|
| `--registry PATH` | Path to corpus_registry.yml | required |
| `--url URL` | Single URL for debug mode | - |
| `--law-ids IDS...` | Filter by law IDs | - |
| `--tier N` | Filter by tier (repeatable) | - |
| `--group NAME` | Filter by group (repeatable) | - |
| `--priority LEVEL` | Filter by priority (repeatable) | - |
| `--only-status STATUS` | Filter by crawl status (repeatable) | - |
| `--include-manual-review` | Include manual_review targets | false |
| `--no-skip-crawled` | Don't skip already-crawled | false |
| `--force` | Force re-crawl with backup | false |
| `--dry-run` | Show selection without crawling | false |
| `--concurrency N` | Max concurrent crawls (1-3) | 2 |
| `--delay-seconds N` | Delay between requests per host | 2.0 |
| `--retry N` | Max retry attempts | 3 |
| `--output DIR` | Output directory for artifacts | data/raw |
| `-v, --verbose` | Enable verbose logging | false |

## Pipeline Execution Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. CLI Entry Point (main())                                     │
│    - Parse command line arguments                               │
│    - Configure logging (structlog)                              │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          v
┌─────────────────────────────────────────────────────────────────┐
│ 2. Load Registry (CorpusRegistryLoader)                         │
│    - Read YAML file                                             │
│    - Validate each entry                                        │
│    - Return list of CrawlTarget objects                         │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          v
┌─────────────────────────────────────────────────────────────────┐
│ 3. Select Targets (CrawlTargetSelector)                         │
│    - Apply filters (law_ids, tier, group, priority, status)    │
│    - Skip manual_review (unless --include-manual-review)        │
│    - Skip already-crawled (check metadata.json)                 │
│    - Return CrawlSelection with targets + skip records          │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          v
┌─────────────────────────────────────────────────────────────────┐
│ 4. Batch Crawl (crawl_from_registry)                            │
│    - Create ThuvienPhapLuatCrawler instances                    │
│    - Configure RateLimiter (delay + concurrency)                │
│    - Create asyncio.Semaphore for concurrency control           │
│    - Spawn async tasks for each target                          │
│    - Gather results with return_exceptions=True                 │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          v
┌─────────────────────────────────────────────────────────────────┐
│ 5. Individual Crawl (ThuvienPhapLuatCrawler.crawl())            │
│    - Validate trusted domain                                    │
│    - Apply rate limiting                                        │
│    - HTTP GET with retry (exponential backoff)                  │
│    - Handle 429 (rate limit) with Retry-After header            │
│    - Save HTML + metadata to RawArtifactStore                   │
│    - Return CrawlResult                                         │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          v
┌─────────────────────────────────────────────────────────────────┐
│ 6. Summary Output (print_crawl_summary)                         │
│    - Total attempted, successful, failed, skipped               │
│    - Duration                                                   │
│    - List of failures with error messages                       │
└─────────────────────────────────────────────────────────────────┘
```

## Data Models

### Enum Types

| Enum | Values |
|------|--------|
| `LegalStatus` | `ACTIVE`, `PLANNED`, `INACTIVE`, `AMENDED`, `REPLACED` |
| `CrawlStatus` | `PENDING`, `CRAWLING`, `CRAWLED`, `PARSED`, `INGESTED`, `VERIFIED`, `FAILED`, `MANUAL_REVIEW` |
| `SourceType` | `HTML`, `PDF`, `DOC`, `DOCX`, `MIXED`, `UNKNOWN` |
| `Priority` | `CRITICAL`, `HIGH`, `MEDIUM`, `LOW` |

### Key Classes

| Class | Location | Purpose |
|-------|----------|---------|
| `CrawlTarget` | `src/ingestion/models.py` | Validated registry entry |
| `CrawlResult` | `src/ingestion/models.py` | Crawl success/failure outcome |
| `CrawlSelection` | `src/ingestion/models.py` | Batch selection summary |
| `CrawlSkipRecord` | `src/ingestion/models.py` | Skip reason and metadata |
| `MetadataSchema` | `src/ingestion/models.py` | metadata.json contract |

## Testing

### Run Tests

```bash
# All ingestion tests
uv run pytest tests/unit/ingestion/ -v

# Specific test files
uv run pytest tests/unit/ingestion/test_crawler.py -v
uv run pytest tests/unit/ingestion/test_storage.py -v
uv run pytest tests/unit/ingestion/test_selector.py -v
uv run pytest tests/unit/ingestion/test_registry.py -v
uv run pytest tests/unit/ingestion/test_models.py -v

# With coverage
uv run pytest tests/unit/ingestion/ --cov=src/ingestion --cov-report=term-missing
```

### Test Coverage

| Component | Test File | Coverage |
|-----------|-----------|----------|
| Domain validation | `test_crawler.py` | Trusted domain checks |
| Retry logic | `test_crawler.py` | Timeout, network errors |
| Rate limiting | `test_rate_limiter.py` | Delay enforcement, concurrency |
| HTML saving | `test_storage.py` | Content + metadata |
| Backup creation | `test_storage.py` | Force refresh |
| Selection filters | `test_selector.py` | All filter combinations |
| Registry loading | `test_registry.py` | YAML parsing, validation |
| Models | `test_models.py` | All data classes, enums |

### Quality Checks

```bash
# Lint (auto-fixable issues)
uv run ruff check src tests --fix

# Format
uv run ruff format src tests

# Run tests
uv run pytest tests/unit/ingestion/ -v
```

**Note:** Mypy is currently disabled due to a known issue with hatchling build structure. To run mypy manually:

```bash
uv run mypy --explicit-package-bases src/ingestion src/core
```

## Error Handling

### HTTP Status Handling

| Status | Behavior |
|--------|----------|
| 200 OK | Success, save content |
| 429 Too Many Requests | Wait Retry-After, retry |
| 4xx Client Error | Fail immediately, no retry |
| 5xx Server Error | Retry with backoff |
| Timeout | Retry with backoff |
| Network error | Retry with backoff |

### Custom Exceptions

| Exception | When Raised |
|-----------|-------------|
| `TrustedDomainError` | URL domain not in allowed list |
| `RegistryError` | Invalid YAML or registry entry |
| `StorageError` | Failed to write files |

All exceptions use proper chaining (`raise ... from err`) for traceability.

## Logging

### Log Levels

| Level | When Used |
|-------|-----------|
| INFO | Crawl started, completed successfully |
| WARNING | Rate limited, retry attempts, crawl failures |
| ERROR | Unexpected errors, storage failures |
| DEBUG | Detailed request/response info (`-v` flag) |

### Structured Format (structlog)

```json
{
  "event": "Starting crawl",
  "law_id": "BLDS_2015",
  "url": "https://...",
  "source_type": "html",
  "timestamp": "2026-05-18T10:30:00+00:00"
}
```

## Troubleshooting

### "No targets to crawl"

**Check:**
1. Registry file exists at specified path
2. At least one entry has `crawl_status: pending`
3. Pending entries have `url` field filled
4. Filters aren't too restrictive

**Fix:**
```bash
# Run dry-run to see selection
uv run python -m src.ingestion.cli \
  --registry config/laws/corpus_registry.yml \
  --only-status pending \
  --dry-run

# Or disable skip for already-crawled
uv run python -m src.ingestion.cli \
  --registry config/laws/corpus_registry.yml \
  --no-skip-crawled
```

### "Domain validation failed"

**Check:**
1. URL contains `thuvienphapluat.vn`
2. No typos in domain name
3. Using HTTPS (not HTTP)

**Fix:**
Update URL in registry to match: `https://thuvienphapluat.vn/...`

### "Already crawled" targets skipped

**Fix:**
```bash
# Force re-crawl with backup
uv run python -m src.ingestion.cli \
  --registry config/laws/corpus_registry.yml \
  --law-ids YOUR_LAW_ID \
  --force

# Or disable skip
uv run python -m src.ingestion.cli \
  --registry config/laws/corpus_registry.yml \
  --no-skip-crawled
```

### Slow crawling

**Adjust:**
```bash
# Increase concurrency (max: 3)
--concurrency 3

# Reduce per-host delay
--delay-seconds 1
```

## Best Practices

1. **Always run dry-run first** - Verify selection before actual crawling
2. **Use `--verbose` for debugging** - See detailed logs
3. **Set reasonable concurrency** - Start with 2, max is 3
4. **Check metadata.json** - Verify crawl success after completion
5. **Keep backups** - Use `--force` when re-crawling
6. **Monitor logs for 429** - Rate limiting indicates need to reduce concurrency

## Changelog

### Version 1.1 (Latest)

**Improvements:**
- Fixed `start_time` scoping bug in `crawl_from_registry()`
- Replaced `(str, Enum)` with `StrEnum` for all enum classes
- Added exception chaining (`raise ... from err`) to all error handlers
- Added `--no-skip-crawled` flag to override skip behavior
- Improved CLI output formatting with table display
- Fixed import sorting and code formatting (ruff compliance)
- Added comprehensive documentation (`docs/crawling.md`)

**Files Modified:**
- `src/ingestion/cli.py` - Fixed start_time, improved formatting
- `src/ingestion/models.py` - StrEnum migration
- `src/ingestion/storage.py` - Exception chaining
- `src/ingestion/registry.py` - Exception chaining
- `docs/crawling.md` - New comprehensive documentation

### Version 1.0 (Initial)

- Basic crawling functionality
- Registry-based target selection
- Rate limiting and retry logic
- Artifact storage with metadata
- CLI interface

## Related Documentation

- [Configuration](../config/README.md)
- [Parsing Pipeline](./parsing.md)
- [RAG Pipeline](../src/retrieval/README.md)