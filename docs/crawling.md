# Legal Document Crawling System

## Overview

This document describes the **data crawling pipeline** for the VnLaw-QA system. The crawler fetches legal documents from trusted sources (primarily [thuvienphapluat.vn](https://thuvienphapluat.vn)), stores raw artifacts with metadata, and prepares data for subsequent parsing and ingestion stages.

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
│    Reports    │     │  (HTML, metadata) │     │  (throttle)     │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

## Components

### 1. Corpus Registry (`config/laws/corpus_registry.yml`)

The registry is the **source of truth** for which laws to crawl. Each entry contains:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `law_id` | string | Yes | Unique identifier (e.g., `BLDS_2015`) |
| `name` | string | Yes | Official law name |
| `tier` | integer | Yes | Legal hierarchy (0=Constitution, 1=Core Codes, 2=Laws) |
| `group` | string | Yes | Logical grouping |
| `domain_tags` | list | No | Topic tags for search |
| `status` | enum | No | `active` \| `planned` \| `inactive` \| `amended` \| `replaced` |
| `source_domain` | string | Yes | Must contain `thuvienphapluat.vn` |
| `source_type` | enum | Yes | `html` \| `pdf` \| `doc` \| `docx` \| `mixed` |
| `url` | string | Conditional | URL to crawl (required for `pending` status) |
| `effective_date` | date | No | Format: `YYYY-MM-DD` |
| `expiry_date` | date | No | Format: `YYYY-MM-DD` |
| `crawl_status` | enum | No | `pending` \| `crawled` \| `failed` \| `manual_review` |
| `priority` | enum | No | `critical` \| `high` \| `medium` \| `low` |

**Example Registry Entry:**

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

The selector filters registry entries based on criteria:

**Filter Chain:**

1. **Explicit law_ids** - Filter by specific law identifiers
2. **Tier filter** - Filter by legal hierarchy tier
3. **Group filter** - Filter by group name
4. **Priority filter** - Filter by priority level
5. **Crawl status filter** - Filter by `crawl_status`
6. **Manual review exclusion** - Skip `manual_review` unless `--include-manual-review`
7. **Already-crawled skip** - Skip if `metadata.json` exists with `crawl_status=success`

**Skip Detection Logic:**

A target is skipped if ALL of these are true:
- `data/raw/{law_id}/latest/metadata.json` exists
- `metadata.crawl_status == "success"`
- `metadata.content_hash` is non-empty
- Expected artifact (`main.html` or attachments) exists

### 3. Crawler (`src/ingestion/crawler.py`)

The `ThuvienPhapLuatCrawler` implements async HTTP crawling with:

**Features:**

| Feature | Implementation |
|---------|----------------|
| Async I/O | `httpx.AsyncClient` with `async/await` |
| Retry logic | Exponential backoff: `2^retry_count` seconds, max 30s |
| Rate limiting | Per-host delay + global semaphore |
| Domain validation | All URLs must contain `thuvienphapluat.vn` |
| Timeout | Configurable (default: settings value) |
| Concurrency | Configurable (max: 3) |

**Crawl Flow:**

```
┌─────────────┐
│  Target     │
│  Received   │
└──────┬──────┘
       │
       v
┌─────────────┐
│ Validate    │── X ──> Raise TrustedDomainError
│  Domain     │
└──────┬──────┘
       │
       v
┌─────────────┐
│ Acquire     │
│ Rate Limit  │
└──────┬──────┘
       │
       v
┌─────────────┐     retry_count < max_retries
│   HTTP GET  │─────(timeout/network error)────> Retry
└──────┬──────┘
       │
       v
┌─────────────┐     429
│ Check HTTP  │─────> Wait Retry-After header, retry
│  Status     │
└──────┬──────┘
       │
       v (200 OK)
┌─────────────┐
│  Save HTML  │
│  + Metadata │
└──────┬──────┘
       │
       v
┌─────────────┐
│  Return     │
│  CrawlResult│
└─────────────┘
```

### 4. Rate Limiter (`src/ingestion/rate_limiter.py`)

The `RateLimiter` class provides:

- **Per-host delay**: Minimum delay between requests to the same host (default: 2s)
- **Global concurrency**: Maximum concurrent requests across all hosts (default: 2, max: 3)
- **Thread-safe**: Uses asyncio locks for host tracking

**Usage:**

```python
async with rate_limiter.limit(host):
    response = await client.get(url)
```

### 5. Artifact Storage (`src/ingestion/storage.py`)

The `RawArtifactStore` manages file output:

**Directory Structure:**

```
data/raw/
└── {LAW_ID}/
    ├── latest/
    │   ├── main.html           # Most recent HTML content
    │   └── metadata.json       # Crawl metadata
    │   └── attachments/        # PDF/DOC/DOCX files (if any)
    └── crawls/
        └── {TIMESTAMP}/        # Backups from force refresh
            ├── main.html
            └── metadata.json
```

**Metadata Schema (`metadata.json`):**

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
  "content_hash": "sha256_hex_hash_of_content",
  "crawler_version": "v1.0.0",
  "parser_hint": "tvpl_html",
  "effective_date": null,
  "expiry_date": null
}
```

**Force Refresh Behavior:**

When `--force` is specified:
1. Existing `latest/` directory is moved to `crawls/{TIMESTAMP}/`
2. New crawl saves to fresh `latest/` directory
3. Backup preserved for rollback

## CLI Usage

### Entry Point

```bash
python -m src.ingestion.cli [OPTIONS]
```

### Command Examples

#### Batch Crawl All Pending Laws

```bash
uv run python -m src.ingestion.cli \
  --registry config/laws/corpus_registry.yml \
  --output data/raw \
  --only-status pending \
  --concurrency 2 \
  --delay-seconds 2 \
  --retry 3
```

#### Crawl Specific Laws by ID

```bash
uv run python -m src.ingestion.cli \
  --registry config/laws/corpus_registry.yml \
  --output data/raw \
  --law-ids BLDS_2015 HP_2013 LDD_VBHN
```

#### Filter by Tier and Priority

```bash
uv run python -m src.ingestion.cli \
  --registry config/laws/corpus_registry.yml \
  --output data/raw \
  --tier 1 \
  --priority critical \
  --only-status pending
```

#### Dry Run (No Actual Crawling)

```bash
uv run python -m src.ingestion.cli \
  --registry config/laws/corpus_registry.yml \
  --output data/raw \
  --only-status pending \
  --dry-run
```

#### Force Re-crawl

```bash
uv run python -m src.ingestion.cli \
  --registry config/laws/corpus_registry.yml \
  --output data/raw \
  --law-ids BLDS_2015 \
  --force
```

#### Debug Single URL

```bash
uv run python -m src.ingestion.cli \
  --url "https://thuvienphapluat.vn/van-ban/..." \
  --law-id BLDS_2015 \
  --output data/raw
```

### CLI Options Reference

| Option | Description | Default |
|--------|-------------|---------|
| `--registry PATH` | Path to corpus_registry.yml (batch mode) | required |
| `--url URL` | Single URL for debug mode | - |
| `--law-ids IDS...` | Filter by specific law IDs | - |
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
│ 4. Batch Crawl (run_batch_crawl / crawl_from_registry)          │
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
│    - Total attempted count                                      │
│    - Successful count                                           │
│    - Failed count                                               │
│    - Skipped count                                              │
│    - Duration                                                   │
│    - List of failures with error messages                       │
└─────────────────────────────────────────────────────────────────┘
```

## Testing

### Unit Tests

```bash
# All ingestion tests
uv run pytest tests/unit/ingestion/ -v

# Crawler tests only
uv run pytest tests/unit/ingestion/test_crawler.py -v

# Storage tests only
uv run pytest tests/unit/ingestion/test_storage.py -v

# Rate limiter tests
uv run pytest tests/unit/ingestion/test_rate_limiter.py -v

# With coverage
uv run pytest tests/unit/ingestion/ -v --cov=src/ingestion --cov-report=term-missing
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

### Run Quality Checks

```bash
# Lint
uv run ruff check src tests

# Format
uv run ruff format src tests --check

# Type checking
uv run mypy src

# Tests
uv run pytest tests/unit/ingestion/ -v
```

## Error Handling

### Crawl Failure Categories

| HTTP Status | Behavior |
|-------------|----------|
| 200 OK | Success, save content |
| 429 Too Many Requests | Wait Retry-After, retry |
| 4xx Client Error | Fail immediately, no retry |
| 5xx Server Error | Retry with backoff |
| Timeout | Retry with backoff |
| Network error | Retry with backoff |

### Exceptions

| Exception | When Raised |
|-----------|-------------|
| `TrustedDomainError` | URL domain not in allowed list |
| `RegistryError` | Invalid YAML or registry entry |
| `StorageError` | Failed to write files |

## Monitoring and Logging

### Log Levels

```
INFO    - Crawl started, completed successfully
WARNING - Rate limited, retry attempts, crawl failures
ERROR   - Unexpected errors, storage failures
DEBUG   - Detailed request/response info (with -v)
```

### Structured Logging Format

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

Check:
1. Registry file exists at specified path
2. At least one entry has `crawl_status: pending`
3. Pending entries have `url` field filled
4. Filters aren't too restrictive

### "Domain validation failed"

Check:
1. URL contains `thuvienphapluat.vn`
2. No typos in domain name
3. Using HTTPS (not HTTP)

### "Already crawled" targets skipped

Use `--no-skip-crawled` to force re-crawl, or:
1. Check `data/raw/{law_id}/latest/metadata.json`
2. Use `--force` to backup and re-crawl

### Slow crawling

Adjust:
1. `--concurrency 3` (increase parallel crawls)
2. `--delay-seconds 1` (reduce per-host delay)

## Best Practices

1. **Always run dry-run first** to verify selection
2. **Use `--verbose`** for debugging crawl issues
3. **Set reasonable concurrency** (2-3) to avoid overwhelming the source
4. **Check metadata.json** after crawling to verify success
5. **Keep backups** with `--force` when re-crawling
6. **Monitor logs** for rate limiting (429) responses

## Related Documentation

- [Configuration](../config/README.md)
- [Parsing Pipeline](./parsing.md) (coming soon)
- [RAG Pipeline](../src/retrieval/README.md) (coming soon)