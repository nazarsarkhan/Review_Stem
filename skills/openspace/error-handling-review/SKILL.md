---
name: error-handling-review
description: Use when a PR modifies error handling, async operations, resource management, or error response logic.
trigger: Use when a PR modifies error handling, async operations, resource management, or error response logic.
tags:
- quality
- error-handling
- async
- review
backends:
- shell
- mcp
version: 1.0.0
lineage:
  origin: manual
  generation: 1
  parent_skill_id: null
  change_summary: Created for comprehensive quality detection
quality_metrics:
  total_selections: 0
  total_applied: 0
  total_completions: 0
  success_rate: 0.0
source_case: async_swallowed_error

---

# Error Handling Review

## Risk Profile

- Swallowed errors (empty catch blocks, ignored promise rejections)
- Information disclosure in error messages (stack traces, DB schema, file paths)
- Missing error boundaries in React/frontend code
- Unhandled promise rejections causing server crashes
- Resource leaks on error paths (unclosed files, DB connections, sockets)
- Error messages exposing sensitive data to clients
- Missing global error handlers for uncaught exceptions
- Async operations without timeout or cancellation

## Context Plan

1. Find all error handling blocks (`try/catch`, `.catch()`, `.then(null, handler)`, error middleware)
2. Check if errors are logged with sufficient context AND propagated appropriately
3. Verify sensitive data (stack traces, internal paths, DB details) is not exposed in client responses
4. Ensure resources (files, connections, streams) are cleaned up in `finally` blocks or equivalent
5. Check for global error handlers (`process.on('unhandledRejection')`, error boundaries)

## Checklist

- [ ] Do catch blocks propagate errors or handle them meaningfully (not just log and continue)?
- [ ] Are error messages sanitized before sending to client (no stack traces, internal paths)?
- [ ] Are all async operations protected with `.catch()` or `try/catch`?
- [ ] Are resources (files, DB connections, sockets) closed in `finally` blocks?
- [ ] Is there a global error handler for unhandled rejections and uncaught exceptions?
- [ ] Do error responses use appropriate HTTP status codes (400, 401, 403, 404, 500)?
- [ ] Are errors logged with sufficient context (user ID, request ID, timestamp)?
- [ ] Do long-running async operations have timeouts?

## Test Templates

- Thrown error is caught, logged with context, and propagated to caller
- Error response does not contain stack trace or internal file paths
- Failed async operation triggers error handler and doesn't crash process
- Resource (file handle, DB connection) is closed even when operation fails
- Unhandled promise rejection is caught by global handler
- Error log includes request ID and user context for debugging
- Async operation times out after configured duration
