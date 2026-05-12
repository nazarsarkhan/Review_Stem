import json
from pathlib import Path
import re
from typing import List

from .logger import logger
from .schemas import LearnedTrait, SelectedSkill
from .skill_evolution import SkillEvolutionEngine


class Epigenetics:
    def __init__(self, memory_file: str = "skills.json", learned_skills_path: str | None = ".reviewstem/learned_skills.json"):
        self.memory_file = Path(memory_file)
        self.traits: List[LearnedTrait] = []
        self.skill_catalog: list[dict] = []
        self.evolution_engine: SkillEvolutionEngine | None = (
            SkillEvolutionEngine(Path(learned_skills_path)) if learned_skills_path else None
        )
        self._load()

    def _load(self):
        if self.memory_file.exists():
            try:
                with self.memory_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                self.skill_catalog = data if isinstance(data, list) else []
                self.traits = [self._to_trait(item) for item in data]
                logger.info("Epigenetics: Loaded %s traits from memory.", len(self.traits))
            except Exception as e:
                logger.error("Epigenetics: Failed to load memory: %s", e)

        if self.evolution_engine is None:
            return

        # Only promoted (corroborated) skills participate in retrieval;
        # candidates accumulate confirmation in the background.
        learned_skills = self.evolution_engine.get_promoted_skills()
        for learned in learned_skills:
            learned_dict = {
                "skill_name": learned.skill_name,
                "trigger": learned.trigger,
                "risk_profile": learned.risk_profile,
                "context_plan": learned.context_plan,
                "checklist": learned.checklist,
                "test_templates": learned.test_templates,
                "source_case": learned.source_case,
                "success_score": learned.success_score,
            }
            self.skill_catalog.append(learned_dict)

        if learned_skills:
            logger.info("Epigenetics: Loaded %s learned skills from evolution engine.", len(learned_skills))

    def save_trait(self, trait: LearnedTrait):
        """Save a new successful trait to memory."""
        if any(t.trait_instruction == trait.trait_instruction for t in self.traits):
            return

        self.traits.append(trait)
        logger.info(
            "Epigenetics: Saving new trait for '%s'.",
            trait.trigger_context,
        )
        try:
            with self.memory_file.open("w", encoding="utf-8") as f:
                json.dump([t.model_dump() for t in self.traits], f, indent=2)
        except Exception as e:
            logger.error("Epigenetics: Failed to save memory: %s", e)

    def retrieve_relevant_skills(self, diff: str) -> List[LearnedTrait]:
        """Retrieve skills relevant to the current diff."""
        return [
            LearnedTrait(trigger_context=skill.trigger_context, trait_instruction=skill.trait_instruction)
            for skill in self.retrieve_selected_skills(diff)
        ]

    def retrieve_selected_skills(
        self,
        diff: str,
        repo_signals: str = "",
        case_id: str | None = None,
        limit: int = 5,
    ) -> list[SelectedSkill]:
        """Return deterministic, auditable scored skills for the current review environment."""
        diff_terms = set(_terms(f"{diff}\n{case_id or ''}"))
        repo_terms = set(_terms(repo_signals)) - diff_terms
        scored: list[SelectedSkill] = []

        for item in self.skill_catalog:
            selected = self._score_skill(item, diff_terms, repo_terms, case_id)
            if selected.total_score > 0:
                scored.append(selected)

        scored.sort(key=lambda skill: (-skill.total_score, skill.skill_name.lower()))
        deduped = _dedupe_skills(scored)
        if deduped:
            logger.info("Epigenetics: Retrieved %s scored skills.", len(deduped[:limit]))
        return deduped[:limit]

    def _score_skill(
        self,
        item: dict,
        diff_terms: set[str],
        repo_terms: set[str],
        case_id: str | None,
    ) -> SelectedSkill:
        weights = {
            "skill_name": 3.0,
            "trigger": 3.0,
            "risk_profile": 2.5,
            "context_plan": 1.5,
            "checklist": 2.0,
            "test_templates": 1.0,
        }
        matched_fields: dict[str, list[str]] = {}
        score = 0.0

        for field, weight in weights.items():
            values = item.get(field, [])
            if isinstance(values, str):
                values = [values]
            field_terms = set(_terms(" ".join(str(value) for value in values)))
            diff_matches = field_terms & diff_terms
            repo_matches = field_terms & repo_terms
            matches = sorted(diff_matches | repo_matches)
            if matches:
                matched_fields[field] = matches
                score += weight * len(diff_matches)
                score += weight * 0.2 * len(repo_matches)

        source_case = item.get("source_case")
        if case_id and source_case and case_id.lower() in str(source_case).lower():
            matched_fields["source_case"] = [case_id]
            score += 2.0

        success_score = item.get("success_score")
        if score > 0 and isinstance(success_score, (int, float)):
            score += min(1.0, max(0.0, float(success_score))) * 0.25

        matched_terms = sorted({term for terms in matched_fields.values() for term in terms})
        trait = self._to_trait(item)
        name = str(item.get("skill_name") or item.get("trigger") or "Unnamed skill")
        reason = "Matched " + ", ".join(
            f"{field}: {', '.join(terms[:5])}" for field, terms in matched_fields.items()
        ) if matched_fields else "No deterministic match."

        return SelectedSkill(
            skill_name=name,
            trigger_context=trait.trigger_context,
            trait_instruction=trait.trait_instruction,
            total_score=round(score, 2),
            matched_terms=matched_terms,
            matched_fields=matched_fields,
            reason=reason,
            source_case=str(source_case) if source_case else None,
            success_score=float(success_score) if isinstance(success_score, (int, float)) else None,
            fallback=False,
            risk_profile=[str(value) for value in item.get("risk_profile", [])],
            context_plan=[str(value) for value in item.get("context_plan", [])],
            checklist=[str(value) for value in item.get("checklist", [])],
            test_templates=[str(value) for value in item.get("test_templates", [])],
        )

    @staticmethod
    def _to_trait(item: dict) -> LearnedTrait:
        if "trigger_context" in item and "trait_instruction" in item:
            return LearnedTrait(**item)

        trigger = item.get("trigger") or item.get("skill_name") or "general review"
        checklist = item.get("checklist") or []
        risk_profile = item.get("risk_profile") or []
        test_templates = item.get("test_templates") or []
        details = [*risk_profile, *checklist, *test_templates]
        instruction = "; ".join(str(value) for value in details if value)
        if not instruction:
            instruction = f"Apply review guidance for {trigger}."
        return LearnedTrait(trigger_context=str(trigger), trait_instruction=instruction)


STOP_TERMS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "when",
    "where",
    "into",
    "review",
    "code",
    "file",
    "files",
    "path",
    "paths",
    "test",
    "tests",
}


def _terms(text: str) -> list[str]:
    return [
        term
        for term in re.findall(r"[a-zA-Z][a-zA-Z0-9_]{2,}", text.lower())
        if term not in STOP_TERMS
    ]


def _dedupe_skills(skills: list[SelectedSkill]) -> list[SelectedSkill]:
    selected: list[SelectedSkill] = []
    seen_families: set[str] = set()
    for skill in skills:
        family = _skill_family(skill.skill_name)
        if family in seen_families:
            continue
        selected.append(skill)
        seen_families.add(family)
    return selected


def _skill_family(name: str) -> str:
    lower = name.lower()
    if "low-context" in lower or "triage" in lower:
        return "low-context"
    if "swallowed" in lower or "error" in lower or "import" in lower:
        return "swallowed-error"
    if "admin" in lower or "auth" in lower:
        return "admin-auth"
    if "cache" in lower:
        return "cache"
    if "sql" in lower or "query" in lower:
        return "sql"
    return re.sub(r"[^a-z0-9]+", "-", lower).strip("-")
