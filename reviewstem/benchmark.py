import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

from .schemas import CodeComment, ReviewOutput


@dataclass(frozen=True)
class BenchmarkCase:
    """A deterministic review benchmark case."""

    case_id: str
    title: str
    diff: str
    expected_filepath: str
    expected_line: int
    expected_severity: str
    required_keywords: tuple[str, ...]
    requires_context: bool = False
    related_files: tuple[str, ...] = ()
    concept_groups: tuple[tuple[str, ...], ...] = ()
    line_tolerance: int = 1


@dataclass(frozen=True)
class BenchmarkScore:
    """Deterministic benchmark score for one review output."""

    case_id: str
    score: float
    matched_filepath: bool
    matched_line: bool
    matched_severity: bool
    keyword_total: int
    hallucinated_files: int
    notes: str
    requires_context: bool = False
    issue_detected: bool = False
    grounding_score: float = 0.0
    concept_score: float = 0.0
    severity_score: float = 0.0


BENCHMARK_CASES = {
    "sql_injection": BenchmarkCase(
        case_id="sql_injection",
        title="Unsafe SQL interpolation in user lookup",
        expected_filepath="src/db/users.ts",
        expected_line=4,
        expected_severity="High",
        required_keywords=("sql injection", "parameter", "name"),
        diff="""diff --git a/src/db/users.ts b/src/db/users.ts
index 1234567..89abcdef 100644
--- a/src/db/users.ts
+++ b/src/db/users.ts
@@ -1,6 +1,6 @@
 import { db } from './connection';

 export async function getUserByName(name: string) {
-    const result = await db.query('SELECT * FROM users WHERE name = $1', [name]);
+    const result = await db.query(`SELECT * FROM users WHERE name = '${name}'`);
     return result[0];
 }""",
    ),
    "admin_auth": BenchmarkCase(
        case_id="admin_auth",
        title="Admin stats route without authorization",
        expected_filepath="src/routes/admin.ts",
        expected_line=4,
        expected_severity="High",
        required_keywords=("admin", "authorization", "middleware"),
        related_files=("src/index.ts", "src/routes/admin.ts", "src/middleware/auth.ts"),
        concept_groups=(
            ("auth", "authentication", "requireAuth", "unauthenticated", "401"),
            ("authorization", "admin", "requireAdmin", "privilege", "403"),
            ("route", "router", "mount", "middleware", "internal/admin", "/admin"),
            ("bypass", "public", "unprotected", "exposed", "non-admin", "before"),
        ),
        diff="""diff --git a/src/routes/admin.ts b/src/routes/admin.ts
index 1234567..89abcdef 100644
--- a/src/routes/admin.ts
+++ b/src/routes/admin.ts
@@ -1,5 +1,7 @@
 import express from 'express';
 const router = express.Router();

+router.get('/stats', (req, res) => {
+    res.json({ totalUsers: 1000, revenue: 50000 });
+});
 export default router;""",
    ),
    "cache_invalidation": BenchmarkCase(
        case_id="cache_invalidation",
        title="User update leaves stale cache entry",
        expected_filepath="src/cache/userCache.ts",
        expected_line=14,
        expected_severity="High",
        required_keywords=("cache", "invalidate", "stale"),
        related_files=("src/cache/userCache.ts",),
        concept_groups=(
            ("cache", "cached", "redis"),
            ("stale", "stale read", "coherence", "invalidation", "invalidate"),
            ("update", "mutation", "write"),
        ),
        diff="""diff --git a/src/cache/userCache.ts b/src/cache/userCache.ts
index 1234567..89abcdef 100644
--- a/src/cache/userCache.ts
+++ b/src/cache/userCache.ts
@@ -1,6 +1,6 @@
 import { db } from '../db';
 import { cache } from './redis';

 export async function updateUser(userId: string, data: any) {
     await db.users.update(userId, data);
-    await cache.del(`user:${userId}`);
 }""",
    ),
    "route_mounting_auth_bypass": BenchmarkCase(
        case_id="route_mounting_auth_bypass",
        title="Admin router mounted before authentication middleware",
        expected_filepath="src/index.ts",
        expected_line=6,
        expected_severity="High",
        required_keywords=("admin", "middleware", "auth", "order"),
        requires_context=True,
        related_files=("src/index.ts", "src/routes/admin.ts", "src/middleware/auth.ts"),
        concept_groups=(
            ("auth", "authentication", "requireAuth", "unauthenticated"),
            ("admin", "requireAdmin", "privilege", "authorization"),
            ("mount", "mounting", "order", "before", "middleware"),
            ("bypass", "unprotected", "exposed", "internal/admin"),
        ),
        diff="""diff --git a/src/index.ts b/src/index.ts
index 1234567..89abcdef 100644
--- a/src/index.ts
+++ b/src/index.ts
@@ -1,8 +1,10 @@
 import express from 'express';
+import adminRouter from './routes/admin';
 import { requireAuth, requireAdmin } from './middleware/auth';
 const app = express();
 app.use(express.json());

+app.use('/internal/admin', adminRouter);
 app.use(requireAuth);
 app.use(requireAdmin);
 app.use('/admin', adminRouter);
""",
    ),
    "cache_key_mismatch": BenchmarkCase(
        case_id="cache_key_mismatch",
        title="Update invalidates a different key than cached reads use",
        expected_filepath="src/cache/accountCache.ts",
        expected_line=14,
        expected_severity="High",
        required_keywords=("cache", "key", "mismatch", "stale"),
        requires_context=True,
        related_files=("src/cache/accountCache.ts",),
        concept_groups=(
            ("cache", "cached", "redis"),
            ("stale", "stale read", "coherence", "mismatch"),
            ("key", "namespace", "singular", "plural", "account", "accounts"),
            ("read", "write", "update", "invalidate"),
        ),
        diff="""diff --git a/src/cache/accountCache.ts b/src/cache/accountCache.ts
index 1234567..89abcdef 100644
--- a/src/cache/accountCache.ts
+++ b/src/cache/accountCache.ts
@@ -12,5 +12,5 @@ export async function updateAccount(accountId: string, data: any) {
     await db.users.update(accountId, data);
-    await cache.del(`account:${accountId}`);
+    await cache.del(`accounts:${accountId}`);
 }
""",
    ),
    "async_swallowed_error": BenchmarkCase(
        case_id="async_swallowed_error",
        title="Import route reports success before asynchronous import failure is observed",
        expected_filepath="src/routes/import.ts",
        expected_line=5,
        expected_severity="High",
        required_keywords=("async", "await", "success", "error"),
        requires_context=True,
        related_files=("src/routes/import.ts",),
        concept_groups=(
            ("async", "promise", "await", "rejected", "rejection"),
            ("swallow", "detached", "fire-and-forget", "not awaited", "catch"),
            ("success", "200", "2xx", "false success", "sendStatus"),
            ("error", "failure", "500", "import", "failed"),
        ),
        diff="""diff --git a/src/routes/import.ts b/src/routes/import.ts
index 1234567..89abcdef 100644
--- a/src/routes/import.ts
+++ b/src/routes/import.ts
@@ -2,8 +2,9 @@ import express from 'express';
 const router = express.Router();

 router.post('/import', async (req, res) => {
     try {
-        await processLargeCSV(req.body.csv);
+        processLargeCSV(req.body.csv).catch(e => console.error(e));
         res.sendStatus(200);
     } catch (e) {
         res.status(500).json({ error: 'import failed' });
     }
""",
    ),
    "xss_vulnerability": BenchmarkCase(
        case_id="xss_vulnerability",
        title="XSS vulnerability through unsanitized user input in HTML response",
        expected_filepath="src/routes/profile.ts",
        expected_line=7,
        expected_severity="Critical",
        required_keywords=("xss", "sanitize", "escape", "html"),
        related_files=("src/routes/profile.ts",),
        concept_groups=(
            ("xss", "cross-site scripting", "html injection", "script injection"),
            ("user input", "request parameter", "url parameter", "username"),
            ("sanitize", "escape", "escapeHtml", "html encoding"),
        ),
        diff="""diff --git a/src/routes/profile.ts b/src/routes/profile.ts
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/src/routes/profile.ts
@@ -0,0 +1,13 @@
+import express from 'express';
+
+const router = express.Router();
+
+router.get('/profile/:username', (req, res) => {
+  const username = req.params.username;
+  res.send(`<html>
+    <head><title>User Profile</title></head>
+    <body>
+      <h1>Profile: ${username}</h1>
+      <p>Welcome to ${username}'s profile page!</p>
+    </body>
+  </html>`);
+});
""",
    ),
    "unhandled_promise_rejection": BenchmarkCase(
        case_id="unhandled_promise_rejection",
        title="Unhandled promise rejection in async email service",
        expected_filepath="src/services/email.ts",
        expected_line=18,
        expected_severity="High",
        required_keywords=("promise", "rejection", "error", "catch"),
        related_files=("src/services/email.ts",),
        concept_groups=(
            ("unhandled rejection", "promise rejection", "async error"),
            ("error handling", "try catch", "catch block"),
            ("email", "notification", "external service"),
        ),
        diff="""diff --git a/src/services/email.ts b/src/services/email.ts
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/src/services/email.ts
@@ -0,0 +1,23 @@
+import { db } from '../db';
+
+const emailClient = {
+  async send(options: { to: string; subject: string; body: string }) {
+    if (Math.random() > 0.9) {
+      throw new Error('Email service unavailable');
+    }
+  }
+};
+
+export async function sendWelcomeEmail(userId: number) {
+  const user = await db.users.findById(userId);
+
+  await emailClient.send({
+    to: user.email,
+    subject: 'Welcome!',
+    body: 'Thanks for signing up'
+  });
+}
""",
    ),
    "missing_auth_tests": BenchmarkCase(
        case_id="missing_auth_tests",
        title="Security-critical authentication endpoints lack test coverage",
        expected_filepath="src/routes/auth.ts",
        expected_line=9,
        expected_severity="Medium",
        required_keywords=("test", "coverage", "authentication", "security"),
        related_files=("src/routes/auth.ts",),
        concept_groups=(
            ("test", "testing", "test coverage", "unit test", "integration test"),
            ("authentication", "login", "password", "credentials"),
            ("security", "security testing", "sql injection", "validation"),
        ),
        diff="""diff --git a/src/routes/auth.ts b/src/routes/auth.ts
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/src/routes/auth.ts
@@ -0,0 +1,36 @@
+import express from 'express';
+import bcrypt from 'bcrypt';
+import jwt from 'jsonwebtoken';
+import { db } from '../db';
+
+const router = express.Router();
+const SECRET = process.env.JWT_SECRET || 'default-secret';
+
+router.post('/login', async (req, res) => {
+  const { email, password } = req.body;
+
+  if (!email || !password) {
+    return res.status(400).json({ error: 'Email and password required' });
+  }
+
+  const user = await db.users.findByEmail(email);
+  if (!user) {
+    return res.status(401).json({ error: 'Invalid credentials' });
+  }
+
+  const valid = await bcrypt.compare(password, user.passwordHash);
+  if (!valid) {
+    return res.status(401).json({ error: 'Invalid credentials' });
+  }
+
+  const token = jwt.sign(
+    { userId: user.id, email: user.email },
+    SECRET,
+    { expiresIn: '24h' }
+  );
+
+  res.json({ token, user: { id: user.id, email: user.email, name: user.name } });
+});
""",
    ),
    "n_plus_one_query": BenchmarkCase(
        case_id="n_plus_one_query",
        title="N+1 query problem fetching authors in a loop",
        expected_filepath="src/routes/posts.ts",
        expected_line=11,
        expected_severity="High",
        required_keywords=("n+1", "query", "performance", "loop"),
        related_files=("src/routes/posts.ts",),
        concept_groups=(
            ("n+1", "query performance", "database optimization"),
            ("loop", "for loop", "iteration", "await in loop"),
            ("join", "eager loading", "batch loading", "include"),
        ),
        diff="""diff --git a/src/routes/posts.ts b/src/routes/posts.ts
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/src/routes/posts.ts
@@ -0,0 +1,14 @@
+import express from 'express';
+import { db } from '../db';
+
+const router = express.Router();
+
+router.get('/posts', async (req, res) => {
+  const posts = await db.posts.findAll();
+
+  for (const post of posts) {
+    post.author = await db.users.findById(post.authorId);
+  }
+
+  res.json(posts);
+});
""",
    ),
}


