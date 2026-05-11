---
name: admin-route-authentication-authorization-review
description: Use when a PR modifies admin or privileged backend/API routes, route
  mounting, middleware ordering, or authorization behavior.
trigger: Use when a PR modifies admin or privileged backend/API routes, route mounting,
  middleware ordering, or authorization behavior.
tags:
- admin
- auth
- security
- review
- authorization
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
  success_rate: 0.88
source_case: admin_auth

---

# Admin Route Authentication/Authorization Review

## Risk Profile

- Missing authentication on privileged routes
- Missing admin authorization checks
- Privilege escalation through inconsistent role checks
- Middleware ordering that leaves handlers reachable before auth
- Route mounting bypass through alternate unprotected paths
- Missing 401 and 403 regression tests

## Context Plan

1. Inspect changed route handlers for authentication and role checks
2. Read router mounting or application setup files when route protection may be applied outside the handler
3. Compare with established protected-route patterns elsewhere in the repository
4. Check middleware order and alternate mount paths before assuming global protection applies
5. Review tests for unauthenticated, non-admin, and admin outcomes

## Checklist

- [ ] Is authentication enforced before the privileged handler runs?
- [ ] Is admin or equivalent role authorization enforced after authentication?
- [ ] Could route mounting or middleware order expose the route through an unprotected path?
- [ ] Are all methods and subroutes covered by the same protection?
- [ ] Are negative-path tests present for 401 and 403 behavior?

## Test Templates

- Unauthenticated requests to the admin endpoint are denied
- Authenticated non-admin requests to the admin endpoint are denied
- Authenticated admin requests succeed
- Alternate mount paths and HTTP methods cannot bypass middleware
