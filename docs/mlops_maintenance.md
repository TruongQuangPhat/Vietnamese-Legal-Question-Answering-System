# MLOps & Corpus Maintenance

## Overview

The MLOps & Corpus Maintenance phase defines how VnLaw-QA keeps its legal corpus, processed data, retrieval indexes, evaluation baselines, and production services reliable over time. Unlike a static RAG demo, a legal QA system must assume that laws can be amended, consolidated, replaced, expired, or reinterpreted through newer legal documents. Therefore, maintenance is not a secondary task; it is part of the core reliability model of the system.

This phase is implemented after the data pipeline, retrieval pipeline, evaluation suite, and API deployment are stable. Its role is to make corpus updates reproducible, measurable, reversible, and safe.

The main objectives are:

- keep the corpus registry as the source of truth;
- recrawl and reprocess legal documents in a controlled way;
- version raw artifacts, processed JSONL files, embeddings, indexes, and evaluation reports;
- detect regressions before deploying a new index or model;
- monitor retrieval quality, citation accuracy, unsupported-answer rate, and system latency;
- support rollback when a corpus update, index refresh, or model change degrades quality.

MLOps for VnLaw-QA is not only about model deployment. It is also about **legal corpus governance**.

## Quick Start

**Intended maintenance workflow** (design phase, not yet implemented):

```bash
# 1. Update the corpus registry after reviewing legal source changes
git checkout -b maintenance/corpus-refresh-YYYYMMDD

# 2. Dry-run the crawl selection
uv run python scripts/crawl_raw_corpus.py \
  --registry config/laws/corpus_registry.yml \
  --output data/raw \
  --only-status pending \
  --dry-run

# 3. Recrawl selected legal documents
uv run python scripts/crawl_raw_corpus.py \
  --registry config/laws/corpus_registry.yml \
  --output data/raw \
  --only-status pending \
  --concurrency 2 \
  --delay-seconds 2 \
  --retry 3

# 4. Run raw corpus audit
uv run python scripts/audit_raw_corpus.py \
  --registry config/laws/corpus_registry.yml \
  --raw-dir data/raw \
  --output data/reports/raw_corpus_audit.json

# 5. Re-run downstream processing after audit passes
uv run python scripts/process_legal_corpus.py \
  --registry config/laws/corpus_registry.yml \
  --raw-dir data/raw \
  --processed-dir data/processed

# 6. Rebuild or refresh indexes
uv run python scripts/build_index.py \
  --processed-dir data/processed \
  --collection vnlaw_qa_chunks

# 7. Run regression evaluation
uv run python scripts/evaluate_rag.py \
  --golden data/eval/golden_qa.jsonl \
  --output data/eval/reports/regression_report.json
```

**Expected maintenance outputs**:

- updated `config/laws/corpus_registry.yml`;
- versioned raw artifacts;
- versioned processed JSONL;
- refreshed vector index;
- optional refreshed graph index;
- regression evaluation report;
- deployment decision: promote, hold, or rollback.

## Architecture

```
┌────────────────────────────────────────────┐
│        Registry Update / Source Review     │
│        config/laws/corpus_registry.yml     │
└───────────────┬────────────────────────────┘
                │
                ▼
┌────────────────────────────┐
│  Controlled Recrawling     │
│  (dry-run, filters, retry) │
└───────────────┬────────────┘
                │
                ▼
┌────────────────────────────┐
│  Versioned Raw Artifacts   │
│  data/raw/{law_id}/latest  │
│  data/raw/{law_id}/crawls  │
└───────────────┬────────────┘
                │
                ▼
┌────────────────────────────┐
│  Raw Corpus Audit          │
│  completeness + quality    │
└───────────────┬────────────┘
                │
                ▼
┌────────────────────────────┐
│  Reprocessing Pipeline     │
│  clean → parse → chunk     │
└───────────────┬────────────┘
                │
                ▼
┌────────────────────────────┐
│  Processed Data Versioning │
│  data/processed/{version}  │
└───────────────┬────────────┘
                │
                ▼
┌────────────────────────────┐
│  Embedding / Index Refresh │
│  Qdrant + optional Neo4j   │
└───────────────┬────────────┘
                │
                ▼
┌────────────────────────────┐
│  Regression Evaluation     │
│  retrieval + citation + QA │
└───────────────┬────────────┘
                │
                ▼
┌────────────────────────────┐
│  Deployment Gate           │
│  promote / hold / rollback │
└───────────────┬────────────┘
                │
                ▼
┌────────────────────────────┐
│  Production Monitoring     │
│  quality + latency + drift │
└────────────────────────────┘
```