def get_benchmark_case(case_id: str) -> BenchmarkCase:
    """Return a benchmark case by ID."""
    return BENCHMARK_CASES[case_id]


def select_benchmark_cases(case_ids: str | None = None) -> List[BenchmarkCase]:
    """Select benchmark cases from a comma-separated list."""
    if not case_ids:
        return list(BENCHMARK_CASES.values())

    selected = []
    for raw_case_id in case_ids.split(","):
        case_id = raw_case_id.strip()
        if case_id:
            selected.append(get_benchmark_case(case_id))
    return selected


def benchmark_repo_path(root: Path) -> Path:
    """Return the benchmark repository path."""
    return root / "benchmark_repo"


def score_review(case: BenchmarkCase, review: ReviewOutput, repo_path: Path) -> BenchmarkScore:
    """Score a review output with deterministic benchmark checks using concept groups and related files."""
    best_comment = _best_comment(case, review.comments)
    hallucinated_files = _count_hallucinated_files(review.comments, repo_path)
    all_text = _review_text(review)
    lower_text = all_text.lower()

    grounding_score, matched_filepath, matched_line = _compute_grounding_score(case, best_comment)
    severity_score, matched_severity = _compute_severity_score(case, best_comment)
    concept_score = _compute_concept_score(case, lower_text)

    no_hallucination_bonus = 0.05 if hallucinated_files == 0 and review.comments else 0.0
    score = grounding_score + severity_score + concept_score + no_hallucination_bonus
    score = max(0.0, min(1.0, score - (0.10 * hallucinated_files)))

    issue_detected = (
        (matched_filepath or (case.related_files and best_comment and best_comment.filepath in case.related_files))
        and matched_severity
        and concept_score >= 0.20
    )

    rounded_score = round(score, 2)
    notes = "matched expected issue" if rounded_score >= 0.75 else "missing expected evidence"

    return BenchmarkScore(
        case_id=case.case_id,
        score=rounded_score,
        matched_filepath=matched_filepath,
        matched_line=matched_line,
        matched_severity=matched_severity,
        keyword_total=len(case.required_keywords),
        hallucinated_files=hallucinated_files,
        notes=notes,
        requires_context=case.requires_context,
        issue_detected=issue_detected,
        grounding_score=round(grounding_score, 2),
        concept_score=round(concept_score, 2),
        severity_score=round(severity_score, 2),
    )


