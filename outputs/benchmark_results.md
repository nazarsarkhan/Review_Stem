# ReviewStem Benchmark Results

| Case | Generic | Generic+Skills | ReviewStem | Delta vs Generic | Detected? | Calls G/S/RS | Passes | Requires Context |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | --- |
| admin_auth | 1.00 | 1.00 | 1.00 | +0.00 | ✓ | 1/1/14 | 1 | No |

## Scoring Notes

The deterministic scorer uses related files and concept groups rather than exact wording only.
This avoids penalizing correct findings that identify the same root cause through a different but valid file or line.

**Detected?** indicates whether the review identified the core issue with correct severity and sufficient concept coverage,
regardless of whether it cited the exact expected line.

Some cases saturate: the generic baseline already catches the obvious issue. These cases are retained as smoke tests,
while context-required cases evaluate whether ReviewStem's specialization trace and repository-aware review flow
provide additional evidence.
