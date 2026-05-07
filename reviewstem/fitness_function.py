import logging
from pathlib import Path
import re

from .llm_client import LLMClient
from .schemas import EvaluationScore, ReviewOutput

logger = logging.getLogger("ReviewStem")


INCOMPLETE_SQL_PARAMETER_PATTERN = re.compile(r"db\.query\([^`]*\$1['\"]\s*,\s*\)")


class FitnessFunction:
    def __init__(self, llm: LLMClient, repo_path: str = "."):
        self.llm = llm
        self.repo_path = Path(repo_path).resolve()

    async def evaluate(self, review: ReviewOutput) -> EvaluationScore:
        """Evaluate review quality by checking repository grounding."""
        logger.info("Evaluating review quality and repository grounding.")

        hallucination_penalty = 0
        for comment in review.comments:
            full_path = (self.repo_path / comment.filepath).resolve()
            try:
                full_path.relative_to(self.repo_path)
            except ValueError:
                logger.warning("Sandbox detected out-of-repo file: %s", comment.filepath)
                hallucination_penalty += 0.2
                continue

            if not full_path.exists():
                logger.warning("Sandbox detected hallucinated file: %s", comment.filepath)
                hallucination_penalty += 0.2
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
                hallucination_penalty += 0.2

            if INCOMPLETE_SQL_PARAMETER_PATTERN.search(comment.suggested_fix):
                logger.warning(
                    "Sandbox detected incomplete parameterized SQL fix: %s:%s",
                    comment.filepath,
                    comment.line_number,
                )
                hallucination_penalty += 0.2

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
        evaluation = await self.llm.parse(prompt, schema=EvaluationScore)

        evaluation.score = max(0.0, evaluation.score - hallucination_penalty)
        if hallucination_penalty > 0:
            evaluation.feedback += " [Sandbox explicitly penalized score due to grounding or fix-quality issues]."

        logger.info("Fitness Score: %s - Feedback: %s", evaluation.score, evaluation.feedback)
        return evaluation
