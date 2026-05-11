# ReviewStem Benchmark Results

| Case | Generic | Generic+Skills | ReviewStem | Delta vs Generic | Detected? | Calls G/S/RS | Passes | Requires Context |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | --- |
| sql_injection | 0.85 | 0.85 | 1.00 | +0.15 | ✓ | 1/1/9 | 1 | No |
| admin_auth | 1.00 | 1.00 | 1.00 | +0.00 | ✓ | 1/1/14 | 1 | No |
| cache_invalidation | 0.90 | 0.75 | 1.00 | +0.10 | ✓ | 1/1/22 | 2 | No |
| route_mounting_auth_bypass | 0.85 | 0.85 | 1.00 | +0.15 | ✓ | 1/1/18 | 2 | Yes |
| cache_key_mismatch | 1.00 | 1.00 | 1.00 | +0.00 | ✓ | 1/1/18 | 2 | Yes |
| async_swallowed_error | 1.00 | 1.00 | 1.00 | +0.00 | ✓ | 1/1/8 | 1 | Yes |
| xss_vulnerability | 0.75 | 0.75 | 0.85 | +0.10 | ✗ | 1/1/13 | 1 | No |
| unhandled_promise_rejection | 0.55 | 0.65 | 0.70 | +0.15 | ✗ | 1/1/24 | 2 | No |
| missing_auth_tests | 0.80 | 0.80 | 0.90 | +0.10 | ✗ | 1/1/17 | 2 | No |
| n_plus_one_query | 0.65 | 0.75 | 0.90 | +0.25 | ✓ | 1/1/30 | 2 | No |

## Scoring Notes

The deterministic scorer uses related files and concept groups rather than exact wording only.
This avoids penalizing correct findings that identify the same root cause through a different but valid file or line.

**Detected?** indicates whether the review identified the core issue with correct severity and sufficient concept coverage,
regardless of whether it cited the exact expected line.

Some cases saturate: the generic baseline already catches the obvious issue. These cases are retained as smoke tests,
while context-required cases evaluate whether ReviewStem's specialization trace and repository-aware review flow
provide additional evidence.
