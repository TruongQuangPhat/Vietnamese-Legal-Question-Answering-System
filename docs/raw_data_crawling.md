# Raw Data Crawling Phase

## 1. Purpose

The Raw Data Crawling phase downloads Vietnamese legal source documents from
the trusted corpus registry and stores them as immutable raw artifacts.

This phase is intentionally narrow. It only answers:

```text
Which legal documents should be fetched?
Where are the trusted source URLs?
How do we fetch them politely and reliably?
How do we store raw evidence for later phases?
```

It does **not** decide whether the HTML contains the correct legal body, does
not clean website content, does not normalize text, does not parse legal
hierarchy, and does not create retrieval chunks.

## 2. Phase Position

```text
┌──────────────────────────────┐
│ Phase 1                      │
│ Legal Corpus Registry        │
│ configs/laws/corpus_registry  │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Phase 2                      │
│ Raw Data Crawling            │
│ data/raw/{LAW_ID}/latest/    │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Phase 3                      │
│ Raw Corpus Audit             │
│ validate raw artifacts       │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Phase 4                      │
│ Cleaning & Normalization     │
│ data/interim/*/normalized    │
└──────────────────────────────┘
```

Phase 2 depends on Phase 1 because it reads crawl targets from the registry.
Phase 3 depends on Phase 2 because it validates the produced raw artifacts.

## 3. Goals

Phase 2 goals:

- Load the approved legal corpus from `configs/laws/corpus_registry.yml`.
- Select crawl targets using filters such as law ID, tier, group, priority, and
  crawl status.
- Validate that each target URL belongs to the trusted source domain.
- Fetch raw HTML from `thuvienphapluat.vn` with bounded concurrency and retry
  handling.
- Save the raw HTML as `data/raw/{LAW_ID}/latest/main.html`.
- Save crawl metadata as `data/raw/{LAW_ID}/latest/metadata.json`.
- Preserve raw artifacts as legal evidence for all downstream phases.

Non-goals:

- Do not audit content quality.
- Do not remove website boilerplate.
- Do not normalize Unicode or whitespace.
- Do not trim legal body starts.
- Do not parse `Điều`, clauses, or points.
- Do not chunk, embed, or index.
- Do not mutate existing raw artifacts outside controlled refresh behavior.

## 4. Main Files

| File | Role |
|---|---|
| `scripts/crawl_raw_corpus.py` | CLI entrypoint and argument parsing |
| `src/services/crawl_service.py` | Pipeline orchestration |
| `src/ingestion/registry.py` | Registry loading and validation |
| `src/ingestion/selector.py` | Target filtering and skip detection |
| `src/ingestion/crawler.py` | Trusted-domain HTTP crawler |
| `src/ingestion/rate_limiter.py` | Per-host delay and concurrency guard |
| `src/ingestion/storage.py` | Raw artifact and metadata persistence |
| `src/ingestion/models.py` | `CrawlTarget`, `CrawlResult`, metadata models |
| `src/ingestion/exceptions.py` | Domain/storage/registry exceptions |
| `tests/unit/ingestion/test_crawler.py` | Crawler behavior tests |
| `tests/unit/ingestion/test_selector.py` | Target selection tests |
| `tests/unit/ingestion/test_registry.py` | Registry loading tests |
| `tests/unit/ingestion/test_storage.py` | Raw artifact storage tests |

## 5. User-Facing Commands

Dry run before any crawl:

```bash
uv run python scripts/crawl_raw_corpus.py \
  --registry configs/laws/corpus_registry.yml \
  --output data/raw \
  --only-status pending \
  --dry-run
```

Actual batch crawl:

```bash
uv run python scripts/crawl_raw_corpus.py \
  --registry configs/laws/corpus_registry.yml \
  --output data/raw \
  --only-status pending \
  --concurrency 2
```

Targeted crawl:

