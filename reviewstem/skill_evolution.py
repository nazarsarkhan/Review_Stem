"""Persistent skill learning and evolution across review sessions."""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

from .logger import logger
from .schemas import ReviewGenome


class LearnedSkill(BaseModel):
    """A skill learned from a successful review session."""

    skill_name: str = Field(..., description="Name of the learned skill")
    trigger: str = Field(..., description="When to use this skill")
    risk_profile: List[str] = Field(..., description="Risk areas this skill addresses")
    context_plan: List[str] = Field(..., description="How to gather context")
    checklist: List[str] = Field(..., description="Specific checks to perform")
    test_templates: List[str] = Field(..., description="Test case templates")
    source_case: str = Field(..., description="Case ID that generated this skill")
    success_score: float = Field(..., description="Fitness score achieved")
    learned_at: str = Field(..., description="ISO timestamp when skill was learned")
    review_genome: ReviewGenome = Field(..., description="Original reviewer genome")
    usage_count: int = Field(default=0, description="Number of times this skill was used")
    success_count: int = Field(default=0, description="Number of successful uses")


class SkillMemory(BaseModel):
    """Persistent memory of learned skills."""

    learned_skills: List[LearnedSkill] = Field(default_factory=list)
    last_updated: str = Field(default_factory=lambda: datetime.now().isoformat())


class SkillEvolutionEngine:
    """Manages persistent skill learning and evolution."""

    def __init__(self, memory_path: Path):
        self.memory_path = memory_path
        self.memory_path.parent.mkdir(parents=True, exist_ok=True)
        self.memory = self._load_memory()

    def _load_memory(self) -> SkillMemory:
        """Load skill memory from disk."""
        if self.memory_path.exists():
            try:
                data = json.loads(self.memory_path.read_text(encoding="utf-8"))
                return SkillMemory.model_validate(data)
            except Exception as e:
                logger.warning(f"Failed to load skill memory: {e}. Starting fresh.")
                return SkillMemory()
        return SkillMemory()

    def _save_memory(self):
        """Save skill memory to disk."""
        try:
            self.memory.last_updated = datetime.now().isoformat()
            self.memory_path.write_text(
                self.memory.model_dump_json(indent=2),
                encoding="utf-8"
            )
            logger.info(f"Saved skill memory with {len(self.memory.learned_skills)} learned skills")
        except Exception as e:
            logger.error(f"Failed to save skill memory: {e}")

    def learn_from_success(
        self,
        genome: ReviewGenome,
        case_id: str,
        fitness_score: float,
        min_score_threshold: float = 0.85
    ) -> Optional[LearnedSkill]:
        """Learn a new skill from a successful review."""
        if fitness_score < min_score_threshold:
            logger.debug(f"Fitness score {fitness_score} below threshold {min_score_threshold}, not learning")
            return None

        # Check if we already have a similar skill
        for existing in self.memory.learned_skills:
            if existing.review_genome.persona_name == genome.persona_name:
                logger.debug(f"Similar skill already exists: {existing.skill_name}")
                return None

        # Create new learned skill
        skill_name = f"{genome.persona_name} (Learned)"
        trigger = f"Use when reviewing {', '.join(genome.focus_areas[:3])}"

        learned_skill = LearnedSkill(
            skill_name=skill_name,
            trigger=trigger,
            risk_profile=genome.risk_profile,
            context_plan=[
                f"Focus on {area}" for area in genome.focus_areas[:5]
            ],
            checklist=genome.specific_checks,
            test_templates=[
                "Verify the identified issue with a test case",
                "Test edge cases and boundary conditions",
                "Ensure regression tests prevent reintroduction"
            ],
            source_case=case_id,
            success_score=fitness_score,
            learned_at=datetime.now().isoformat(),
            review_genome=genome,
            usage_count=0,
            success_count=0
        )

        self.memory.learned_skills.append(learned_skill)
        self._save_memory()

        logger.info(f"Learned new skill: {skill_name} (score: {fitness_score:.2f})")
        return learned_skill

    def get_learned_skills(self) -> List[LearnedSkill]:
        """Get all learned skills."""
        return self.memory.learned_skills

    def record_skill_usage(self, skill_name: str, success: bool):
        """Record usage of a learned skill."""
        for skill in self.memory.learned_skills:
            if skill.skill_name == skill_name:
                skill.usage_count += 1
                if success:
                    skill.success_count += 1
                self._save_memory()
                logger.debug(f"Recorded usage for {skill_name}: {skill.success_count}/{skill.usage_count}")
                break

    def prune_underperforming_skills(self, min_success_rate: float = 0.5, min_usage: int = 3):
        """Remove skills that consistently underperform."""
        before_count = len(self.memory.learned_skills)

        self.memory.learned_skills = [
            skill for skill in self.memory.learned_skills
            if skill.usage_count < min_usage or
               (skill.success_count / skill.usage_count) >= min_success_rate
        ]

        after_count = len(self.memory.learned_skills)
        if before_count > after_count:
            self._save_memory()
            logger.info(f"Pruned {before_count - after_count} underperforming skills")

    def export_to_skill_catalog(self, output_path: Path):
        """Export learned skills to the main skill catalog format."""
        catalog_skills = []

        for learned in self.memory.learned_skills:
            catalog_skill = {
                "skill_name": learned.skill_name,
                "trigger": learned.trigger,
                "risk_profile": learned.risk_profile,
                "context_plan": learned.context_plan,
                "checklist": learned.checklist,
                "test_templates": learned.test_templates,
                "source_case": learned.source_case,
                "success_score": learned.success_score,
                "learned_at": learned.learned_at,
                "usage_stats": {
                    "usage_count": learned.usage_count,
                    "success_count": learned.success_count,
                    "success_rate": learned.success_count / learned.usage_count if learned.usage_count > 0 else 0.0
                }
            }
            catalog_skills.append(catalog_skill)

        output_path.write_text(
            json.dumps(catalog_skills, indent=2),
            encoding="utf-8"
        )
        logger.info(f"Exported {len(catalog_skills)} learned skills to {output_path}")

    def get_skill_statistics(self) -> dict:
        """Get statistics about learned skills."""
        total_skills = len(self.memory.learned_skills)
        total_usage = sum(s.usage_count for s in self.memory.learned_skills)
        total_success = sum(s.success_count for s in self.memory.learned_skills)

        avg_success_rate = 0.0
        if total_usage > 0:
            avg_success_rate = total_success / total_usage

        return {
            "total_learned_skills": total_skills,
            "total_usage": total_usage,
            "total_success": total_success,
            "average_success_rate": avg_success_rate,
            "last_updated": self.memory.last_updated
        }
