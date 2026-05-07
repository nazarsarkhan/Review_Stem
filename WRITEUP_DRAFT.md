# ReviewStem: A Stem Agent for Pull Request Review

## 1. Abstract
The prompt asks whether an AI agent can start as something minimal, read signals from its environment, and become specific to the task it is facing. I chose pull request review as the task domain because good review is strongly contextual: a SQL diff needs a different reviewer than an admin route, cache update, import flow, or API contract change.

ReviewStem starts as a generic review orchestrator. It reads the diff and repository map, retrieves relevant review guidance, generates specialized reviewer personas, consolidates redundant reviewers, runs draft reviews, performs peer review, edits the final output, and scores the result. If the score is below a target threshold, the reviewer instructions are revised and the loop runs again.

## 2. Approach

### Environmental Signals
The stem agent reads three signals: the active diff, a lightweight repository map, and reusable review guidance from `skills/skills.json`. These inputs determine what the agent should become for the current PR.

### Specialization
The reviewer-selection step creates one to three specialized reviewer personas. For example, a SQL change usually becomes a security-focused SQL reviewer, while an admin route change can become an authorization reviewer. A consolidation step merges overlapping reviewers to avoid redundant work.

### Tools And Safeguards
The draft reviewers can read repository files when the diff is not enough. The final editor removes weak or duplicate findings. The fitness function checks that file paths exist, line references are valid, and obvious fix-quality mistakes are penalized. This is the safeguard layer: if the review is not grounded or actionable enough, the pipeline revises the reviewer instructions instead of blindly accepting the result.

### Stopping Rule
ReviewStem stops when the review reaches `REVIEWSTEM_TARGET_SCORE` or when it hits `REVIEWSTEM_MAX_ITERATIONS`. This makes the loop measurable and bounded.

## 3. Experiments And Results
I added a benchmark command that compares a generic baseline reviewer against the ReviewStem pipeline. The benchmark cases are:

- SQL injection in `src/db/users.ts`
- missing admin authorization in `src/routes/admin.ts`
- stale cache after user update in `src/cache/userCache.ts`

Each case has an expected file, line, severity, and keyword set. The deterministic benchmark scorer checks whether the review is grounded in the expected evidence and avoids hallucinated files.

The intended measurement is:

```bash
reviewstem benchmark --quiet
```

This writes:

- `outputs/benchmark_results.json`
- `outputs/benchmark_results.md`

The important comparison is not just the model's self-score. It is the deterministic benchmark delta between the baseline prompt and the specialized ReviewStem pipeline.

Latest measured run:

| Case | Baseline | ReviewStem | Delta | Notes |
| --- | ---: | ---: | ---: | --- |
| `sql_injection` | 1.00 | 1.00 | +0.00 | Saturated case; both systems catch the obvious injection. |
| `admin_auth` | 0.83 | 1.00 | +0.17 | Specialization improves the authorization finding. |
| `cache_invalidation` | 0.77 | 0.85 | +0.08 | ReviewStem better identifies stale-cache risk. |

The benchmark result supports the core claim: specialization does not matter equally for every task, but it helps on cases where a generic reviewer is less naturally focused.

## 4. What Surprised Me
The final rendering layer mattered more than expected. Rich interpreted `[name]` as markup and hid it from the terminal output, which made a correct SQL fix look broken. Escaping model-generated text became part of the reliability work.

Another surprise was benchmark contamination. The first benchmark files contained comments that revealed the seeded issue. That made the review look better than it really was. Removing those comments made the benchmark more honest.

The mock diff also initially did not match the actual benchmark file. The agent mixed a real finding with a synthetic one, which exposed how important benchmark construction is for evaluating agent behavior.

## 5. What Failed
The first version overused the biological metaphor in user-facing output. It was memorable, but it made the project feel less serious. I moved that language into the conceptual framing and kept the CLI/review output professional.

The model sometimes produced incomplete fix snippets such as `db.query('...', )`. I added prompt constraints and deterministic scoring penalties for that class of issue. This reinforced a key lesson: LLM self-evaluation is useful, but concrete validators are needed for trust.

## 6. What I Would Do With More Time
I would add more benchmark cases, run multiple model seeds, and report confidence intervals. I would also persist successful review guidance after high-scoring runs and retrieve it with a better similarity method than keyword matching.

The next architectural step would be letting the stem agent choose from a larger tool library instead of only repository file reads. For this submission, I kept the tool surface small so the specialization loop and evaluation method stayed clear.

ReviewStem is not a universal agent. It is a stem agent for one class of work: pull request review. Its value is that it becomes specific through a bounded process, then proves it is good enough through measurable fitness checks.
