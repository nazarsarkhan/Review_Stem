# ReviewStem — A Stem Agent for Code Review

**Author:** Nazar Sarkhan · **Date:** 2026-05-12

**v2 pass (this revision):** added multi-seed bootstrap CIs, embeddings
retrieval in the fallback path, +10 benchmark cases, and a second task
domain (dependency-upgrade safety review) that reuses the same pipeline.
The original v1 PR-review results below are kept in place; v2 results live
in §3a and §3b.

---

## 1. Why this task, and why the stem-cell framing maps to it

I picked **pull request review** as the task class for three reasons:

1. **It has clear evaluation signals.** Code review quality reduces to: did the reviewer point at the right file, the right line, with the right severity, and propose a concrete fix? That's deterministically checkable against fixtures — no human-in-the-loop scoring required.
2. **It rewards specialization.** SQL-injection review is a different cognitive shape from cache-coherence review, from authorization-ordering review. A single generalist prompt either misses the subtlety or pads every review with irrelevant checks. This is exactly the shape the brief describes: "a neuron, a muscle fiber, a blood cell — whatever the body needs."
3. **The environment is rich.** A PR comes with a diff, a repo map, and arbitrary files the reviewer can pull on demand. That gives the stem agent real *signals* to read, not just a prompt to react to.

The stem-cell mapping is deliberate, not cosmetic. Each module names one biological function and implements exactly that function:

| Module | Biological role | What it actually does |
|---|---|---|
| `hippocampus.py` | spatial map of environment | walks the repo, returns a bounded file tree |
| `epigenetics.py` | reads inherited signals, expresses traits | term-scores curated + learned skills against the diff |
| `stem_cell.py` | differentiation | asks the LLM to pick 1–3 reviewer personas given the skill mix |
| `motor_cortex.py` | sensorimotor action | runs the draft review with bounded `read_file` tool access |
| `immune_system.py` | filter foreign / faulty material | synthesizes peer reviews, drops vague / off-topic findings |
| `fitness_function.py` | apoptosis signal | applies deterministic penalties (hallucinated file, invalid line, weak fix, …) on top of an LLM grade |
| `mutation_engine.py` | rewrites the genome on failure | regenerates personas with explicit constraints from the evaluator's feedback |
| `skill_evolution.py` | germline memory | promotes high-fitness genomes to persistent skills, tracks usage, prunes underperformers |

A single review is one differentiation event. Across runs, the agent's *gene pool* (its skill catalog) grows from successes and shrinks on failures.

---

## 2. Architecture and the four questions the brief asks

The brief asks four questions. Here are the answers ReviewStem commits to:

**(a) How does it figure out how the task is typically approached?** It doesn't infer this from scratch — that would require an order of magnitude more compute than I had. Instead it starts with a curated `skills/skills.json` (10 skill specs covering security, code quality, performance, and test generation) and grows that catalog from its own successful runs. Each skill is a structured spec: trigger, risk profile, context plan, checklist, test templates. Selection is deterministic weighted term matching (per-field weights from 1.0 to 3.0), so the same diff always picks the same skills — auditable, not vibes-based.

**(b) How does it decide what to become?** Given the top-5 scored skills plus the diff, the `StemCell` asks the LLM to emit 1–3 `ReviewGenome` JSON objects: a persona name, focus areas, specific checks, source skills, and risk profile. This is where the LLM does architectural work — but it's heavily constrained by the structured-output schema and the skill text we feed in. `NeuralPruner` then merges overlapping genomes (e.g., "Security Reviewer" + "SQL Injection Reviewer" collapse).

**(c) How does it rebuild itself without breaking?** Three safeguards. First, **structured output everywhere** — every LLM call goes through `client.beta.chat.completions.parse(response_format=schema)`, so a malformed mutation can't propagate. Second, **deterministic grounding penalties** subtract from any score the LLM-grader gives: hallucinated file (−0.2), out-of-repo path (−0.2), invalid line number (−0.2), incomplete SQL fix (−0.2), vague description (−0.1), missing high-severity fix (−0.1), duplicate finding (−0.05), outside changed files (−0.05). The LLM cannot grade its way past these — they're additive penalties grounded in real filesystem state. Third, **bounded tool use**: `MotorCortex` resolves every `read_file` path inside the repo root and rejects traversal.

**(d) When does it stop?** `target_score` met (default 0.90) or `max_iterations` reached (default 2). Both are configurable per-run. The score history is persisted in `SpecializationState`, so you can see exactly which iteration converged and why.

---

## 3. Experiments and measured before/after

I ran the same 10 benchmark cases through three configurations:

