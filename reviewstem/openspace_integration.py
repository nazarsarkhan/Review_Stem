"""
OpenSpace integration for ReviewStem.

This module provides the bridge between ReviewStem's review system
and OpenSpace's skill learning framework.
"""

import json
import logging
from pathlib import Path
from typing import List, Optional

from openspace.skill_engine import SkillStore, SkillRegistry
from openspace.skill_engine.types import (
    ExecutionAnalysis,
    EvolutionSuggestion,
    EvolutionType,
)

from .llm_client import LLMClient
from .schemas import (
    DeterministicPenalty,
    LearnedTrait,
    ReviewOutput,
    SelectedSkill,
)

logger = logging.getLogger("ReviewStem")


class ReviewStemSkillEngine:
    """Manages skill retrieval with OpenSpace quality metrics."""

    def __init__(self, skill_dirs: List[Path], llm: LLMClient):
        self.llm = llm
        self.store = SkillStore()
        # SkillRegistry expects Path objects, not strings
        self.registry = SkillRegistry(skill_dirs=skill_dirs)
        self.registry.discover()
        logger.info("OpenSpace SkillEngine initialized with %d skill directories", len(skill_dirs))

    async def sync_skills(self):
        """Sync discovered skills to the persistent store."""
        skills = self.registry.list_skills()
        await self.store.sync_from_registry(skills)
        logger.info("Synced %d skills to SkillStore", len(skills))

    def retrieve_skills(
        self,
        diff: str,
        repo_signals: str = "",
        case_id: Optional[str] = None,
        limit: int = 5,
    ) -> List[SelectedSkill]:
        """
        Retrieve skills using OpenSpace quality metrics.

        This is a simplified version that uses the existing epigenetics
        scoring logic but will be enhanced with LLM-based selection.
        """
        # Get quality metrics from store
        quality_summary = self.store.get_summary(active_only=True)
        quality_map = {
            row["skill_id"]: {
                "total_selections": row["total_selections"],
                "total_applied": row["total_applied"],
                "total_completions": row["total_completions"],
                "success_rate": row["total_completions"] / max(1, row["total_applied"]),
            }
            for row in quality_summary
        }

        # For now, use simplified selection based on skill metadata
        # TODO: Implement LLM-based selection with quality awareness
        selected = []
        all_skills = self.registry.list_skills()

        for skill in all_skills:
            # Simple keyword matching for now
            skill_text = f"{skill.name} {skill.description}".lower()
            diff_lower = diff.lower()

            score = 0.0
            if "sql" in diff_lower and "sql" in skill_text:
                score += 3.0
            if "auth" in diff_lower and "auth" in skill_text:
                score += 3.0
            if "cache" in diff_lower and "cache" in skill_text:
                score += 3.0
            if "admin" in diff_lower and "admin" in skill_text:
                score += 2.5
            if "error" in diff_lower and "error" in skill_text:
                score += 2.0

            # Boost by quality metrics
            if skill.skill_id in quality_map:
                quality = quality_map[skill.skill_id]
                score += quality["success_rate"] * 0.5

            if score > 0:
                selected.append(
                    SelectedSkill(
                        skill_name=skill.name,
                        trigger_context=skill.description,
                        trait_instruction=skill.description,
                        total_score=round(score, 2),
                        matched_terms=[],
                        matched_fields={},
                        reason=f"Matched with score {score:.2f}",
                        source_case=None,
                        success_score=quality_map.get(skill.skill_id, {}).get("success_rate"),
                        fallback=False,
                        risk_profile=[],
                        context_plan=[],
                        checklist=[],
                        test_templates=[],
                    )
                )

        # Sort by score and return top N
        selected.sort(key=lambda s: -s.total_score)
        return selected[:limit]

    def record_skill_selection(self, skill_id: str, task_id: str):
        """Record that a skill was selected for a task."""
        self.store.record_skill_selection(skill_id, task_id)

    def record_skill_applied(self, skill_id: str, task_id: str):
        """Record that a skill was actually applied in the review."""
        self.store.record_skill_applied(skill_id, task_id)

    def record_skill_completion(self, skill_id: str, task_id: str):
        """Record that a skill led to successful completion."""
        self.store.record_skill_completion(skill_id, task_id)


