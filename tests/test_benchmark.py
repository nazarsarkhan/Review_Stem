from pathlib import Path

from reviewstem.benchmark import get_benchmark_case, score_review, select_benchmark_cases, write_benchmark_outputs
from reviewstem.schemas import CodeComment, ReviewOutput


def test_select_benchmark_cases_filters_requested_ids():
    cases = select_benchmark_cases("sql_injection,cache_invalidation")

    assert [case.case_id for case in cases] == ["sql_injection", "cache_invalidation"]


def test_score_review_rewards_expected_grounded_finding():
    case = get_benchmark_case("sql_injection")
    review = ReviewOutput(
        comments=[
            CodeComment(
                filepath="src/db/users.ts",
                line_number=4,
                severity="High",
                issue_description="SQL injection from name interpolation.",
                suggested_fix="Use a parameterized query with [name].",
            )
        ],
        overall_summary="SQL injection risk should be fixed with a parameter.",
    )

    score = score_review(case, review, Path("benchmark_repo"))

    assert score.score >= 0.90
    assert score.matched_filepath
    assert score.matched_line
    assert score.hallucinated_files == 0


def test_score_review_penalizes_hallucinated_file():
    case = get_benchmark_case("sql_injection")
    review = ReviewOutput(
        comments=[
            CodeComment(
                filepath="src/db/missing.ts",
                line_number=4,
                severity="High",
                issue_description="SQL injection from name interpolation.",
                suggested_fix="Use a parameterized query with [name].",
            )
        ],
        overall_summary="SQL injection risk should be fixed with a parameter.",
    )

    score = score_review(case, review, Path("benchmark_repo"))

    assert score.hallucinated_files == 1
    assert score.score < 0.80


def test_select_benchmark_cases_includes_context_required_cases():
    cases = select_benchmark_cases("route_mounting_auth_bypass,cache_key_mismatch")

    assert [case.case_id for case in cases] == ["route_mounting_auth_bypass", "cache_key_mismatch"]
    assert all(case.requires_context for case in cases)


def test_write_benchmark_outputs_includes_stronger_baseline_columns(tmp_path):
    json_path, markdown_path = write_benchmark_outputs(
        [
            {
                "case_id": "unit",
                "baseline_score": 0.5,
                "skilled_baseline_score": 0.7,
                "reviewstem_score": 0.9,
                "baseline_calls": 1,
                "skilled_baseline_calls": 1,
                "reviewstem_calls": 5,
                "requires_context": True,
                "notes": "matched expected issue",
                "issue_detected": True,
                "passes": 2,
            }
        ],
        tmp_path,
    )

    assert json_path.exists()
    assert "Generic+Skills" in markdown_path.read_text(encoding="utf-8")


def test_score_review_accepts_related_files_for_admin_auth():
    """Test that admin_auth accepts findings in src/index.ts (related file)."""
    case = get_benchmark_case("admin_auth")
    review = ReviewOutput(
        comments=[
            CodeComment(
                filepath="src/index.ts",
                line_number=6,
                severity="High",
                issue_description="Admin router mounted before authentication middleware, allowing unauthenticated access",
                suggested_fix="Move admin router mount after requireAuth and requireAdmin middleware",
            )
        ],
        overall_summary="Authorization bypass in admin route mounting",
    )

    score = score_review(case, review, Path("benchmark_repo"))

    assert score.matched_filepath, "Should accept related file src/index.ts"
    assert score.matched_severity
    assert score.issue_detected, "Should detect the issue even though it's in a related file"
    assert score.score >= 0.75, f"Score should be high for correct related-file finding, got {score.score}"


def test_score_review_uses_concept_groups():
    """Test that concept groups work for semantic matching."""
    case = get_benchmark_case("admin_auth")

    # Review with good concepts but different wording
    review = ReviewOutput(
        comments=[
            CodeComment(
                filepath="src/index.ts",
                line_number=6,
                severity="High",
                issue_description="Privileged endpoint exposed before auth checks, allowing non-admin users to bypass authorization",
                suggested_fix="Reorder middleware to apply requireAuth and requireAdmin before mounting admin routes",
            )
        ],
        overall_summary="Found privilege escalation vulnerability",
    )

    score = score_review(case, review, Path("benchmark_repo"))

    assert score.concept_score > 0.20, "Should match multiple concept groups"
    assert score.issue_detected


def test_score_review_penalizes_vague_generic_advice():
    """Test that vague generic advice scores lower than specific findings."""
    case = get_benchmark_case("admin_auth")

    vague_review = ReviewOutput(
        comments=[
            CodeComment(
                filepath="src/routes/admin.ts",
                line_number=4,
                severity="Medium",
                issue_description="This route might have security issues",
                suggested_fix="Add proper security",
            )
        ],
        overall_summary="Security review completed",
    )

    score = score_review(case, vague_review, Path("benchmark_repo"))

    assert score.concept_score < 0.15, "Vague advice should have low concept score"
    assert not score.issue_detected, "Vague advice should not count as issue detection"
    assert score.score < 0.75, "Vague advice should score lower than specific findings"
