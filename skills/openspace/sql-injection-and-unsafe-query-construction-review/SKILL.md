---
name: sql-injection-and-unsafe-query-construction-review
description: Use when a PR modifies database access, raw SQL, query construction,
  search/filter/login endpoints, or user-controlled values in queries.
trigger: Use when a PR modifies database access, raw SQL, query construction, search/filter/login
  endpoints, or user-controlled values in queries.
tags:
- review
- sql
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
source_case: sql_injection

---

# SQL Injection and Unsafe Query Construction Review

## Risk Profile

- SQL injection through unsafe interpolation
- Missing parameter binding for user-controlled values
- Escaping or string formatting mistaken for parameterization
- Sensitive data exposure through overly broad query behavior
- Query construction that changes semantics for special characters

## Context Plan

1. Inspect changed database access code and identify all user-controlled values that reach a query
2. Compare unsafe string construction with existing parameterized query patterns in the repository
3. Check whether the suggested fix binds every dynamic value through placeholders or query builder parameters
4. Look for search, filter, login, and lookup paths where attacker-controlled input can affect SQL structure

## Checklist

- [ ] Does any SQL string interpolate request, route, form, or function parameters directly?
- [ ] Are placeholders paired with complete argument arrays or query-builder bindings?
- [ ] Does the fix avoid manual escaping as the primary defense?
- [ ] Could wildcard, quote, comment, or boolean payloads alter query semantics?
- [ ] Are tests proposed for malicious input and normal lookup behavior?

## Test Templates

- A lookup containing quotes or SQL comment syntax is treated as data and does not alter the query structure
- The repository database mock verifies that user input is passed as a bound parameter
- Normal search/filter behavior still returns expected records after parameterization
