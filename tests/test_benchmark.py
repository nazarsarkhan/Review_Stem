from pathlib import Path

from reviewstem.benchmark import get_benchmark_case, score_review, select_benchmark_cases
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