def write_benchmark_outputs(results: Iterable[dict], output_dir: Path) -> tuple[Path, Path]:
    """Write benchmark JSON and Markdown reports."""
    output_dir.mkdir(parents=True, exist_ok=True)
    result_list = list(results)
    json_path = output_dir / "benchmark_results.json"
    markdown_path = output_dir / "benchmark_results.md"
    json_path.write_text(json.dumps(result_list, indent=2), encoding="utf-8")
    markdown_path.write_text(_format_markdown_results(result_list), encoding="utf-8")
    return json_path, markdown_path


def _best_comment(case: BenchmarkCase, comments: List[CodeComment]) -> CodeComment | None:
    # First try exact expected file
    matches = [comment for comment in comments if comment.filepath == case.expected_filepath]
    if matches:
        return min(matches, key=lambda comment: abs(comment.line_number - case.expected_line))

    # Then try related files
    if case.related_files:
        related_matches = [comment for comment in comments if comment.filepath in case.related_files]
        if related_matches:
            # Prefer high severity findings in related files
            high_severity = [c for c in related_matches if c.severity.lower() in ('high', 'critical')]
            if high_severity:
                return high_severity[0]
            return related_matches[0]

    # Fall back to first comment
    return comments[0] if comments else None


def _count_hallucinated_files(comments: List[CodeComment], repo_path: Path) -> int:
    count = 0
    root = repo_path.resolve()
    for comment in comments:
        full_path = (root / comment.filepath).resolve()
        try:
            full_path.relative_to(root)
        except ValueError:
            count += 1
            continue
        if not full_path.exists():
            count += 1
    return count


