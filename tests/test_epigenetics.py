from reviewstem.epigenetics import Epigenetics


def test_epigenetics_loads_skill_catalog_schema():
    memory = Epigenetics("skills/skills.json")

    assert memory.traits
    assert all(trait.trigger_context for trait in memory.traits)
    assert all(trait.trait_instruction for trait in memory.traits)


def test_epigenetics_retrieves_relevant_admin_skill():
    memory = Epigenetics("skills/skills.json")

    relevant = memory.retrieve_relevant_skills("diff --git a/src/routes/admin.ts b/src/routes/admin.ts")

    assert relevant
    assert any("admin" in trait.trigger_context.lower() for trait in relevant)


def test_epigenetics_selects_sql_skill_for_query_diff():
    memory = Epigenetics("skills/skills.json")

    selected = memory.retrieve_selected_skills(
        "db.query(`SELECT * FROM users WHERE name = '${name}'`)"
    )

    assert selected
    assert selected[0].skill_name == "SQL Injection and Unsafe Query Construction Review"
    assert "query" in selected[0].matched_terms or "sql" in selected[0].matched_terms


def test_epigenetics_selected_skill_is_auditable():
    memory = Epigenetics("skills/skills.json")

    selected = memory.retrieve_selected_skills("diff --git a/src/routes/admin.ts b/src/routes/admin.ts")

    assert selected[0].total_score > 0
    assert selected[0].matched_fields
    assert selected[0].reason.startswith("Matched")
