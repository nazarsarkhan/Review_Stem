---
name: cache-invalidation-audit-for-update-path-stale-read-bugs
description: Use when a PR changes cache behavior, cached reads, mutation paths, update
  flows, or cache key construction.
trigger: Use when a PR changes cache behavior, cached reads, mutation paths, update
  flows, or cache key construction.
tags:
- review
- cache
- security
backends:
- shell
- mcp
version: 1.0.0
lineage:
  origin: manual
  generation: 1
  parent_skill_id: null
  change_summary: Migrated from skills.json
quality_metrics:
  total_selections: 0
  total_applied: 0
  total_completions: 0
  success_rate: 0.9
source_case: cache_invalidation

---

# Cache Invalidation Audit for Update-Path Stale-Read Bugs

## Risk Profile

- Stale cache after successful update
- Read and write cache key mismatch
- Missing invalidation after mutation
- Asymmetric create, update, and delete cache behavior
- Missing read-update-read regression tests

## Context Plan

1. Trace read-path cache key construction and update-path invalidation key construction
2. Verify every successful update invalidates, refreshes, or overwrites the exact key later served by reads
3. Compare create, update, and delete behavior for cache coherence symmetry
4. Read surrounding cache helpers when the diff only shows one side of the read/write flow

## Checklist

- [ ] Does the update path invalidate or refresh the same key used by cached reads?
- [ ] Can a read immediately after update return stale pre-update data?
- [ ] Are create, update, and delete paths consistent in cache handling?
- [ ] Do error and retry branches avoid mixed stale state?
- [ ] Is there a read-update-read regression test?

## Test Templates

- Cache a record, update it, then read again and assert the updated value is returned
- Verify the invalidation key exactly matches the read cache key
- Repeated updates followed by reads always return the latest persisted value