## Components

### 1. Corpus Update Workflow

**Goal**: Update the legal corpus safely when a new law, amended document, VBHN version, or replacement document becomes available.

**Responsibilities**:

- review legal sources before changing the registry;
- add or update entries in `config/laws/corpus_registry.yml`;
- preserve `law_id` stability unless the legal document truly represents a new source;
- update lifecycle fields such as `status`, `crawl_status`, `effective_date`, `expiry_date`, and `notes`;
- document why a corpus change was made.

**Typical update cases**:

| Case | Example | Expected Action |
|------|---------|-----------------|
| New law added | A new sectoral law becomes relevant | Add a new registry entry |
| VBHN replaces older source | New consolidated version appears | Update URL and notes, preserve relationship in metadata |
| Law amended | Effective articles change | Update metadata and plan reprocessing |
| Law expired/replaced | Old law no longer applies | Mark `status` as `replaced` or `inactive` |
| URL changed | Source website changes URL | Update `url`, run dry-run and recrawl |

**Important principle**: the registry must remain the source of truth. A raw artifact or index entry should not exist without a corresponding registry entry.

### 2. Recrawling Strategy

**Goal**: Refresh raw legal artifacts without corrupting or overwriting previous crawl evidence.

**Strategy**:

- always run a dry-run before crawling;
- recrawl only selected entries unless a full corpus refresh is intended;
- preserve previous raw artifacts when forcing a refresh;
- maintain metadata for crawl time, source URL, content hash, HTTP status, and crawler version.

**Recommended recrawl modes**:

| Mode | Purpose | Example |
|------|---------|---------|
| Targeted recrawl | Refresh one law | `--law-ids LDD_2024` |
| Status-based recrawl | Crawl pending entries | `--only-status pending` |
| Priority refresh | Refresh high-value laws | `--priority critical` |
| Forced recrawl | Replace latest artifact with backup | `--force` |
| Full refresh | Rebuild corpus snapshot | Scheduled maintenance window |

**Expected raw artifact layout**:

```text
data/raw/
└── {LAW_ID}/
    ├── latest/
    │   ├── main.html
    │   ├── metadata.json
    │   └── attachments/
    └── crawls/
        └── {TIMESTAMP}/
            ├── main.html
            └── metadata.json
```

### 3. Versioned Raw Artifacts

**Goal**: Keep raw legal sources reproducible and auditable.

Raw artifacts are legal evidence for downstream processing. If a parser bug is found, the system must be able to reproduce the processed output from the same raw input. If a source page changes, the system must preserve the previous snapshot.

**Recommended metadata fields**:

- `law_id`
- `name`
- `url`
- `source_domain`
- `source_type`
- `crawl_status`
- `http_status`
- `crawled_at`
- `content_hash`
- `crawler_version`
- `registry_version`
- `raw_snapshot_id`

**Raw artifact governance rules**:

- never mutate old snapshots;
- write new snapshots instead of editing old files;
- compute content hashes for change detection;
- store crawl metadata next to the artifact;
- keep a pointer from processed output back to raw artifact path.

### 4. Processed Data Versioning

**Goal**: Track which raw corpus, parser version, cleaner version, and chunker version produced each processed JSONL output.

