import asyncio

from reviewstem.config import ReviewStemConfig
from reviewstem.fitness_function import FitnessFunction
from reviewstem.llm_client import LLMClient
from reviewstem.schemas import CodeComment, EvaluationScore, ReviewOutput


class StubLLM(LLMClient):
    """Bypass network calls; always return a perfect EvaluationScore."""

    def __init__(self, score: float = 1.0, feedback: str = "stub"):
        self.config = ReviewStemConfig.from_env()
        self.model = "stub"
        self.temperature = 0
        self.client = None
        self.call_count = 0
        self.call_log = []
        self._score = score
        self._feedback = feedback

    async def parse(self, prompt, schema, **kwargs):
        self.call_count += 1
        return EvaluationScore(score=self._score, feedback=self._feedback)


def _run(coro):
    return asyncio.run(coro)


def test_empty_review_is_heavily_penalised(tmp_path):
    fitness = FitnessFunction(StubLLM(score=1.0), repo_path=str(tmp_path))

    result = _run(fitness.evaluate(ReviewOutput(comments=[], overall_summary="")))

    assert result.score <= 0.70  # 1.0 stub - 0.30 empty review penalty
    assert any(p.code == "empty_review" for p in fitness.last_penalties)


def test_high_severity_without_tests_is_penalised(tmp_path):
    real_file = tmp_path / "a.py"
    real_file.write_text("line1\nline2\nline3\n", encoding="utf-8")
    fitness = FitnessFunction(StubLLM(score=1.0), repo_path=str(tmp_path))

    review = ReviewOutput(
        comments=[
            CodeComment(
                filepath="a.py",
                line_number=1,
                severity="High",
                issue_description="SQL injection risk in dynamic query construction here",
                suggested_fix="Use parameterized queries everywhere",
            ),
            CodeComment(
                filepath="a.py",
                line_number=2,
                severity="Critical",
                issue_description="Authentication bypass via missing middleware on admin path",
                suggested_fix="Add requireAuth before mounting the admin router",
            ),
        ],
        overall_summary="Critical findings without any suggested tests",
    )

    result = _run(fitness.evaluate(review))

    codes = {p.code for p in fitness.last_penalties}
    assert "no_tests_for_high_severity" in codes
    assert result.score < 1.0


def test_severity_inflation_is_penalised(tmp_path):
    real_file = tmp_path / "a.py"
    real_file.write_text("\n".join(f"line {i}" for i in range(20)), encoding="utf-8")
    fitness = FitnessFunction(StubLLM(score=1.0), repo_path=str(tmp_path))

    review = ReviewOutput(
        comments=[
            CodeComment(
                filepath="a.py",
                line_number=i,
                severity="Critical",
                issue_description=f"Long enough description for finding number {i} here",
                suggested_fix="Apply a complete and concrete fix to remediate this issue",
                suggested_tests=["test_case_for_this_finding"],
            )
            for i in range(1, 6)
        ],
        overall_summary="Spam-Critical review",
    )

    result = _run(fitness.evaluate(review))

    codes = {p.code for p in fitness.last_penalties}
    assert "severity_inflation" in codes


def test_hallucinated_file_is_penalised(tmp_path):
    fitness = FitnessFunction(StubLLM(score=1.0), repo_path=str(tmp_path))

    review = ReviewOutput(
        comments=[
            CodeComment(
                filepath="does/not/exist.py",
                line_number=1,
                severity="Low",
                issue_description="Some description that is long enough to avoid the vague penalty",
                suggested_fix="Apply this concrete fix here",
            )
        ],
        overall_summary="Cited a phantom file",
    )

    result = _run(fitness.evaluate(review))

    assert any(p.code == "hallucinated_file" for p in fitness.last_penalties)
    assert result.score < 1.0
