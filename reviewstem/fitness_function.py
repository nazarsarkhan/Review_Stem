import logging
from pathlib import Path
import re

from .llm_client import LLMClient
from .schemas import DeterministicPenalty, EvaluationScore, ReviewOutput

logger = logging.getLogger("ReviewStem")


INCOMPLETE_SQL_PARAMETER_PATTERN = re.compile(r"db\.query\([^`]*\$1['\"]\s*,\s*\)")


class FitnessFunction:
    def __init__(self, llm: LLMClient, repo_path: str = ".", changed_files: list[str] | None = None):
        self.llm = llm
        self.repo_path = Path(repo_path).resolve()
        self.changed_files = set(changed_files or [])
        self.last_penalties: list[DeterministicPenalty] = []

    async def evaluate(self, review: ReviewOutput) -> EvaluationScore:
        """Evaluate review quality by checking repository grounding."""
        logger.info("Evaluating review quality and repository grounding.")

        penalties: list[DeterministicPenalty] = []
        seen_findings: set[tuple[str, int, str]] = set()
        for comment in review.comments:
            full_path = (self.repo_path / comment.filepath).resolve()
            try:
                full_path.relative_to(self.repo_path)
            except ValueError:
                logger.warning("Sandbox detected out-of-repo file: %s", comment.filepath)
                penalties.append(_penalty("out_of_repo_file", 0.2, comment.filepath, comment.line_number, "Finding references a path outside the repository."))
                continue

            if not full_path.exists():
                logger.warning("Sandbox detected hallucinated file: %s", comment.filepath)
                penalties.append(_penalty("hallucinated_file", 0.2, comment.filepath, comment.line_number, "Finding references a file that does not exist."))
                continue

            try:
                line_count = len(full_path.read_text(encoding="utf-8").splitlines())
            except Exception:
                line_count = 0

            if comment.line_number < 1 or (line_count and comment.line_number > line_count):
                logger.warning(
                    "Sandbox detected invalid line reference: %s:%s",
                    comment.filepath,
                    comment.line_number,
                )
                penalties.append(_penalty("invalid_line", 0.2, comment.filepath, comment.line_number, "Finding references a line outside the file."))

            if INCOMPLETE_SQL_PARAMETER_PATTERN.search(comment.suggested_fix):
                logger.warning(
                    "Sandbox detected incomplete parameterized SQL fix: %s:%s",
                    comment.filepath,
                    comment.line_number,
                )
                penalties.append(_penalty("incomplete_sql_fix", 0.2, comment.filepath, comment.line_number, "Suggested SQL parameterization fix is incomplete."))

            if self.changed_files and comment.filepath not in self.changed_files:
                penalties.append(_penalty("outside_changed_files", 0.05, comment.filepath, comment.line_number, "Finding is grounded in the repo but outside the changed files."))

            if _is_vague(comment.issue_description):
                penalties.append(_penalty("vague_finding", 0.1, comment.filepath, comment.line_number, "Finding description is too short or vague."))

            if comment.severity.lower() in {"high", "critical"} and len(comment.suggested_fix.strip()) < 20:
                penalties.append(_penalty("missing_high_severity_fix", 0.1, comment.filepath, comment.line_number, "High-severity finding lacks a concrete suggested fix."))

            key = (comment.filepath, comment.line_number, _normalize_issue(comment.issue_description))
            if key in seen_findings:
                penalties.append(_penalty("duplicate_finding", 0.05, comment.filepath, comment.line_number, "Duplicate finding appears more than once."))
            seen_findings.add(key)

        prompt = f"""
        You are the ReviewStem Evaluator. Grade this code review on a scale of 0.0 to 1.0.

        Review Data:
        {review.model_dump_json(indent=2)}

        Criteria:
        - Accuracy: Are the issues real?
        - Actionability: Are the suggested fixes concrete?
        - Completeness: Are suggested fixes complete enough to apply?
        - Precision: Does it point to exact files and lines?
        - Grounding: Is it based on the actual code, or is it generic advice?

        Provide a single score and short constructive feedback.
        """
        evaluation = await self.llm.parse(prompt, schema=EvaluationScore, stage="fitness_evaluate")

        deterministic_penalty = sum(item.amount for item in penalties)
        evaluation.score = max(0.0, evaluation.score - deterministic_penalty)
        self.last_penalties = penalties
        if deterministic_penalty > 0:
            evaluation.feedback += " [Sandbox explicitly penalized score due to grounding or fix-quality issues]."

        logger.info("Fitness Score: %s - Feedback: %s", evaluation.score, evaluation.feedback)
        return evaluation


def _penalty(code: str, amount: float, filepath: str | None, line_number: int | None, reason: str) -> DeterministicPenalty:
    return DeterministicPenalty(code=code, amount=amount, filepath=filepath, line_number=line_number, reason=reason)


def _is_vague(text: str) -> bool:
    lowered = text.strip().lower()
    if len(lowered) < 24:
        return True
    vague_phrases = ("fix this", "bad code", "issue here", "problematic", "could be improved")
    return any(phrase in lowered for phrase in vague_phrases)


def _normalize_issue(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()[:80]