- **Generic baseline** — one general-purpose review prompt, one LLM call.
- **Generic + Skills** — same generic prompt but with the deterministically retrieved skills appended.
- **ReviewStem** — the full pipeline: selection → differentiation → pruning → stress profiles → tool-capable drafts → peer review → synthesis → fitness → mutate-if-needed.

Score is on a 0.0–1.0 scale using deterministic concept-group matching (described in §4 of the README), so it accepts a finding in any file that contributes to the issue, not just the exact expected one.

| Case | Generic | Gen+Skills | ReviewStem | Δ | LLM calls (G/S/RS) |
|---|---:|---:|---:|---:|---:|
| sql_injection | 0.85 | 0.85 | **1.00** | +0.15 | 1 / 1 / 9 |
| admin_auth | 1.00 | 1.00 | 1.00 | 0.00 | 1 / 1 / 14 |
| cache_invalidation | 0.90 | 0.75 | **1.00** | +0.10 | 1 / 1 / 22 |
| route_mounting_auth_bypass | 0.85 | 0.85 | **1.00** | +0.15 | 1 / 1 / 18 |
| cache_key_mismatch | 1.00 | 1.00 | 1.00 | 0.00 | 1 / 1 / 18 |
| async_swallowed_error | 1.00 | 1.00 | 1.00 | 0.00 | 1 / 1 / 8 |
| xss_vulnerability | 0.75 | 0.75 | **0.85** | +0.10 | 1 / 1 / 13 |
| unhandled_promise_rejection | 0.55 | 0.65 | **0.70** | +0.15 | 1 / 1 / 24 |
| missing_auth_tests | 0.80 | 0.80 | **0.90** | +0.10 | 1 / 1 / 17 |
| n_plus_one_query | 0.65 | 0.75 | **0.90** | +0.25 | 1 / 1 / 30 |
| **Mean** | **0.835** | **0.840** | **0.925** | **+0.090** | 1 / 1 / 17.3 |

**Headline:** ReviewStem strictly beats both baselines on 7 of 10 cases, ties on 3, and never loses. Mean improvement over the generic baseline is **+0.09** absolute (≈ 10.8% relative). The hard cases — `n_plus_one_query` (+0.25), `unhandled_promise_rejection` (+0.15), `route_mounting_auth_bypass` (+0.15) — are where specialization actually pays. The easy cases saturate.

**Cost:** ReviewStem uses ~17× more LLM calls than the baseline on average (mean 17.3 vs 1). That's the price of differentiate → review → peer → synthesize → grade, plus a second pass on iterations that don't converge. The trade is "buy +0.09 fitness for 16 extra calls." Whether that's worth it depends on context: for a security gate before merge, yes. For drive-by linting, no.

---

## 3a. v2: multi-seed benchmark, +10 cases, and what survives noise

The v1 numbers above are one run per cell, temperature 0. That's nearly deterministic at the model level but says nothing about whether a +0.10 cell would survive a different seed. The v2 harness (`reviewstem benchmark --seeds 5`) runs each (case, condition) cell across the seed schedule `[(1,0.0),(2,0.2),(3,0.2),(4,0.5),(5,0.5)]` — five seeds mixing deterministic and exploratory temperatures — and reports **mean ± stdev with a 95% percentile bootstrap CI** (2000 resamples, fixed RNG seed for reproducibility). A cell where ReviewStem's CI overlaps the generic baseline's CI is flagged `sig?=no` and explicitly *not* claimed as a win.

The on-disk LLM cache (keyed by `(prompt, schema, temperature, seed)`) makes reruns free, so the seed schedule pays once and amortizes over every later iteration.

I also added **10 new benchmark cases** that break the easy-case saturation of v1 and cover classes the original 10 missed: `csrf_missing_token`, `idor_user_id_in_url`, `jwt_no_verify`, `secret_in_log_line`, `regex_redos`, `unsafe_deserialization`, `open_redirect_param`, `ssti_template_injection`, `missing_rate_limit_login`, `prototype_pollution_lodash`. Each ships with a matching fixture file in `benchmark_repo/` so the fitness existence-check passes. Total: 20 cases.

The actual multi-seed numbers depend on `OPENAI_API_KEY` and a benchmark run; the harness writes them to `outputs/benchmark_multiseed.{json,md}`. The methodology is what's load-bearing here, not the numbers — v1's "+0.09 mean delta" was honest about being single-run, and now there's a way to know which cells survive being seeded differently.

---

## 3b. v2: second domain — dependency-upgrade safety review

The brief says *"for a different class of tasks, you'd start a new stem agent."* v2 ships a second domain — **dependency-upgrade safety review** — that reuses the existing `StemCell → MotorCortex → ImmuneSystem → MutationEngine → NeuralPruner` pipeline unchanged, swapping in:

