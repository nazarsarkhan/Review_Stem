---
name: backend-api-swallowed-error-review
description: Use when a PR modifies backend/API route handlers, import/process endpoints,
  try/catch blocks, async control flow, promise handling, or response emission.
trigger: Use when a PR modifies backend/API route handlers, import/process endpoints,
  try/catch blocks, async control flow, promise handling, or response emission.
tags:
- review
- error-handling
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
source_case: async_swallowed_error

---

# Backend API Swallowed Error Review

## Risk Profile

- Caught exceptions ignored
- Async errors not awaited or returned
- False 2xx success response after failure
- Logging without propagation
- Partial side effects before failure
- Missing negative-path tests

## Context Plan

1. Trace route control flow from request validation through response emission
2. Inspect try/catch blocks and promise chains for swallowed failures
3. Verify caught errors return non-2xx responses, rethrow, or call error middleware
4. Check whether async work is awaited before success is sent
5. Review tests for thrown and rejected downstream failures

## Checklist

- [ ] Can execution continue to a success response after a caught exception?
- [ ] Are downstream async operations awaited or returned?
- [ ] Is logging used in addition to propagation rather than as a substitute?
- [ ] Do partial side effects have explicit failure semantics?
- [ ] Are negative-path tests present for thrown and rejected failures?

## Test Templates

- The route returns a non-2xx response when the service throws
- The route does not emit success before required async work completes
- Rejected promises are propagated to error handling
- Caught failures are logged and still represented in the HTTP response