Processed data is the input to embedding/indexing. If the chunk schema changes, all downstream embeddings may need to be regenerated.

**Recommended processed layout**:

```text
data/processed/
├── latest/
│   ├── BLDS_2015.jsonl
│   ├── LDD_2024.jsonl
│   └── manifest.json
└── versions/
    └── v2026-05-21/
        ├── BLDS_2015.jsonl
        ├── LDD_2024.jsonl
        └── manifest.json
```

**Manifest example**:

```json
{
  "processed_version": "v2026-05-21",
  "created_at": "2026-05-21T10:30:00Z",
  "registry_hash": "sha256...",
  "raw_snapshot_id": "raw-2026-05-21",
  "cleaner_version": "v0.1",
  "parser_version": "v0.1",
  "chunker_version": "v0.1",
  "total_laws": 52,
  "total_chunks": 12345,
  "schema_version": "processed-jsonl-v0.1"
}
```

**Versioning triggers**:

- corpus registry changes;
- raw artifact content hash changes;
- cleaning rules change;
- parser rules change;
- chunk schema changes;
- citation construction changes;
- effective-date metadata changes.

### 5. Embedding and Index Refresh

**Goal**: Keep retrieval indexes synchronized with processed JSONL.

Index refresh must be deterministic. Every vector point should trace back to one processed chunk and one legal source.

**Refresh strategies**:

| Strategy | When to Use | Trade-off |
|----------|-------------|-----------|
| Full reindex | Schema/model changes | Safest, slower |
| Incremental upsert | New or changed chunks | Faster, requires reliable diffing |
| Shadow index | Production-safe migration | More storage, safer rollout |
| Blue-green index | Switch between two collections | Enables rollback |

**Recommended Qdrant collection strategy**:

```text
vnlaw_qa_chunks_v2026_05_21   # new candidate collection
vnlaw_qa_chunks_current       # alias or active collection
vnlaw_qa_chunks_previous      # rollback target
```

**Index validation checks**:

- vector count equals processed chunk count;
- every vector payload contains `chunk_id`, `law_id`, `citation`, and `source_url`;
- random sample retrieval returns expected fields;
- metadata filters work for `law_id`, `effective_date`, and legal status;
- collection alias points to the intended version.

### 6. Regression Evaluation

**Goal**: Prevent quality degradation when data, index, retrieval logic, prompts, or model settings change.

Regression evaluation should run before promoting a new corpus or index version.

**Evaluation layers**:

- **Parser regression**: article/clause/point extraction should not degrade.
- **Chunk regression**: no missing citations, no duplicate chunk IDs.
- **Retrieval regression**: expected articles/clauses should appear in top-k.
- **Generation regression**: answers should remain faithful to retrieved context.
- **Citation regression**: answer citations must match retrieved chunks.
- **Fallback regression**: unsupported questions should trigger fallback.

**Recommended report**:

```json
{
  "evaluation_version": "eval-2026-05-21",
  "processed_version": "v2026-05-21",
  "index_version": "qdrant-v2026-05-21",
  "metrics": {
    "article_recall_at_5": 0.94,
    "clause_recall_at_10": 0.91,
    "citation_exact_match": 0.97,
    "faithfulness": 0.92,
    "unsupported_claim_rate": 0.03,
    "fallback_precision": 0.95,
    "fallback_recall": 0.90,
    "latency_p95_ms": 1800
  },
  "decision": "promote"
}
```

**Promotion policy example**:

- promote if all required metrics pass;
- hold if retrieval/citation metrics degrade;
- rollback if unsupported-claim rate increases beyond threshold;
- require manual review for legal-critical regressions.

### 7. CI/CD Gates

**Goal**: Automate checks while keeping high-risk legal changes reviewable.

**Recommended CI stages**:

```text
┌──────────────────────┐
│  Lint / Format       │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│  Unit Tests          │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│  Corpus Audit        │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│  Processed JSONL     │
│  Validation          │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│  Retrieval Smoke     │
│  Tests               │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│  Regression Eval     │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│  Deployment Gate     │
└──────────────────────┘
```

**Suggested CI commands**:

```bash
uv run ruff check .
uv run pytest tests/unit -v
uv run python scripts/audit_raw_corpus.py \
  --registry config/laws/corpus_registry.yml \
  --raw-dir data/raw \
  --output data/reports/raw_corpus_audit.json
uv run python scripts/validate_processed_jsonl.py \
  --processed-dir data/processed
uv run python scripts/evaluate_retrieval.py \
  --golden data/eval/golden_qa.jsonl
```

### 8. Monitoring and Observability

**Goal**: Detect operational and quality issues after deployment.

MLOps monitoring for Legal RAG must include both system metrics and legal-quality metrics.

**System metrics**:

- API request count;
- latency p50/p95/p99;
- error rate;
- timeout rate;
- Qdrant query latency;
- Neo4j query latency;
- LLM latency and error rate;
- token usage and cost;
- cache hit rate.

**Quality metrics**:

- retrieval empty-result rate;
- average retrieval confidence;
- citation validation failure rate;
- unsupported-answer rate;
- fallback rate;
- top retrieved law distribution;
- query categories with low confidence;
- effective-date filter usage;
- user feedback rate.

**Alert examples**:

| Alert | Condition | Response |
|-------|-----------|----------|
| High unsupported-answer rate | > 5% over 1 hour | Inspect retrieval logs and prompts |
| Citation failure spike | > 2% over 30 minutes | Disable new index or rollback |
| Retrieval empty-rate spike | > 10% over 1 hour | Check Qdrant collection/alias |
| LLM timeout spike | > 5% over 15 minutes | Switch model or increase timeout |
| Latency p95 breach | > SLA for 10 minutes | Scale service or inspect dependencies |

### 9. Rollback Strategy

**Goal**: Recover quickly when an update degrades correctness, latency, or citation reliability.

Rollback should be possible at multiple layers:

| Layer | Rollback Method |
|-------|-----------------|
| Raw corpus | Restore previous raw snapshot |
| Processed JSONL | Repoint `latest/` to previous processed version |
| Vector index | Switch Qdrant alias to previous collection |
| Graph index | Restore Neo4j dump or use previous graph version |
| Prompt/model config | Revert config version |
| API image | Roll back Docker/Kubernetes deployment |

**Blue-green index rollback**:

```text
vnlaw_qa_chunks_previous  ← stable old collection
vnlaw_qa_chunks_candidate ← new collection under evaluation
vnlaw_qa_chunks_current   ← alias used by API
```

If evaluation fails:

```bash
# Intended example, exact command depends on vector store client
uv run python scripts/switch_index_alias.py \
  --alias vnlaw_qa_chunks_current \
  --target vnlaw_qa_chunks_previous
```

**Rollback policy**:

- prefer index alias switch over deleting data;
- never overwrite old processed artifacts without backup;
- keep evaluation reports for both failed and promoted versions;
- document rollback cause in the maintenance log.

### 10. Maintenance Runbook

**Goal**: Provide a repeatable operating procedure for corpus and index refresh.

**Monthly maintenance checklist**:

1. Review registry entries and legal source changes.
2. Identify laws needing recrawl or metadata update.
3. Create a maintenance branch.
4. Run crawler dry-run.
5. Recrawl selected entries.
6. Run raw corpus audit.
7. Reprocess affected laws.
8. Validate processed JSONL.
9. Re-embed changed chunks.
10. Refresh vector index.
11. Run regression evaluation.
12. Promote or hold the new index.
13. Update changelog and maintenance notes.
14. Monitor production quality metrics after promotion.

**Emergency maintenance checklist**:

1. Identify failing component: corpus, parser, index, retriever, generator, API.
2. Disable risky feature if possible.
3. Switch index alias to previous stable version if retrieval/citation quality degraded.
4. Roll back API image if runtime errors increased.
5. Run targeted regression tests.
6. Write incident notes and follow-up action items.

## Pipeline Execution Flow

1. **Source review**:
   - Review `corpus_registry.yml`, legal source URLs, effective dates, status, and notes.
   - Identify entries requiring recrawl or metadata update.

2. **Recrawl planning**:
   - Run dry-run selection.
   - Confirm target law IDs and expected artifact updates.
   - Choose targeted, priority-based, or full refresh mode.

3. **Raw refresh**:
   - Recrawl selected entries.
   - Preserve old snapshots if force-refreshing.
   - Write metadata and content hashes.

4. **Audit gate**:
   - Run raw corpus audit.
   - Reject artifacts with missing HTML, invalid metadata, error pages, unreadable text, or suspicious legal markers.

5. **Processing refresh**:
   - Clean, normalize, parse, and chunk affected laws.
   - Write processed JSONL with versioned manifest.

6. **Index refresh**:
   - Generate embeddings for new/changed chunks.
   - Upsert into candidate collection or build a shadow index.
   - Validate vector count, payload fields, and metadata filters.

7. **Regression evaluation**:
   - Run retrieval, citation, generation, fallback, and latency metrics.
   - Compare against previous stable baseline.

8. **Deployment decision**:
   - Promote if metrics pass.
   - Hold for manual review if legal-critical metrics are ambiguous.
   - Roll back if quality or latency degrades.

9. **Monitoring**:
   - Watch production metrics after promotion.
   - Trigger alerts on quality degradation, citation failure spikes, or latency breaches.

## Data Models / Output Schema

### Maintenance Manifest

```json
{
  "maintenance_id": "maint-2026-05-21",
  "created_at": "2026-05-21T10:30:00Z",
  "reason": "scheduled monthly corpus refresh",
  "registry_hash_before": "sha256...",
  "registry_hash_after": "sha256...",
  "affected_law_ids": ["LDD_2024", "BLDS_2015"],
  "raw_snapshot_id": "raw-2026-05-21",
  "processed_version": "processed-v2026-05-21",
  "index_version": "qdrant-v2026-05-21",
  "evaluation_report": "data/eval/reports/eval-2026-05-21.json",
  "decision": "promote",
  "notes": "All validation gates passed."
}
```

### Corpus Version Manifest

```json
{
  "corpus_version": "corpus-v2026-05-21",
  "registry_entries": 52,
  "raw_snapshot_id": "raw-2026-05-21",
  "processed_version": "processed-v2026-05-21",
  "index_version": "qdrant-v2026-05-21",
  "created_at": "2026-05-21T10:30:00Z",
  "created_by": "maintenance_pipeline",
  "status": "promoted"
}
```

### Index Version Manifest

```json
{
  "index_version": "qdrant-v2026-05-21",
  "collection_name": "vnlaw_qa_chunks_v2026_05_21",
  "active_alias": "vnlaw_qa_chunks_current",
  "embedding_model": "BAAI/bge-m3",
  "embedding_dimension": 1024,
  "processed_version": "processed-v2026-05-21",
  "total_vectors": 12345,
  "created_at": "2026-05-21T10:30:00Z",
  "status": "candidate"
}
```

### Monitoring Event

```json
{
  "event_type": "citation_validation_failure",
  "timestamp": "2026-05-21T10:35:12Z",
  "query_id": "query-abc123",
  "index_version": "qdrant-v2026-05-21",
  "processed_version": "processed-v2026-05-21",
  "retrieved_chunk_ids": ["LDD_2024__article_123__clause_2"],
  "severity": "warning",
  "action": "sample_for_review"
}
```

## CLI Reference

### Corpus Refresh