- **Domain skills:** `reviewstem/domains/dep_upgrade/skills.json` — six skills (CVE detection, major-version breaking change, transitive bloat, license shift, pinning quality, deprecation).
- **Domain fitness:** `DepUpgradeFitness` with grounding checks against OSV.dev. Penalties: `hallucinated_cve` (-0.20), `bad_semver` (-0.10), `non_manifest_file` (-0.10), `vague_finding` (-0.10), `missing_fix_action` (-0.10), `duplicate` (-0.05). A cited CVE that isn't in OSV for any package in the manifest diff is treated the same way as a hallucinated filepath in the PR-review domain.
- **Domain benchmark:** 8 cases mixing pip and npm: `requests_cve_upgrade` (CVE-2023-32681), `lodash_prototype_pollution_fix` (CVE-2019-10744), `numpy_major_bump`, `flask_deprecation`, `event_stream_compromise` (CVE-2018-1000620), `pyyaml_unsafe_load`, `cryptography_breaking` (CVE-2023-49083), `axios_ssrf_upgrade` (CVE-2024-39338).
- **OSV cache fixtures:** the relevant OSV records are committed under `reviewstem/domains/dep_upgrade/osv_fixtures/` so the benchmark is reproducible offline. Live OSV calls happen for any unseen `(pkg, version)` and the result is cached next to the fixtures.

`reviewstem dep-upgrade-review <manifest_diff>` runs a single review; `reviewstem dep-upgrade-benchmark --seeds 5` runs the multi-seed harness against the dep-upgrade suite.

What this demonstrates is the *generality of the stem-cell framing*, not a production-grade CVE tool. The same differentiate → review → synthesize → grade loop works on a class of inputs that has nothing in common with PR diffs — different file types, different vocabulary, different grounding source. That's the part the brief asked for; the absolute scores on this domain are the LLM-grader's opinion of itself again, and the deltas matter more than the levels.

---

## 4. What surprised me

**The "Generic + Skills" baseline barely helps.** Mean 0.840 vs 0.835 — just +0.005 over plain generic. I expected adding the skill text to a single prompt to capture most of the benefit. It didn't. The lift comes from *constructing distinct reviewer personas* with distinct checklists, then forcing them to peer-review each other. Inlining the skill text into one prompt doesn't reproduce that structure — the model averages everything into mush. This was the single strongest signal that the stem-cell framing isn't just a metaphor: differentiation into separate agents matters.

**Deterministic penalties did more work than the LLM grader.** During development I'd see the LLM-grader hand out 0.95s that were obviously wrong (the review cited a nonexistent file). The eight deterministic penalties claw those back to a realistic 0.55. I expected the LLM-grader to dominate; instead it sets a ceiling that the filesystem-grounded penalties cut down to truth. This is the closest thing to the brief's "built-in safeguards pull it back" — and removing them turned the agent into a self-validating hallucinator within two runs.

**One-shot learning is dangerous.** The first version promoted any genome that hit ≥0.85 into the persistent skill catalog. Within five runs the catalog had picked up several near-duplicate "specialists" whose triggers were broad enough to match unrelated diffs — and because term-scoring weights skill name and trigger heavily (3.0×), these learned skills *outranked the curated ones* on future runs. A test I'd written previously even started failing because of state pollution. I fixed it two ways: (a) tests now pass `learned_skills_path=None` to isolate, and (b) I'm adding a candidate-tier so genomes need corroborating successes before promotion (see §6).

**The benchmark scorer is the most important file in the project.** Early scoring used exact-keyword matching against the expected finding. The agent would correctly identify "route mounted before authentication middleware" but score 0 because it said "auth" instead of "authentication." Rewriting the scorer around *related files* and *concept groups* changed the verdict on three cases. The lesson: if your evaluator is brittle, your agent looks bad for the wrong reasons — and you'll spend days "fixing" non-bugs.

**Porting to the dep-upgrade domain forced the *right* abstraction.** I expected the second-domain port to be painful — different file types, different vocabulary, different grounding source. What actually broke was the *scorer*, not the pipeline. The PR-review scorer assumes filesystem grounding; the dep-upgrade scorer needs CVE-id grounding against OSV. The stem-cell pipeline (StemCell → MotorCortex → ImmuneSystem → MutationEngine → NeuralPruner) plugged in unchanged. That's stronger evidence the framing is doing real work than any benchmark delta would be: if the dep-upgrade domain had needed me to refactor `stem_cell.py`, the metaphor would be cosmetic. It didn't.

---

## 5. What failed (or only half-worked)

