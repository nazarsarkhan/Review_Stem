from typing import List

from .llm_client import LLMClient
from .logger import logger
from .schemas import GenomeCluster, LearnedTrait, SelectedSkill


class StemCell:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def differentiate(
        self,
        repo_map: str,
        diff: str,
        skills: List[LearnedTrait | SelectedSkill],
    ) -> GenomeCluster:
        """Analyze the PR environment and select specialized review personas."""
        logger.info("Selecting specialized reviewers based on PR context.")

        skills_json = [s.model_dump_json() for s in skills]
        review_guidance = "\n".join(skills_json) if skills_json else "None."

        prompt = f"""
You are ReviewStem's reviewer selection step. Analyze the following PR diff and repository structure,
then create specialized ReviewGenomes that are suited to review these specific changes.

Repository Map:
{repo_map}

PR Diff:
{diff}

Review Guidance:
{review_guidance}

Instructions:
1. Identify the core components modified (e.g., Database, UI, Security).
2. For each major concern, spawn a specialized `ReviewGenome`.
3. If selected skills are provided, copy relevant skill names into `source_skills`,
   copy risk areas into `risk_profile`, and adopt concrete checklist/test items into `specific_checks`.
4. Keep the cluster lean (1-3 genomes maximum).
"""
        cluster = await self.llm.parse(prompt, schema=GenomeCluster, stage="differentiate")
        logger.info("Selected %s specialized reviewers.", len(cluster.genomes))
        for genome in cluster.genomes:
            logger.info("  - Reviewer: %s", genome.persona_name)
        return cluster