```bash
uv run python scripts/crawl_raw_corpus.py \
  --registry configs/laws/corpus_registry.yml \
  --output data/raw \
  --law-ids BLDS_2015 HP_2013
```

Debug one URL:

```bash
uv run python scripts/crawl_raw_corpus.py \
  --url "https://thuvienphapluat.vn/van-ban/..." \
  --law-id BLDS_2015 \
  --output data/raw
```

Inspect CLI options:

```bash
uv run python scripts/crawl_raw_corpus.py --help
```

## 6. CLI Options

| Option | Purpose |
|---|---|
| `--registry` | Load crawl targets from the YAML registry |
| `--url` | Crawl a single URL in debug mode |
| `--law-id` | Required with `--url` |
| `--law-ids` | Select specific registry law IDs |
| `--tier` | Filter by legal tier |
| `--group` | Filter by registry group |
| `--priority` | Filter by priority |
| `--only-status` | Filter by crawl lifecycle status |
| `--include-manual-review` | Include targets marked for manual review |
| `--no-skip-crawled` | Attempt already-crawled targets |
| `--force` | Expose force refresh mode for targeted re-crawls |
| `--dry-run` | Show target selection without network calls |
| `--concurrency` | Maximum concurrent crawl tasks, capped at 3 |
| `--delay-seconds` | Per-host delay between requests |
| `--retry` | Maximum retry attempts |
| `--output` | Raw artifact output directory |
| `--verbose` | Enable verbose logging |

## 7. High-Level Architecture

```text
┌────────────────────────────────────────────┐
│ scripts/crawl_raw_corpus.py                │
│ CLI: argparse, console output, exit code   │
└────────────────────┬───────────────────────┘
                     │ builds CrawlPipelineConfig
                     ▼
┌────────────────────────────────────────────┐
│ src/services/crawl_service.py              │
│ Orchestrates mode, registry loading,       │
│ target selection, workers, and summary     │
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│ src/ingestion/registry.py                  │
│ Loads corpus_registry.yml into             │
│ validated CrawlTarget objects              │
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│ src/ingestion/selector.py                  │
│ Applies filters and skip rules             │
└────────────────────┬───────────────────────┘
                     │ selected targets
                     ▼
┌────────────────────────────────────────────┐
│ src/ingestion/crawler.py                   │
│ Trusted-domain validation, HTTP fetch,     │
│ retry handling, content hashing            │
└────────────────────┬───────────────────────┘
                     │ uses
                     ▼
┌────────────────────────────────────────────┐
│ src/ingestion/rate_limiter.py              │
│ Per-host delay + global concurrency guard  │
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│ src/ingestion/storage.py                   │
│ Writes main.html and metadata.json         │
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│ data/raw/{LAW_ID}/latest/                  │
│ Immutable raw legal evidence               │
└────────────────────────────────────────────┘
```

## 8. Registry Batch Pipeline

```text
┌────────────────────────────────────────────┐
│ 1. Parse CLI arguments                     │
│ mode: --registry                           │
│ filters: law_ids/tier/group/priority/status│
│ behavior: dry_run/concurrency/retry/output │
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│ 2. Build CrawlPipelineConfig               │
│ Pure config object passed into service     │
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│ 3. Load registry                           │
│ CorpusRegistryLoader -> list[CrawlTarget]  │
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│ 4. Select targets                          │
│ CrawlTargetSelector filters and records    │
│ skip reasons                               │
└────────────────────┬───────────────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
        ▼                         ▼
┌──────────────────────┐   ┌────────────────────────────┐
│ dry_run == true      │   │ dry_run == false           │
│ print target table   │   │ create Store, RateLimiter, │
│ no network request   │   │ and Crawler                │
└──────────────────────┘   └──────────────┬─────────────┘
                                           │
                                           ▼
┌────────────────────────────────────────────┐
│ 5. Crawl selected targets                  │
│ asyncio.gather + semaphore                 │
│ max concurrency capped at 3                │
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│ 6. Store raw artifacts                     │
│ main.html + metadata.json                  │
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│ 7. Print crawl summary                     │
│ attempted / successful / failed / skipped  │
└────────────────────────────────────────────┘
```

