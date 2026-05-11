from typing import List

from .llm_client import LLMClient
from .logger import logger
from .schemas import EvaluationScore, GenomeCluster, ReviewGenome, ReviewOutput


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
        4. Explicitly address grounding failures, weak or incomplete fixes, hallucinated files,
           invalid line references, missing risk areas, and insufficient test expectations when the feedback mentions them.
        5. Preserve useful source_skills and risk_profile fields, but add or remove them when the failure shows
           that the temporary review architecture selected the wrong expertise.
        """
        mutated_cluster = await self.llm.parse(prompt, schema=GenomeCluster, stage="mutate_reviewers")
        logger.info("Reviewer revision generated %s new reviewers.", len(mutated_cluster.genomes))
        return mutated_cluster
