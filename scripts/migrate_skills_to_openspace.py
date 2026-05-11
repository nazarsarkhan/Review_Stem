#!/usr/bin/env python3
"""
Migrate skills.json to OpenSpace markdown format.

This script converts the existing ReviewStem skills from JSON format
to OpenSpace's markdown format with YAML frontmatter.
"""

import json
import yaml
from pathlib import Path


def migrate_skills():
    """Migrate skills.json to OpenSpace markdown format."""

    # Load existing skills
    skills_json_path = Path("skills/skills.json")
    if not skills_json_path.exists():
        print(f"Error: {skills_json_path} not found")
        return

    with open(skills_json_path) as f:
        old_skills = json.load(f)

    # Create output directory
    skill_dir = Path("skills/openspace")
    skill_dir.mkdir(parents=True, exist_ok=True)

    print(f"Migrating {len(old_skills)} skills to OpenSpace format...")

    for skill in old_skills:
        # Generate skill name from skill_name
        skill_name = skill["skill_name"].lower()
        skill_name = skill_name.replace(" ", "-")
        skill_name = skill_name.replace("/", "-")

        # Create skill directory (OpenSpace expects each skill in its own directory)
        skill_subdir = skill_dir / skill_name
        skill_subdir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_subdir / "SKILL.md"

        # Extract tags from skill name and trigger
        tags = ["security", "review"]
        if "sql" in skill_name.lower():
            tags.append("sql")
        if "auth" in skill_name.lower():
            tags.extend(["auth", "authorization"])
        if "cache" in skill_name.lower():
            tags.append("cache")
        if "admin" in skill_name.lower():
            tags.append("admin")
        if "error" in skill_name.lower():
            tags.append("error-handling")

        # Build frontmatter
        frontmatter = {
            "name": skill_name,
            "description": skill.get("trigger", skill["skill_name"]),
            "trigger": skill.get("trigger", ""),
            "tags": list(set(tags)),
            "backends": ["shell", "mcp"],
            "version": "1.0.0",
            "lineage": {
                "origin": "manual",
                "generation": 1,
                "parent_skill_id": None,
                "change_summary": "Migrated from skills.json"
            },
            "quality_metrics": {
                "total_selections": 0,
                "total_applied": 0,
                "total_completions": 0,
                "success_rate": 0.0
            }
        }

        # Add source_case and success_score if present
        if "source_case" in skill:
            frontmatter["source_case"] = skill["source_case"]
        if "success_score" in skill:
            frontmatter["quality_metrics"]["success_rate"] = skill["success_score"]

        # Build markdown content
        content_parts = [
            "---",
            yaml.dump(frontmatter, default_flow_style=False, sort_keys=False),
            "---",
            "",
            f"# {skill['skill_name']}",
            ""
        ]

        # Add Risk Profile section
        if "risk_profile" in skill and skill["risk_profile"]:
            content_parts.extend([
                "## Risk Profile",
                ""
            ])
            for risk in skill["risk_profile"]:
                content_parts.append(f"- {risk}")
            content_parts.append("")

        # Add Context Plan section
        if "context_plan" in skill and skill["context_plan"]:
            content_parts.extend([
                "## Context Plan",
                ""
            ])
            for i, plan in enumerate(skill["context_plan"], 1):
                content_parts.append(f"{i}. {plan}")
            content_parts.append("")

        # Add Checklist section
        if "checklist" in skill and skill["checklist"]:
            content_parts.extend([
                "## Checklist",
                ""
            ])
            for check in skill["checklist"]:
                content_parts.append(f"- [ ] {check}")
            content_parts.append("")

        # Add Test Templates section
        if "test_templates" in skill and skill["test_templates"]:
            content_parts.extend([
                "## Test Templates",
                ""
            ])
            for test in skill["test_templates"]:
                content_parts.append(f"- {test}")
            content_parts.append("")

        # Write to file
        skill_file.write_text("\n".join(content_parts), encoding="utf-8")
        print(f"[OK] Migrated: {skill_name}")

    print(f"\nMigration complete! {len(old_skills)} skills written to {skill_dir}")
    print("\nNext steps:")
    print("1. Review the generated markdown files")
    print("2. Update reviewstem code to use OpenSpace SkillStore")
    print("3. Run benchmark to verify skills work correctly")


if __name__ == "__main__":
    migrate_skills()
