---
name: low-context-pr-triage-and-repository-validation
description: Use when PR review input lacks a real diff, changed-file context, repository
  metadata, title, description, or uses placeholder/mock content.
trigger: Use when PR review input lacks a real diff, changed-file context, repository
  metadata, title, description, or uses placeholder/mock content.
tags:
- review
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
  success_rate: 0.84
source_case: low_context

---

# Low-Context PR Triage and Repository Validation

## Risk Profile

- Missing diff prevents semantic review
- Placeholder diff can cause speculative findings
- Missing changed files blocks impact analysis
- Missing PR metadata obscures intended behavior
- Repository extraction failures can create misleading review conditions

## Context Plan

1. Validate whether the diff is real and the changed files are accessible
2. Request PR title, description, changed files, and file contents when missing
3. Avoid file-specific findings until concrete source evidence is available
4. Defer correctness, security, performance, and test assessment until source context exists

## Checklist

- [ ] Is there a real unified diff with changed files?
- [ ] Are changed files accessible in the repository?
- [ ] Is PR intent described by title, description, or equivalent metadata?
- [ ] Are review limitations explicitly stated instead of inventing findings?
- [ ] Is the minimum missing context requested?

## Test Templates

- Placeholder or empty diffs produce triage-only review output
- Missing file context suppresses code-specific findings
- Repository access failures are surfaced as process blockers