- **`xss_vulnerability`, `unhandled_promise_rejection`, `missing_auth_tests`** — ReviewStem improves these but doesn't cross the "detected" threshold (concept score ≥ 0.20 AND severity match AND file match). The reviewer finds *something*, often the right something, but doesn't articulate it in language the concept groups match. Either my concept groups are too narrow or the mutation engine isn't pushing the reviewer hard enough on these. I think it's the former — they're three of the four cases I added later, and I never iterated on their concept groups the way I did the originals.
- **Term-matching skill retrieval is shallow.** A diff that mentions `redis` but is actually about cache key namespaces still retrieves the generic "Cache Coherence" skill. Embeddings would catch that — but adding an embedding dependency and a vector index for ten skills felt like over-engineering. With more skills it would justify the cost.
- **LLM-graded fitness is meta-circular.** I'm asking the same model that wrote the review to grade it. The deterministic penalties bound the damage, but the absolute number on the 0–1 scale isn't trustworthy in isolation — only the *delta vs. baseline* on the same scorer is. That's why the writeup leans on relative deltas, not absolute scores.
- **Single-run evaluation.** Each cell in the results table is one run. Temperature is 0 so reruns are nearly deterministic, but model-side nondeterminism (especially the structured-output parser) means a proper evaluation would average ≥3 runs per cell and report confidence intervals. I didn't.
- **Mutation is just persona-rewriting.** Real architectural search would vary the *number* of reviewers, the *tools* they have, the *order* of synthesis. Mine only varies the prompt text. It's enough to recover from "you missed the file" but not enough to discover a fundamentally new review strategy.

---

## 6. What I'd do with more time

In rough order of payoff per hour:

1. **Candidate-tier learning.** Promote a genome to "candidate" on first success, to "learned" only after two corroborating wins on related diffs. Prevents the one-shot pollution failure. **Done in v2** — `skill_evolution.py` thresholds are configurable via `REVIEWSTEM_CANDIDATE_PROMOTIONS` and the candidate tier never participates in retrieval.
2. **Multi-run benchmark with bootstrap CIs.** Five seeds per cell, report mean ± stdev with 95% percentile bootstrap CIs, flag any case whose CI overlaps the baseline as `sig?=no`. **Done in v2** — `reviewstem benchmark --seeds 5`. On-disk LLM cache keyed by `(prompt, schema, temperature, seed)` makes reruns free.
3. **Embeddings retrieval.** Replace the term-scoring weights with a `text-embedding-3-small` index over skill name + trigger + checklist. **Done in v2** — `reviewstem/embeddings.py` with an on-disk JSON cache. Epigenetics now scores `0.7 * (cosine * 10) + 0.3 * term_score` when an embedding provider is available, with graceful fallback to pure term matching when offline.
4. **Hidden benchmark suite.** **Partially done in v2** — added 10 new cases the development loop never trained against (CSRF, IDOR, JWT, ReDoS, SSTI, prototype pollution, etc.) for 20 total. A *fully held-out* set the agent has never seen during any development run is still the right next step.
5. **Second task domain.** **Done in v2** — dep-upgrade safety review (§3b). The pipeline plugged in unchanged.
6. **Architectural mutation.** Let the mutation engine add/remove reviewers and add/remove tools (e.g., a `call_graph` tool, a `test_runner` tool) — not just rewrite prompts. **Still future work** and the single biggest gap between "real evolution" and "prompt rewriting in a structured wrapper."
7. **Real-world PR evaluation.** Pull 20 closed PRs from a public repo, run ReviewStem on each, and compare its findings to the actual review comments that landed. The synthetic benchmark is calibrated by me; the real-world one would calibrate me. **Still future work.**

---

## 7. Closing

The brief asked: *"What if AI agents worked like stem cells?"* The honest answer this project gives is: **the differentiation step works, the safeguards work, persistent learning works, and the framing generalizes to a second task class — but evolution is still mostly LLM prompting in a structured wrapper, not true architectural search.** v1 showed +0.09 mean improvement over the generic baseline with single-run measurement; v2 replaces that with multi-seed bootstrap CIs so future claims of improvement come with a `sig?` flag attached. The agent figured out how to *select among human-written specs*, *grow that set from its own wins*, *port the pipeline to a different domain unchanged*, and *flag its own claims as significant or noise*. It still didn't figure out the approach from scratch — that's the next horizon.

The full audit trail for every run is in `outputs/specialization_state*.json` — selected skills with their match terms (now including semantic cosine scores when embeddings are available), the genomes before and after pruning, every `read_file` call, every deterministic penalty (now including OSV-backed CVE checks in the dep-upgrade domain), every mutation delta. The agent is auditable end-to-end. Whatever else it is, it isn't a black box.
