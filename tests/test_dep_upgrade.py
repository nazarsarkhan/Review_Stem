"""Tests for the dep_upgrade domain: diff extraction, scoring, fitness penalties."""

import asyncio
from pathlib import Path

from reviewstem.config import ReviewStemConfig
from reviewstem.domains.dep_upgrade.benchmark import (
    DEP_UPGRADE_CASES,
    extract_packages_from_diff,
    score_dep_review,
)
from reviewstem.domains.dep_upgrade.fitness import DepUpgradeFitness
from reviewstem.domains.dep_upgrade.osv_client import OSVClient
from reviewstem.schemas import CodeComment, EvaluationScore, ReviewOutput


class StubLLM:
    """Bypasses network; always returns a perfect EvaluationScore."""

    def __init__(self, score: float = 1.0, feedback: str = "stub"):
        self.config = ReviewStemConfig.from_env()
        self.model = "stub"
        self.temperature = 0
        self.client = None
        self.call_count = 0
        self._score = score
        self._feedback = feedback

    async def parse(self, prompt, schema, **kwargs):
        self.call_count += 1
        return EvaluationScore(score=self._score, feedback=self._feedback)


def _run(coro):
    return asyncio.run(coro)


def test_extract_pip_diff_captures_both_versions():
    diff = """--- a/requirements.txt
+++ b/requirements.txt
@@ -1,2 +1,2 @@
-requests==2.25.0
+requests==2.31.0
"""
    pkgs = extract_packages_from_diff(diff)
    assert ("PyPI", "requests", "2.25.0") in pkgs
    assert ("PyPI", "requests", "2.31.0") in pkgs


def test_extract_npm_diff_captures_both_versions():
    diff = """--- a/package.json
+++ b/package.json
@@ -3,5 +3,5 @@
   "dependencies": {
-    "lodash": "4.17.10",
+    "lodash": "4.17.21"
   }
"""
    pkgs = extract_packages_from_diff(diff)
    assert ("npm", "lodash", "4.17.10") in pkgs
    assert ("npm", "lodash", "4.17.21") in pkgs


def test_extract_ignores_diff_headers():
    """The +++/--- header lines must not be parsed as package entries."""
    diff = "diff --git a/requirements.txt b/requirements.txt\n+++ b/requirements.txt\n---a/requirements.txt\n+requests==1.0.0\n"
    pkgs = extract_packages_from_diff(diff)
    assert pkgs == [("PyPI", "requests", "1.0.0")]


def test_score_dep_review_full_credit_when_all_signals_match():
    case = DEP_UPGRADE_CASES["requests_cve_upgrade"]
    review = ReviewOutput(
        comments=[
            CodeComment(
                filepath="requirements.txt",
                line_number=1,
                severity="High",
                issue_description=(
                    "Upgrading requests fixes CVE-2023-32681, a Proxy-Authorization header leak."
                ),
                suggested_fix="Pin requests==2.31.0 in requirements.txt and audit the lockfile.",
            )
        ],
        overall_summary="Requests upgrade addresses CVE-2023-32681.",
    )
    s = score_dep_review(case, review)
    assert s.matched_vuln_ids == 1
    assert s.severity_match is True
    assert s.score >= 0.75


def test_score_dep_review_partial_credit_when_severity_wrong():
    case = DEP_UPGRADE_CASES["requests_cve_upgrade"]
    review = ReviewOutput(
        comments=[
            CodeComment(
                filepath="requirements.txt",
                line_number=1,
                severity="Low",  # wrong severity
                issue_description="Upgrade requests; CVE-2023-32681 is a minor leak.",
                suggested_fix="Bump version",
            )
        ],
        overall_summary="x",
    )
    s = score_dep_review(case, review)
    assert s.severity_match is False
    assert s.score < 0.85


def test_fitness_penalizes_hallucinated_cve():
    fitness = DepUpgradeFitness(
        StubLLM(score=1.0),
        osv=OSVClient(cache_dir=Path("reviewstem/domains/dep_upgrade/osv_fixtures"), offline=True),
        manifest_packages=[("PyPI", "requests", "2.25.0")],
    )
    review = ReviewOutput(
        comments=[
            CodeComment(
                filepath="requirements.txt",
                line_number=1,
                severity="High",
                issue_description="requests has CVE-9999-99999 which causes RCE in this version range",
                suggested_fix="Upgrade to requests==2.31.0 to remediate this hallucinated CVE",
            )
        ],
        overall_summary="x",
    )
    out = _run(fitness.evaluate(review))
    codes = {p.code for p in fitness.last_penalties}
    assert "hallucinated_cve" in codes
    assert out.score < 1.0


def test_fitness_does_not_penalize_real_cve():
    fitness = DepUpgradeFitness(
        StubLLM(score=1.0),
        osv=OSVClient(cache_dir=Path("reviewstem/domains/dep_upgrade/osv_fixtures"), offline=True),
        manifest_packages=[("PyPI", "requests", "2.25.0")],
    )
    review = ReviewOutput(
        comments=[
            CodeComment(
                filepath="requirements.txt",
                line_number=1,
                severity="High",
                issue_description="requests 2.25.0 has CVE-2023-32681, a Proxy-Authorization header leak risk",
                suggested_fix="Upgrade to requests==2.31.0 which is the fixed version",
            )
        ],
        overall_summary="x",
    )
    out = _run(fitness.evaluate(review))
    codes = {p.code for p in fitness.last_penalties}
    assert "hallucinated_cve" not in codes


def test_fitness_penalizes_non_manifest_file():
    fitness = DepUpgradeFitness(
        StubLLM(score=1.0),
        manifest_packages=[],
    )
    review = ReviewOutput(
        comments=[
            CodeComment(
                filepath="src/app.py",  # not a manifest
                line_number=1,
                severity="Medium",
                issue_description="This is a dependency review that points at application code by mistake",
                suggested_fix="Move the finding to requirements.txt instead",
            )
        ],
        overall_summary="x",
    )
    out = _run(fitness.evaluate(review))
    codes = {p.code for p in fitness.last_penalties}
    assert "non_manifest_file" in codes


def test_fitness_penalizes_empty_review():
    fitness = DepUpgradeFitness(StubLLM(score=1.0))
    out = _run(fitness.evaluate(ReviewOutput(comments=[], overall_summary="")))
    codes = {p.code for p in fitness.last_penalties}
    assert "empty_review" in codes


def test_all_8_dep_upgrade_cases_have_required_metadata():
    for case_id, case in DEP_UPGRADE_CASES.items():
        assert case.diff, f"{case_id}: empty diff"
        assert case.expected_filepath
        assert case.expected_severity
        assert case.concept_groups, f"{case_id}: needs concept_groups for scoring"
        assert case.packages, f"{case_id}: needs packages for OSV grounding"
