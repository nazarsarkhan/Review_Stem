from .llm_client import LLMClient
from .logger import logger
from .schemas import GenomeCluster, ReviewGenome, StressTestProfile


class NeuralPruner:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def prune(self, cluster: GenomeCluster) -> GenomeCluster:
        """Merge redundant specialized genomes to ensure efficient focus."""
        logger.info("Removing redundant specialized reviewers.")
        prompt = f"""
        You are the reviewer consolidation step. Review this cluster of specialized review genomes.
        If two or more genomes are highly overlapping or searching for the exact same bugs
        (e.g., 'Security Reviewer' and 'SQL Injection Reviewer'), merge them into a single comprehensive genome.
        Keep orthogonal genomes separate. Limit the final cluster to max 3 highly distinct genomes.

        Current Genomes:
        {[g.model_dump_json() for g in cluster.genomes]}
        """
        pruned_cluster = await self.llm.parse(prompt, schema=GenomeCluster, stage="prune_reviewers")
        logger.info(
            "Reduced reviewer set from %s to %s.",
            len(cluster.genomes),
            len(pruned_cluster.genomes),
        )
        return pruned_cluster


class StressTester:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def generate_profile(self, genome: ReviewGenome, diff: str) -> StressTestProfile:
        """Generate likely bug classes to focus the reviewer's attention."""
        logger.info("Generating risk profile for '%s'.", genome.persona_name)
        prompt = f"""
        You are a code-review risk analyst. Based on this ReviewGenome and the PR Diff,
        what are 3 highly probable bugs or edge cases that this specific persona should prioritize finding?
        This will be used to prime the reviewer's attention.

        Genome: {genome.model_dump_json()}
        Diff: {diff}
        """
        return await self.llm.parse(prompt, schema=StressTestProfile, stage="stress_profile")