class ReviewStemExecutionAnalyzer:
    """Analyzes review execution to determine skill evolution needs."""

    def __init__(self, store: SkillStore):
        self.store = store

    def analyze_review_execution(
        self,
        run_id: str,
        selected_skills: List[SelectedSkill],
        review_output: ReviewOutput,
        fitness_score: float,
        deterministic_penalties: List[DeterministicPenalty],
        target_score: float,
    ) -> ExecutionAnalysis:
        """
        Analyze review execution and determine evolution candidates.

        Returns an ExecutionAnalysis with evolution suggestions.
        """
        overall_success = fitness_score >= target_score

        # Identify which skills contributed to success/failure
        skill_performance = {}
        for skill in selected_skills:
            # Simple heuristic: skill was applied if its name appears in review
            skill_applied = self._skill_was_applied(skill, review_output)

            if skill_applied:
                # Record application
                skill_performance[skill.skill_name] = "applied"

                if overall_success:
                    skill_performance[skill.skill_name] = "success"
                else:
                    skill_performance[skill.skill_name] = "needs_fix"
            else:
                skill_performance[skill.skill_name] = "not_applied"

        # Determine evolution candidates
        candidate_for_evolution = False
        evolution_suggestions = []

        if not overall_success:
            # FIX: Skills that were applied but led to failures
            for skill_name, perf in skill_performance.items():
                if perf == "needs_fix":
                    candidate_for_evolution = True
                    evolution_suggestions.append({
                        "type": "FIX",
                        "skill_name": skill_name,
                        "reason": f"Skill applied but fitness {fitness_score:.2f} < target {target_score:.2f}",
                        "penalties": [p.model_dump() for p in deterministic_penalties],
                    })

        # CAPTURED: Novel successful pattern not covered by existing skills
        if overall_success and not selected_skills:
            candidate_for_evolution = True
            evolution_suggestions.append({
                "type": "CAPTURED",
                "reason": "Successful review without skill guidance - novel pattern detected",
                "review_summary": review_output.model_dump(),
            })

        analysis = ExecutionAnalysis(
            task_id=run_id,
            overall_success=overall_success,
            candidate_for_evolution=candidate_for_evolution,
            analysis_notes=f"Fitness: {fitness_score:.2f}, Skills applied: {sum(1 for p in skill_performance.values() if p != 'not_applied')}/{len(selected_skills)}",
        )

        # Store evolution suggestions in analysis notes (OpenSpace doesn't have this field)
        if evolution_suggestions:
            analysis.analysis_notes += f"\nEvolution suggestions: {json.dumps(evolution_suggestions)}"

        self.store.save_analysis(analysis)
        return analysis

    def _skill_was_applied(self, skill: SelectedSkill, review: ReviewOutput) -> bool:
        """
        Heuristic to determine if a skill was actually applied.

        Checks if skill-related keywords appear in the review findings.
        """
        skill_keywords = skill.skill_name.lower().split("-")
        review_text = " ".join([
            c.issue_description.lower() + " " + c.suggested_fix.lower()
            for c in review.comments
        ])

        # Skill was applied if at least 2 keywords appear in review
        matches = sum(1 for keyword in skill_keywords if keyword in review_text)
        return matches >= 2


class ReviewStemEvolutionEngine:
    """Manages skill evolution using OpenSpace's SkillEvolver."""

    def __init__(self, store: SkillStore, registry: SkillRegistry, llm: LLMClient):
        # OpenSpace's SkillEvolver expects an LLMClient with specific interface
        # For now, we'll skip automatic evolution and implement it manually
        self.store = store
        self.registry = registry
        self.llm = llm
        logger.info("ReviewStem EvolutionEngine initialized")

    async def evolve_skills(
        self,
        analysis: ExecutionAnalysis,
        review_output: ReviewOutput,
        deterministic_penalties: List[DeterministicPenalty],
    ) -> List[dict]:
        """
        Evolve skills based on execution analysis.

        Returns list of evolved skill records.
        """
        evolved_skills = []

        # Parse evolution suggestions from analysis notes
        if "Evolution suggestions:" not in analysis.analysis_notes:
            return evolved_skills

        suggestions_json = analysis.analysis_notes.split("Evolution suggestions: ")[1]
        suggestions = json.loads(suggestions_json)

        for suggestion in suggestions:
            if suggestion["type"] == "FIX":
                # For now, log the need for a fix
                # Full implementation would use SkillEvolver
                logger.info(
                    "Skill '%s' needs FIX evolution: %s",
                    suggestion["skill_name"],
                    suggestion["reason"],
                )
                evolved_skills.append({
                    "skill_name": suggestion["skill_name"],
                    "evolution_type": "FIX",
                    "reason": suggestion["reason"],
                    "status": "logged",
                })

            elif suggestion["type"] == "CAPTURED":
                # Extract pattern from successful review
                logger.info("Novel pattern detected for CAPTURED evolution")
                evolved_skills.append({
                    "skill_name": "captured-pattern",
                    "evolution_type": "CAPTURED",
                    "reason": suggestion["reason"],
                    "status": "logged",
                })

        return evolved_skills

    def _extract_pattern(self, review_summary: dict) -> str:
        """Extract reusable pattern from successful review."""
        comments = review_summary.get("comments", [])

        # Group by severity
        patterns = {}
        for comment in comments:
            severity = comment.get("severity", "Unknown")
            if severity not in patterns:
                patterns[severity] = []
            patterns[severity].append({
                "issue": comment.get("issue_description"),
                "fix": comment.get("suggested_fix"),
            })

        return json.dumps(patterns, indent=2)