## 9. Single URL Debug Pipeline

```text
┌────────────────────────────────────────────┐
│ --url + --law-id                           │
│ Build temporary CrawlTarget                │
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│ Validate trusted domain                    │
│ hostname must contain thuvienphapluat.vn   │
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│ Crawl exactly one target                   │
│ max_concurrency = 1                        │
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│ Save under data/raw/{LAW_ID}/latest/       │
└────────────────────────────────────────────┘
```

## 10. Target Selection

Selection starts from all registry entries:

```text
all registry targets
→ law_ids filter, if provided
→ tiers filter, if provided
→ groups filter, if provided
→ priorities filter, if provided
→ only_statuses filter, if provided
→ remove manual_review unless --include-manual-review
→ skip already-crawled targets unless --no-skip-crawled
→ CrawlSelection
```

Already-crawled detection uses disk metadata as the primary source of truth:

```text
data/raw/{LAW_ID}/latest/metadata.json exists
metadata.crawl_status == "success"
metadata.content_hash exists
expected artifact exists
```

This is safer than trusting only the registry status because the registry can
be out of sync with local raw artifacts.

Selection output:

```text
┌────────────────────────────────────────────┐
│ CrawlSelection                             │
├────────────────────────────────────────────┤
│ targets: selected CrawlTarget list         │
│ total_available: registry target count     │
│ selected_count: count after filters        │
│ skipped_count: skipped target count        │
│ skip_reasons: reason -> count              │
│ dry_run: bool                              │
└────────────────────────────────────────────┘
```

## 11. Crawl Execution Logic

`ThuvienPhapLuatCrawler` handles the single-target crawl.

```text
┌────────────────────────────────────────────┐
│ CrawlTarget                                │
│ law_id, name, source_domain, source_type,  │
│ url, tier, group, priority, dates          │
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│ Validate trusted domain                    │
│ hostname must contain thuvienphapluat.vn   │
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│ Extract host and enter RateLimiter         │
│ per-host delay + concurrency guard         │
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│ HTTP GET with redirects                    │
│ User-Agent: VnLaw-QA-Crawler/1.0.0         │
└────────────────────┬───────────────────────┘
                     │
       ┌─────────────┼─────────────────────┐
       │             │                     │
       ▼             ▼                     ▼
┌────────────┐ ┌──────────────┐ ┌──────────────────────┐
│ 200 OK     │ │ 429 response │ │ timeout/network error│
│ read bytes │ │ wait header  │ │ retry                │
└─────┬──────┘ └──────┬───────┘ └──────────┬───────────┘
      │               │                    │
      ▼               └──────────┬─────────┘
┌────────────────────────────────▼───────────┐
│ retry loop until success or max retries     │
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│ Compute SHA-256 content hash               │
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│ RawArtifactStore.save_html()               │
│ write main.html and metadata.json          │
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│ CrawlResult                                │
│ success, http_status, duration, hash/error │
└────────────────────────────────────────────┘
```

## 12. Rate Limiting and Concurrency

The crawler uses two levels of request control:

```text
┌────────────────────────────────────────────┐
│ Service-level semaphore                    │
│ bounds concurrent crawl tasks              │
│ configured by --concurrency, capped at 3   │
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│ RateLimiter                                │
│ enforces per-host delay and max concurrency│
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│ HTTP request                               │
└────────────────────────────────────────────┘
```

This protects the trusted legal source from aggressive request bursts.

## 13. Error Handling