```bash
# Dry-run recrawl selection
uv run python scripts/crawl_raw_corpus.py \
  --registry config/laws/corpus_registry.yml \
  --output data/raw \
  --only-status pending \
  --dry-run

# Recrawl selected laws
uv run python scripts/crawl_raw_corpus.py \
  --registry config/laws/corpus_registry.yml \
  --output data/raw \
  --law-ids LDD_2024 BLDS_2015 \
  --concurrency 2 \
  --delay-seconds 2 \
  --retry 3
```

### Validation and Processing

```bash
# Raw corpus audit
uv run python scripts/audit_raw_corpus.py \
  --registry config/laws/corpus_registry.yml \
  --raw-dir data/raw \
  --output data/reports/raw_corpus_audit.json

# Processed JSONL validation
uv run python scripts/validate_processed_jsonl.py \
  --processed-dir data/processed \
  --output data/reports/processed_validation.json
```

### Index and Evaluation

```bash
# Build or refresh index
uv run python scripts/build_index.py \
  --processed-dir data/processed \
  --collection vnlaw_qa_chunks_candidate

# Run regression evaluation
uv run python scripts/evaluate_rag.py \
  --golden data/eval/golden_qa.jsonl \
  --output data/eval/reports/regression_report.json
```

### Rollback

```bash
# Switch active vector index alias to a previous collection
uv run python scripts/switch_index_alias.py \
  --alias vnlaw_qa_chunks_current \
  --target vnlaw_qa_chunks_previous

# Roll back API deployment
kubectl rollout undo deployment/vnlaw-qa
```

## Testing

**Unit tests**:

- `test_registry_hash_changes_when_registry_updates()`
- `test_processed_manifest_contains_required_versions()`
- `test_index_manifest_vector_count_matches_processed_chunks()`
- `test_maintenance_manifest_records_decision()`
- `test_monitoring_event_schema()`

**Integration tests**:

- simulate a small corpus refresh from registry update to processed JSONL validation;
- build a temporary candidate index and verify payload fields;
- switch index alias in a test environment;
- run a small regression evaluation set and compare metrics.

**Regression tests**:

- run golden QA queries against previous and candidate indexes;
- compare retrieval recall, citation exact match, fallback precision/recall, and latency;
- fail the deployment gate if candidate metrics fall below thresholds.

**Operational tests**:

- test rollback script on staging;
- test health checks after index switch;
- test alert rules with synthetic metric spikes.

## Error Handling

- **Registry update error**: reject invalid YAML, duplicate `law_id`, missing URL, or invalid status transition.
- **Recrawl failure**: mark affected `law_id` as failed; preserve previous raw snapshot.
- **Raw audit failure**: block reprocessing for invalid artifacts.
- **Processing failure**: keep previous processed version active; write failure report.
- **Index refresh failure**: do not switch active alias; keep previous collection active.
- **Regression failure**: hold candidate version for manual review; do not promote.
- **Monitoring spike**: trigger alert; sample affected queries; consider rollback.
- **Rollback failure**: escalate and restore from previous stable artifacts or backups.

All maintenance actions should write structured logs with `maintenance_id`, `corpus_version`, `processed_version`, and `index_version`.

## Troubleshooting

| Issue | Possible Cause | How to Check | Recommended Fix |
|-------|----------------|--------------|-----------------|
| Registry hash changed unexpectedly | Manual edit, formatting change, unreviewed source update | Compare git diff and registry hash | Review change, update manifest, rerun dry-run |
| Recrawl returns fewer artifacts than expected | Filter too narrow, skip logic, failed requests | Check crawl summary and skip records | Adjust filters, use targeted law IDs, retry failed laws |
| Raw audit fails after recrawl | Error page, missing metadata, encoding issue | Inspect audit report | Fix crawler, retry recrawl, or restore previous raw snapshot |
| Processed chunk count drops sharply | Parser or cleaner regression | Compare processed manifests | Revert parser/cleaner change or inspect affected laws |
| Vector count does not match chunks | Embedding job failed or skipped chunks | Compare index manifest and processed manifest | Re-run embedding for missing chunks |
| Retrieval quality drops after index refresh | New embeddings, bad metadata, alias mismatch | Run regression evaluation and sample queries | Roll back alias, inspect candidate index |
| Citation failures increase | Chunk citation fields changed or context packing bug | Monitor citation validator logs | Revalidate processed JSONL, fix citation builder |
| Fallback rate increases | Retrieval recall drop or stricter confidence threshold | Compare fallback metrics | Tune threshold, inspect retrieval results |
| Latency increases after deployment | Larger index, slower LLM, cache disabled | Check p95 metrics by component | Enable cache, optimize filters, scale services |
| Rollback does not restore quality | Wrong alias target or old index corrupted | Check active index manifest | Restore from backup or rebuild previous version |

