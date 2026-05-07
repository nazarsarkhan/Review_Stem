import logging
from typing import List

from .llm_client import LLMClient
from .schemas import EvaluationScore, GenomeCluster, ReviewGenome, ReviewOutput

logger = logging.getLogger("ReviewStem")


class MutationEngine:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def evolve(
        self,
        previous_genomes: List[ReviewGenome],
        review: ReviewOutput,
        evaluation: EvaluationScore,
    ) -> GenomeCluster:
        """Revise review instructions based on failure feedback."""
        logger.info("Revising reviewer instructions based on fitness feedback.")

        prompt = f"""
        You are ReviewStem's reviewer revision step.
        A previous generation of reviewers failed to reach the quality threshold.

        Previous Reviewers:
        {[g.model_dump_json() for g in previous_genomes]}

        The Failure Findings:
        {review.model_dump_json()}

        The Evaluator's Feedback:
        {evaluation.feedback}

        Instructions:
        1. Identify exactly what the reviewers missed or where they hallucinated.
        2. Rewrite the persona and checklists in the genomes to fix these issues.
        3. Add specific, hard constraints to the `specific_checks` to ensure the same mistake is not repeated.
        """
        mutated_cluster = await self.llm.parse(prompt, schema=GenomeCluster)
        logger.info("Reviewer revision generated %s new reviewers.", len(mutated_cluster.genomes))
        return mutated_cluster