| Condition | Behavior |
|---|---|
| Untrusted domain | return trusted-domain failure |
| Missing `--law-id` in URL mode | CLI exits with error |
| HTTP `200` | read content and store artifacts |
| HTTP `429` | wait `Retry-After`, then retry |
| Other HTTP status | mark crawl failed with `HTTP <status>` |
| Timeout | retry until retry budget is exhausted |
| Network request error | retry until retry budget is exhausted |
| Unexpected error | log exception details and return failed result |
| Save failure | crawl result becomes failed even if content was fetched |

## 14. Raw Artifact Layout

```text
data/raw/
└── {LAW_ID}/
    ├── latest/
    │   ├── main.html
    │   └── metadata.json
    └── crawls/
        └── {TIMESTAMP}/
            ├── main.html
            └── metadata.json
```

`latest/` is the active raw snapshot consumed by audit and cleaning.
Timestamped `crawls/{TIMESTAMP}/` directories are reserved for refresh and
backup workflows.

## 15. metadata.json

Raw metadata is legal traceability evidence. Later phases should read it, but
should not rewrite it.

Important fields:

```text
┌────────────────────────────────────────────┐
│ metadata.json                              │
├────────────────────────────────────────────┤
│ law_id                                     │
│ name                                       │
│ tier                                       │
│ group                                      │
│ source_domain                              │
│ source_type                                │
│ url                                        │
│ crawl_status                               │
│ http_status                                │
│ crawled_at                                 │
│ content_hash                               │
│ crawler_version                            │
│ parser_hint                                │
│ effective_date / expiry_date               │
└────────────────────────────────────────────┘
```

Downstream usage:

```text
metadata.json
→ Raw Corpus Audit source validation
→ Cleaning & Normalization traceability
→ normalized.json source fields
→ future hierarchy/chunk metadata
→ final legal citation provenance
```

## 16. Output Summary

After a registry crawl, the CLI prints:

```text
┌────────────────────────────────────────────┐
│ Crawl Execution Summary                    │
├────────────────────────────────────────────┤
│ Total attempted                            │
│ Successful                                 │
│ Failed                                     │
│ Skipped                                    │
│ Duration                                   │
│ Failed law IDs with error messages         │
│ Skipped law IDs with skip reasons          │
└────────────────────────────────────────────┘
```

Meaning:

- `failed`: a selected target was attempted and did not produce a valid stored
  artifact.
- `skipped`: the selector intentionally did not crawl a target, usually because
  local disk metadata already proved a successful crawl.

## 17. Current Result

Final Phase 2 corpus state:

```text
registry entries:        52
latest/main.html files:  52
latest/metadata.json:    52
trusted source domain:   thuvienphapluat.vn
downstream raw mutation: none
```

## 18. Validation Gate

The crawling phase passes when:

- each registry law has a raw artifact directory;
- successful crawls have `main.html` and `metadata.json`;
- content hashes are recorded;
- source metadata points back to `thuvienphapluat.vn`;
- no downstream phase mutates raw artifacts.

Phase 2 has passed this gate.

## 19. Tests

Relevant tests:

```bash
uv run pytest tests/unit/ingestion/test_crawler.py -v
uv run pytest tests/unit/ingestion/test_selector.py -v
uv run pytest tests/unit/ingestion/test_registry.py -v
uv run pytest tests/unit/ingestion/test_storage.py -v
uv run pytest tests/unit/ingestion -q
```

Test coverage focuses on:

- trusted domain validation;
- retry and error handling;
- rate limiter behavior;
- registry loading;
- target filtering and skip records;
- artifact storage;
- metadata writing;
- backup behavior in storage.

## 20. Handoff to Phase 3

Phase 2 hands off raw artifacts to Raw Corpus Audit:

```text
data/raw/{LAW_ID}/latest/main.html
data/raw/{LAW_ID}/latest/metadata.json
→ scripts/audit_raw_corpus.py
→ data/reports/raw_corpus_audit.json
```

The audit phase verifies that raw artifacts are complete, readable, trusted,
and suitable for Cleaning & Normalization.
