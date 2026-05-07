import json
import logging
from pathlib import Path
from typing import List

from .schemas import LearnedTrait

logger = logging.getLogger("ReviewStem")


class Epigenetics:
    def __init__(self, memory_file: str = "skills.json"):
        self.memory_file = Path(memory_file)
        self.traits: List[LearnedTrait] = []
        self._load()

    def _load(self):
        if self.memory_file.exists():
            try:
                with self.memory_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                self.traits = [self._to_trait(item) for item in data]
                logger.info("Epigenetics: Loaded %s traits from memory.", len(self.traits))
            except Exception as e:
                logger.error("Epigenetics: Failed to load memory: %s", e)

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
        relevant = []
        diff_lower = diff.lower()

        for trait in self.traits:
            keywords = set(trait.trigger_context.lower().split())
            match_score = sum(1 for kw in keywords if kw in diff_lower and len(kw) > 3)
            if match_score > 0:
                relevant.append(trait)

        if relevant:
            logger.info("Epigenetics: Retrieved %s relevant traits.", len(relevant))
        return relevant

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
