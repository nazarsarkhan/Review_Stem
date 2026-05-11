import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from .schemas import MutationDelta, ReviewGenome, ReviewOutput, SelectedSkill, SpecializationState


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_run_id(case_id: str | None = None) -> str:
    prefix = case_id or "review"
    return f"{prefix}-{uuid4().hex[:10]}"


def extract_changed_files(diff: str) -> list[str]:
    files: list[str] = []
    for match in re.finditer(r"^\+\+\+ b/(.+)$", diff, flags=re.MULTILINE):
        path = match.group(1).strip()
        if path != "/dev/null" and path not in files:
            files.append(path)
    return files


def summarize_diff(diff: str) -> str:
    changed = extract_changed_files(diff)
    additions = sum(1 for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
    deletions = sum(1 for line in diff.splitlines() if line.startswith("-") and not line.startswith("---"))
    hints = []
    lowered = diff.lower()
    for label, terms in {
        "database/query": ("select ", "query(", "sql", "db."),
        "admin/auth": ("admin", "auth", "middleware"),
        "cache": ("cache", "redis", "invalidate"),
        "async/error": ("catch", "await", "promise", "async"),
    }.items():
        if any(term in lowered for term in terms):
            hints.append(label)
    return f"{len(changed)} changed files, +{additions}/-{deletions}, signals: {', '.join(hints) or 'general'}"


def summarize_repo_map(repo_map: str, max_lines: int = 18) -> str:
    lines = [line for line in repo_map.splitlines() if line.strip()]
    suffix = "" if len(lines) <= max_lines else f"\n... ({len(lines) - max_lines} more entries)"
    return "\n".join(lines[:max_lines]) + suffix


def summarize_review(review: ReviewOutput) -> str:
    severities = {}
    for comment in review.comments:
        severities[comment.severity] = severities.get(comment.severity, 0) + 1
    severity_text = ", ".join(f"{key}:{value}" for key, value in sorted(severities.items())) or "no comments"
    return f"{len(review.comments)} comments ({severity_text}). {review.overall_summary[:220]}"


def compare_genomes(old: Iterable[ReviewGenome], new: Iterable[ReviewGenome]) -> MutationDelta:
    old_by_name = {g.persona_name: g for g in old}
    new_by_name = {g.persona_name: g for g in new}

    delta = MutationDelta(
        added_reviewers=sorted(set(new_by_name) - set(old_by_name)),
        removed_reviewers=sorted(set(old_by_name) - set(new_by_name)),
    )

    shared = sorted(set(old_by_name) & set(new_by_name))
    for name in shared:
        old_genome = old_by_name[name]
        new_genome = new_by_name[name]
        _record_list_change(delta.changed_focus_areas, name, old_genome.focus_areas, new_genome.focus_areas)
        _record_list_change(delta.changed_specific_checks, name, old_genome.specific_checks, new_genome.specific_checks)
        _record_list_change(delta.changed_source_skills, name, old_genome.source_skills, new_genome.source_skills)
        _record_list_change(delta.changed_risk_areas, name, old_genome.risk_profile, new_genome.risk_profile)

    if len(old_by_name) == len(new_by_name):
        old_names = sorted(old_by_name)
        new_names = sorted(new_by_name)
        for old_name, new_name in zip(old_names, new_names):
            if old_name != new_name:
                delta.changed_reviewer_names.append(f"{old_name} -> {new_name}")

    return delta


def _record_list_change(target: dict, name: str, old_values: list[str], new_values: list[str]) -> None:
    added = sorted(set(new_values) - set(old_values))
    removed = sorted(set(old_values) - set(new_values))
    if added or removed:
        target[name] = {"added": added, "removed": removed}


def infer_reviewer_skill_map(genomes: Iterable[ReviewGenome], skills: Iterable[SelectedSkill]) -> dict[str, list[str]]:
    skill_names = [skill.skill_name for skill in skills]
    mapping: dict[str, list[str]] = {}
    for genome in genomes:
        explicit = [name for name in genome.source_skills if name in skill_names]
        text = " ".join([genome.persona_name, *genome.focus_areas, *genome.specific_checks]).lower()
        inferred = [name for name in skill_names if name.lower() in text]
        mapping[genome.persona_name] = sorted(set(explicit + inferred))
    return mapping


def write_specialization_state(state: SpecializationState, output_dir: Path, case_id: str | None = None) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"_{case_id}" if case_id else ""
    json_path = output_dir / f"specialization_state{suffix}.json"
    md_path = output_dir / f"specialization_state{suffix}.md"
    json_path.write_text(json.dumps(state.model_dump(mode="json"), indent=2), encoding="utf-8")
    md_path.write_text(format_specialization_markdown(state), encoding="utf-8")
    return json_path, md_path


def format_specialization_markdown(state: SpecializationState) -> str:
    lines = [
        "# ReviewStem Specialization State",
        "",
        f"- Run: `{state.run_id}`",
        f"- Mode: `{state.mode}`",
        f"- Case: `{state.case_id or 'live_review'}`",
        f"- Model: `{state.model}`",
        f"- Target score: `{state.target_score}`",
        f"- Stop reason: {state.stop_reason or 'not recorded'}",
        "",
        "## Selected Skills",
    ]
    for skill in state.selected_skills:
        fallback = " fallback" if skill.fallback else ""
        lines.append(f"- `{skill.skill_name}` score={skill.total_score:.2f}{fallback}: {skill.reason}")

    lines.extend(["", "## Iterations"])
    for item in state.iterations:
        lines.append(
            f"- Pass {item.iteration}: score={item.fitness_score:.2f}, "
            f"reviewers={len(item.pruned_reviewer_architecture)}, "
            f"mutation={'yes' if item.mutation_applied else 'no'}"
        )
        if item.mutation_reason:
            lines.append(f"  Reason: {item.mutation_reason}")

    lines.extend(["", "## Tool Use"])
    if not state.tool_use:
        lines.append("- No read_file tool calls recorded.")
    for event in state.tool_use:
        status = "ok" if event.success else f"failed: {event.error}"
        lines.append(f"- Pass {event.iteration} `{event.reviewer}` read `{event.path}` ({status}, {event.characters_returned} chars)")

    return "\n".join(lines) + "\n"
