import json
from pathlib import Path
import re
from typing import List

from .embeddings import EmbeddingProvider, cosine_sim
from .logger import logger
from .schemas import LearnedTrait, SelectedSkill
from .skill_evolution import SkillEvolutionEngine


# Weight of cosine similarity vs. term matching in the hybrid retrieval score.
# 0.7/0.3 keeps semantic similarity as the dominant signal while preserving the
# interpretable term-match reasons that show up in the audit trail.
EMBEDDING_WEIGHT = 0.7
TERM_WEIGHT = 0.3
# Per-skill score this contributes per unit of cosine similarity (in [0, 1]).
COSINE_SCORE_SCALE = 10.0


class Epigenetics:
    def __init__(
        self,
        memory_file: str = "skills.json",
        learned_skills_path: str | None = ".reviewstem/learned_skills.json",
        embedding_provider: EmbeddingProvider | None = None,
    ):
        self.memory_file = Path(memory_file)
        self.traits: List[LearnedTrait] = []
        self.skill_catalog: list[dict] = []
        self.evolution_engine: SkillEvolutionEngine | None = (
            SkillEvolutionEngine(Path(learned_skills_path)) if learned_skills_path else None
        )
        self.embedding_provider = embedding_provider
        self._skill_embeddings: list[list[float] | None] = []
        self._load()
        self._precompute_embeddings()

    def _precompute_embeddings(self) -> None:
        """Embed every skill in the catalog at load time and cache the result.

        Falls back silently if the embedding provider is missing or refuses;
        downstream retrieval will use pure term matching.
        """
        if self.embedding_provider is None or not self.skill_catalog:
            self._skill_embeddings = [None] * len(self.skill_catalog)
            return
        skill_texts = [_skill_embedding_text(item) for item in self.skill_catalog]
        self._skill_embeddings = self.embedding_provider.embed_batch(skill_texts)
        n_ok = sum(1 for v in self._skill_embeddings if v is not None)
        if n_ok:
            logger.info("Epigenetics: Pre-computed embeddings for %d/%d skills.", n_ok, len(self.skill_catalog))

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
        """Return deterministic, auditable scored skills for the current review environment.

        Hybrid scoring: when an embedding provider is wired in and successfully
        produced a query vector, the final score is
            EMBEDDING_WEIGHT * (cosine * COSINE_SCORE_SCALE) + TERM_WEIGHT * term_score
        Otherwise it's pure term matching. Term match reasons are still recorded
        so the audit trail shows *why* a skill was selected, not just *that* it was.
        """
        diff_terms = set(_terms(f"{diff}\n{case_id or ''}"))
        repo_terms = set(_terms(repo_signals)) - diff_terms

        query_vec: list[float] | None = None
        if self.embedding_provider is not None:
            query_text = _query_embedding_text(diff, repo_signals, case_id)
            query_vec = self.embedding_provider.embed(query_text)

        scored: list[SelectedSkill] = []
        for idx, item in enumerate(self.skill_catalog):
            selected = self._score_skill(item, diff_terms, repo_terms, case_id)
            term_score = selected.total_score
            cosine = 0.0
            if query_vec is not None and idx < len(self._skill_embeddings):
                skill_vec = self._skill_embeddings[idx]
                if skill_vec is not None:
                    cosine = cosine_sim(query_vec, skill_vec)

            if query_vec is not None and any(v is not None for v in self._skill_embeddings):
                hybrid = EMBEDDING_WEIGHT * (cosine * COSINE_SCORE_SCALE) + TERM_WEIGHT * term_score
                selected = selected.model_copy(update={"total_score": round(hybrid, 3)})
                if cosine > 0.2 and not selected.reason.startswith("Matched"):
                    selected = selected.model_copy(
                        update={"reason": f"Semantic match (cos={cosine:.2f}); {selected.reason}"}
                    )
                elif cosine > 0.2:
                    selected = selected.model_copy(
                        update={"reason": selected.reason + f"; semantic cos={cosine:.2f}"}
                    )

            if selected.total_score > 0:
                scored.append(selected)

        scored.sort(key=lambda skill: (-skill.total_score, skill.skill_name.lower()))
        deduped = _dedupe_skills(scored)
        if deduped:
            mode = "hybrid (cos+term)" if query_vec is not None else "term-only"
            logger.info("Epigenetics: Retrieved %s skills via %s.", len(deduped[:limit]), mode)
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


def _skill_embedding_text(item: dict) -> str:
    """Build the text to embed for a skill catalog entry.

    Concatenates the high-signal fields (name, trigger, checklist) and skips
    boilerplate (test templates). Trimmed to 4000 chars so we never blow the
    embedding model's input cap.
    """
    parts: list[str] = []
    for field in ("skill_name", "trigger", "risk_profile", "checklist"):
        value = item.get(field)
        if isinstance(value, list):
            parts.append("\n".join(str(x) for x in value))
        elif value:
            parts.append(str(value))
    return "\n\n".join(p for p in parts if p)[:4000]


def _query_embedding_text(diff: str, repo_signals: str, case_id: str | None) -> str:
    """Build the query string to embed for retrieval.

    Diff is the dominant signal; we keep enough repo context that retrieval
    can disambiguate between similar diffs in different repos.
    """
    head = f"case: {case_id}\n" if case_id else ""
    diff_chunk = diff[:3000]
    repo_chunk = repo_signals[:500]
    return f"{head}{diff_chunk}\n\n{repo_chunk}"


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
