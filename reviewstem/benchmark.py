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


@dataclass(frozen=True)
class BenchmarkScore:
    """Deterministic benchmark score for one review output."""

    case_id: str
    score: float
    matched_filepath: bool
    matched_line: bool
    matched_severity: bool
    keyword_hits: int
    keyword_total: int
    hallucinated_files: int
    notes: str


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
        expected_line=4,
        expected_severity="Medium",
        required_keywords=("cache", "invalidate", "stale"),
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
    """Score a review output with deterministic benchmark checks."""
    best_comment = _best_comment(case, review.comments)
    hallucinated_files = _count_hallucinated_files(review.comments, repo_path)
    all_text = _review_text(review)
    lower_text = all_text.lower()
    keyword_hits = sum(1 for keyword in case.required_keywords if keyword.lower() in lower_text)

    matched_filepath = best_comment is not None and best_comment.filepath == case.expected_filepath
    matched_line = best_comment is not None and abs(best_comment.line_number - case.expected_line) <= 1
    matched_severity = best_comment is not None and best_comment.severity.lower() == case.expected_severity.lower()

    score = 0.0
    score += 0.30 if matched_filepath else 0.0
    score += 0.20 if matched_line else 0.0
    score += 0.15 if matched_severity else 0.0
    score += 0.25 * (keyword_hits / max(1, len(case.required_keywords)))
    score += 0.10 if hallucinated_files == 0 and review.comments else 0.0
    score = max(0.0, min(1.0, score - (0.10 * hallucinated_files)))

    notes = "matched expected issue" if score >= 0.80 else "missing expected evidence"
    return BenchmarkScore(
        case_id=case.case_id,
        score=round(score, 2),
        matched_filepath=matched_filepath,
        matched_line=matched_line,
        matched_severity=matched_severity,
        keyword_hits=keyword_hits,
        keyword_total=len(case.required_keywords),
        hallucinated_files=hallucinated_files,
        notes=notes,
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
    matches = [comment for comment in comments if comment.filepath == case.expected_filepath]
    if matches:
        return min(matches, key=lambda comment: abs(comment.line_number - case.expected_line))
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


def _review_text(review: ReviewOutput) -> str:
    pieces = [review.overall_summary]
    for comment in review.comments:
        pieces.extend([comment.issue_description, comment.suggested_fix, comment.severity])
    return "\n".join(pieces)


def _format_markdown_results(results: List[dict]) -> str:
    lines = [
        "# ReviewStem Benchmark Results",
        "",
        "| Case | Baseline | ReviewStem | Delta | Notes |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for result in results:
        baseline = result["baseline_score"]
        reviewstem = result["reviewstem_score"]
        delta = reviewstem - baseline
        lines.append(
            f"| {result['case_id']} | {baseline:.2f} | {reviewstem:.2f} | {delta:+.2f} | {result['notes']} |"
        )
    return "\n".join(lines) + "\n"