## Best Practices

- **Keep registry changes reviewable** — every corpus update should be visible in git diff.
- **Never mutate old raw snapshots** — create a new snapshot for every meaningful source change.
- **Run audit before processing** — invalid raw artifacts should never reach parser/chunker stages.
- **Version every major artifact** — raw corpus, processed JSONL, vector index, graph index, prompts, and evaluation reports.
- **Use shadow indexes for risky changes** — build candidate collections before switching production aliases.
- **Prefer deterministic gates** — schema validation, vector count checks, and citation checks should run before LLM-based evaluation.
- **Evaluate before promotion** — retrieval and citation metrics must pass before new indexes serve traffic.
- **Keep rollback simple** — index alias switching should be fast and tested.
- **Monitor legal-quality metrics** — unsupported-answer rate and citation failures are more important than generic accuracy alone.
- **Document every maintenance run** — record reason, affected laws, versions, metrics, decision, and rollback plan.
- **Do not log sensitive user questions** — legal queries may contain private facts; use query hashes or sampled redacted logs.
- **Treat effective dates as first-class metadata** — index updates must not serve expired or replaced provisions as current law.

## Changelog

### Version 0.1 (2026-05-21)

- Created initial MLOps & corpus maintenance documentation.
- Defined corpus update workflow, recrawling strategy, versioned artifacts, processed data versioning, and index refresh policy.
- Added regression evaluation gates and promotion/rollback policy.
- Documented monitoring metrics for system health and Legal RAG quality.
- Added maintenance manifests, corpus version manifests, index version manifests, and monitoring event schema.
- Included CLI examples, testing strategy, troubleshooting guide, and best practices.

## Related Documentation

| Document | Status | Description |
|----------|--------|-------------|
| `docs/end_to_end_pipeline.md` | Existing | High-level project pipeline and phase roadmap |
| `docs/crawling.md` | Existing | Registry-driven crawling implementation |
| `docs/project_setup.md` | Existing | Environment setup and development principles |
| `docs/corpus_registry.md` | Existing | Corpus registry schema and lifecycle |
| `docs/raw_corpus_audit.md` | Designed | Raw artifact audit and validation |
| `docs/cleaning_normalization.md` | Planned | HTML-to-text extraction and normalization |
| `docs/legal_parsing.md` | Planned | Legal hierarchy parsing into Phần/Chương/Mục/Điều/Khoản/Điểm |
| `docs/parent_child_chunking.md` | Planned | Parent-child chunking and citation construction |
| `docs/processed_jsonl.md` | Planned | Processed JSONL schema and validation |
| `docs/embedding_indexing.md` | Future extension | Embedding generation and vector indexing |
| `docs/naive_rag.md` | Future extension | Baseline RAG pipeline |
| `docs/advanced_rag.md` | Future extension | Hybrid retrieval, reranking, and time-aware filtering |
| `docs/graphrag_agents.md` | Future extension | GraphRAG and agent orchestration |
| `docs/evaluation.md` | Future extension | Evaluation metrics, golden QA, and regression gates |
| `docs/api_deployment.md` | Future extension | FastAPI service and deployment strategy |
