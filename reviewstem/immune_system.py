from typing import List

from .llm_client import LLMClient
from .logger import logger
from .schemas import ReviewOutput


class ImmuneSystem:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def synthesize_and_criticize(self, reviews: List[ReviewOutput]) -> ReviewOutput:
        """Synthesize multiple expert reviews and filter out weak findings."""
        logger.info("Synthesizing and validating draft reviews.")

        raw_jsons = [r.model_dump_json(indent=2) for r in reviews]

        prompt = f"""
        You are ReviewStem's final review editor. You have received several draft reviews from specialized agents.
        Your goal is to synthesize them into a single, high-quality, authoritative code review.

        Raw Reviews:
        {raw_jsons}

        Instructions:
        1. Deduplicate findings (if multiple specialists found the same bug).
        2. Filter out 'noise' (vague comments, purely stylistic nitpicks, or findings that seem like hallucinations).
        3. Prioritize high-severity security and logic bugs.
        4. Keep only findings tied to a concrete file and exact line number.
        5. Suggested fixes must be complete enough to apply, including all required arguments and placeholders.
           For SQL parameterization, do not write incomplete examples like `db.query('...', )`.
           A complete example is `await db.query('SELECT * FROM users WHERE name = $1', [name])`.
        6. Use concise, professional language suitable for an engineering code review.
        7. Provide a cohesive Executive Summary.
        8. Output the final ReviewOutput JSON with high-fidelity and structurally sound comments.
        """
        final_review = await self.llm.parse(prompt, schema=ReviewOutput, stage="synthesize_review")
        logger.info("Final review contains %s critical comments.", len(final_review.comments))
        return final_review
