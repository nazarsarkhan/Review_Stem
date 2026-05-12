"""Orchestrator for dep-upgrade reviews.

Reuses the existing stem_cell -> motor_cortex -> immune_system -> mutation
loop, swapping in the dep-upgrade skill catalog and the OSV-aware fitness
function. This is the test of generality the brief asks for: the same
specialization mechanics drive a different task class with a different
fitness signal.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from ...advanced_agents import NeuralPruner, StressTester
from ...config import ReviewStemConfig
from ...epigenetics import Epigenetics
from ...immune_system import ImmuneSystem
from ...llm_client import LLMClient
from ...logger import logger
from ...motor_cortex import MotorCortex
from ...mutation_engine import MutationEngine
from ...schemas import EvaluationScore, GenomeCluster, ReviewOutput
from ...stem_cell import StemCell
from .benchmark import extract_packages_from_diff
from .fitness import DepUpgradeFitness
from .osv_client import OSVClient


def _domain_skills_path() -> Path:
    return Path(__file__).parent / "skills.json"


async def run_dep_upgrade_review(
    diff: str,
    config: ReviewStemConfig,
    case_id: str | None = None,
    llm_kwargs: dict | None = None,
) -> tuple[ReviewOutput, EvaluationScore]:
    """End-to-end dep-upgrade review.

    Args:
        diff: manifest diff (pip / npm).
        config: pipeline configuration.
        case_id: optional benchmark case id.
        llm_kwargs: optional overrides forwarded to LLMClient (seed, temperature, cache_dir).

    Returns:
        (final_review, evaluation)
    """
    llm = LLMClient(config, **(llm_kwargs or {}))
    stem = StemCell(llm)
    motor = MotorCortex(llm, repo_path=str(Path.cwd()), config=config)
    immune = ImmuneSystem(llm)
    mutation = MutationEngine(llm)
    pruner = NeuralPruner(llm)
    stress_tester = StressTester(llm)

    packages = extract_packages_from_diff(diff)
    # Use the bundled fixture cache first so the dep-upgrade benchmark is
    # reproducible offline. Live OSV lookups still happen for any unseen
    # (package, version) tuple, and the result is written next to the
    # fixtures so subsequent runs are free.
    fixture_dir = Path(__file__).parent / "osv_fixtures"
    osv = OSVClient(cache_dir=fixture_dir)
    fitness = DepUpgradeFitness(llm, osv=osv, manifest_packages=packages)

    # Domain-specific Epigenetics: own skill catalog, no learned-skills crossover.
    skill_memory = Epigenetics(str(_domain_skills_path()), learned_skills_path=None)
    skills = skill_memory.retrieve_selected_skills(diff, case_id=case_id)
    if not skills:
        logger.info("dep_upgrade: no skills matched; falling back to all skills.")
        skills = skill_memory.retrieve_selected_skills(diff or "dependency upgrade")

    cluster = await stem.differentiate(
        repo_map=f"manifest packages: {packages}",
        diff=diff,
        skills=skills,
    )
    current_genomes = cluster.genomes
    final_review: ReviewOutput | None = None
    evaluation: EvaluationScore | None = None

    for iteration in range(1, config.max_iterations + 1):
        logger.info("dep_upgrade pass %d: %d reviewers", iteration, len(current_genomes))
        pruned_cluster = await pruner.prune(GenomeCluster(genomes=current_genomes))
        current_genomes = pruned_cluster.genomes
        stress_profiles = await asyncio.gather(
            *[stress_tester.generate_profile(genome, diff) for genome in current_genomes]
        )
        draft_reviews = await asyncio.gather(
            *[
                motor.execute_draft_review(genome, diff, profile, iteration=iteration)
                for genome, profile in zip(current_genomes, stress_profiles)
            ]
        )

        final_peer_tasks = []
        for i, genome in enumerate(current_genomes):
            peers = [draft_reviews[j] for j in range(len(current_genomes)) if j != i]
            final_peer_tasks.append(motor.finalize_review_with_peers(genome, draft_reviews[i], peers))
        finalized_reviews = await asyncio.gather(*final_peer_tasks)

        final_review = await immune.synthesize_and_criticize(finalized_reviews)
        evaluation = await fitness.evaluate(final_review)

        if evaluation.score >= config.target_score:
            logger.info("dep_upgrade: target met at iteration %d (score=%.2f)", iteration, evaluation.score)
            break

        if iteration < config.max_iterations:
            cluster = await mutation.evolve(current_genomes, final_review, evaluation)
            current_genomes = cluster.genomes

    if not final_review or not evaluation:
        raise RuntimeError("dep_upgrade pipeline produced no review.")

    return final_review, evaluation


async def run_dep_upgrade_baseline(
    diff: str,
    config: ReviewStemConfig,
    llm_kwargs: dict | None = None,
) -> tuple[ReviewOutput, int]:
    """Single-prompt baseline for the dep-upgrade domain (no specialization)."""
    llm = LLMClient(config, **(llm_kwargs or {}))
    prompt = f"""
You are a dependency-upgrade safety reviewer. Look at this manifest diff and
flag any concrete risks: known CVEs being introduced or fixed, major-version
breaking changes, license shifts, transitive bloat, and pinning quality.

Cite CVE / GHSA ids when you know them, and name the package and version
involved.

Diff:
{diff}

Return findings with file, line (use the manifest line), severity, and a
concrete suggested fix.
"""
    review = await llm.parse(prompt, schema=ReviewOutput, stage="dep_baseline")
    return review, llm.call_count
