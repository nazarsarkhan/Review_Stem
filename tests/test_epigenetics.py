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