def _compute_grounding_score(case: BenchmarkCase, best_comment: CodeComment | None) -> tuple[float, bool, bool]:
    """Compute grounding score based on file and line matching."""
    grounding_score = 0.0
    matched_filepath = False
    matched_line = False

    if best_comment is not None:
        if best_comment.filepath == case.expected_filepath:
            matched_filepath = True
            grounding_score += 0.30
        elif case.related_files and best_comment.filepath in case.related_files:
            matched_filepath = True
            grounding_score += 0.25

        if matched_filepath and abs(best_comment.line_number - case.expected_line) <= case.line_tolerance:
            matched_line = True
            grounding_score += 0.20
        elif case.related_files and best_comment.filepath in case.related_files:
            grounding_score += 0.10

    return grounding_score, matched_filepath, matched_line


def _compute_severity_score(case: BenchmarkCase, best_comment: CodeComment | None) -> tuple[float, bool]:
    """Compute severity score based on severity matching."""
    severity_score = 0.0
    matched_severity = False
    if best_comment is not None and best_comment.severity.lower() == case.expected_severity.lower():
        matched_severity = True
        severity_score = 0.15
    return severity_score, matched_severity


def _compute_concept_score(case: BenchmarkCase, lower_text: str) -> float:
    """Compute concept score using concept groups or keywords."""
    if case.concept_groups:
        satisfied_groups = sum(
            1 for group in case.concept_groups
            if any(term.lower() in lower_text for term in group)
        )
        return 0.30 * (satisfied_groups / max(1, len(case.concept_groups)))
    else:
        keyword_hits = sum(1 for keyword in case.required_keywords if keyword.lower() in lower_text)
        return 0.30 * (keyword_hits / max(1, len(case.required_keywords)))


