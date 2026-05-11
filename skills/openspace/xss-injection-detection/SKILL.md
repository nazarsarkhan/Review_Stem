---
name: xss-injection-detection
description: Use when a PR modifies user input handling, HTML rendering, template engines, file path operations, or shell command execution.
trigger: Use when a PR modifies user input handling, HTML rendering, template engines, file path operations, or shell command execution.
tags:
- security
- xss
- injection
- review
backends:
- shell
- mcp
version: 1.0.0
lineage:
  origin: manual
  generation: 1
  parent_skill_id: null
  change_summary: Created for comprehensive security detection
quality_metrics:
  total_selections: 0
  total_applied: 0
  total_completions: 0
  success_rate: 0.0
source_case: xss_vulnerability

---

# XSS and Injection Detection

## Risk Profile

- Cross-Site Scripting (XSS): reflected, stored, DOM-based
- HTML injection through unsanitized user input
- Template injection with unsafe interpolation
- Command injection via shell execution with user input
- Path traversal through unvalidated file paths
- LDAP injection, XML injection, NoSQL injection
- Missing Content-Security-Policy headers
- Unsafe use of `innerHTML`, `dangerouslySetInnerHTML`, `eval()`

## Context Plan

1. Identify all user-controlled inputs (request params, query strings, headers, cookies, form data)
2. Trace data flow from input to output contexts (HTML rendering, templates, shell commands, file operations)
3. Check for sanitization, escaping, or validation at each output boundary
4. Compare with existing XSS/injection prevention patterns in the repository
5. Verify Content-Security-Policy and other security headers are set

## Checklist

- [ ] Are user inputs escaped before HTML rendering (e.g., `escapeHtml()`, auto-escaping templates)?
- [ ] Does template engine use safe interpolation (e.g., `{{ }}` not `{{{ }}}` in Handlebars)?
- [ ] Are file paths validated against directory traversal patterns (`../`, absolute paths)?
- [ ] Are shell commands parameterized or input strictly validated with allowlists?
- [ ] Is `innerHTML`, `dangerouslySetInnerHTML`, or `eval()` avoided with user input?
- [ ] Is Content-Security-Policy header configured to prevent inline scripts?
- [ ] Are URL parameters validated before use in redirects or href attributes?
- [ ] Are database queries parameterized (covered by sql-injection skill, but check NoSQL)?

## Test Templates

- Input containing `<script>alert(1)</script>` is escaped as `&lt;script&gt;alert(1)&lt;/script&gt;` in HTML output
- Path traversal attempt `../../etc/passwd` is rejected or normalized to safe path
- Template injection payload `{{7*7}}` or `${7*7}` is treated as literal text, not evaluated
- Shell command with input `; rm -rf /` is rejected or safely parameterized
- XSS via event handler `<img src=x onerror=alert(1)>` is sanitized
- Content-Security-Policy header blocks inline script execution