def _review_text(review: ReviewOutput) -> str:
    pieces = [review.overall_summary]
    for comment in review.comments:
        pieces.extend([comment.issue_description, comment.suggested_fix, comment.severity])
    return "\n".join(pieces)


def _format_markdown_results(results: List[dict]) -> str:
    lines = [
        "# ReviewStem Benchmark Results",
        "",
        "| Case | Generic | Generic+Skills | ReviewStem | Delta vs Generic | Detected? | Calls G/S/RS | Passes | Requires Context |",
        "| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | --- |",
    ]
    for result in results:
        baseline = result["baseline_score"]
        skilled = result.get("skilled_baseline_score", 0.0)
        reviewstem = result["reviewstem_score"]
        delta = reviewstem - baseline
        detected = "✓" if result.get("issue_detected", False) else "✗"
        calls = f"{result.get('baseline_calls', 0)}/{result.get('skilled_baseline_calls', 0)}/{result.get('reviewstem_calls', 0)}"
        passes = result.get("passes", 1)
        requires_context = "Yes" if result.get('requires_context', False) else "No"
        lines.append(
            f"| {result['case_id']} | {baseline:.2f} | {skilled:.2f} | {reviewstem:.2f} | {delta:+.2f} | {detected} | {calls} | {passes} | {requires_context} |"
        )

    lines.extend([
        "",
        "## Scoring Notes",
        "",
        "The deterministic scorer uses related files and concept groups rather than exact wording only.",
        "This avoids penalizing correct findings that identify the same root cause through a different but valid file or line.",
        "",
        "**Detected?** indicates whether the review identified the core issue with correct severity and sufficient concept coverage,",
        "regardless of whether it cited the exact expected line.",
        "",
        "Some cases saturate: the generic baseline already catches the obvious issue. These cases are retained as smoke tests,",
        "while context-required cases evaluate whether ReviewStem's specialization trace and repository-aware review flow",
        "provide additional evidence.",
    ])

    return "\n".join(lines) + "\n"
