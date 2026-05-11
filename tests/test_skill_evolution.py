"""Tests for skill evolution and persistent learning."""

import json
from pathlib import Path

import pytest

from reviewstem.schemas import ReviewGenome
from reviewstem.skill_evolution import SkillEvolutionEngine, LearnedSkill


@pytest.fixture
def temp_memory_path(tmp_path):
    """Create a temporary memory path for testing."""
    return tmp_path / "learned_skills.json"


@pytest.fixture
def sample_genome():
    """Create a sample reviewer genome for testing."""
    return ReviewGenome(
        persona_name="SQL Injection Specialist",
        focus_areas=["SQL queries", "parameter binding", "user input validation"],
        specific_checks=[
            "Check for string interpolation in SQL queries",
            "Verify parameterized queries are used",
            "Ensure user input is validated"
        ],
        source_skills=["SQL Injection and Unsafe Query Construction Review"],
        risk_profile=["SQL injection", "unsafe query construction"]
    )


def test_skill_evolution_learns_from_success(temp_memory_path, sample_genome):
    """Test that successful reviews create learned skills."""
    engine = SkillEvolutionEngine(temp_memory_path)

    learned = engine.learn_from_success(
        genome=sample_genome,
        case_id="sql_injection",
        fitness_score=0.92,
        min_score_threshold=0.85
    )

    assert learned is not None
    assert learned.skill_name == "SQL Injection Specialist (Learned)"
    assert learned.success_score == 0.92
    assert learned.source_case == "sql_injection"
    assert learned.usage_count == 0
    assert learned.success_count == 0


def test_skill_evolution_ignores_low_fitness(temp_memory_path, sample_genome):
    """Test that low fitness scores don't create learned skills."""
    engine = SkillEvolutionEngine(temp_memory_path)

    learned = engine.learn_from_success(
        genome=sample_genome,
        case_id="test_case",
        fitness_score=0.70,
        min_score_threshold=0.85
    )

    assert learned is None
    assert len(engine.get_learned_skills()) == 0


def test_skill_evolution_persists_to_disk(temp_memory_path, sample_genome):
    """Test that learned skills are saved to disk."""
    engine = SkillEvolutionEngine(temp_memory_path)

    engine.learn_from_success(
        genome=sample_genome,
        case_id="sql_injection",
        fitness_score=0.92
    )

    assert temp_memory_path.exists()
    data = json.loads(temp_memory_path.read_text())
    assert "learned_skills" in data
    assert len(data["learned_skills"]) == 1
    assert data["learned_skills"][0]["skill_name"] == "SQL Injection Specialist (Learned)"


def test_skill_evolution_loads_from_disk(temp_memory_path, sample_genome):
    """Test that learned skills are loaded from disk."""
    # First engine learns a skill
    engine1 = SkillEvolutionEngine(temp_memory_path)
    engine1.learn_from_success(
        genome=sample_genome,
        case_id="sql_injection",
        fitness_score=0.92
    )

    # Second engine loads the learned skill
    engine2 = SkillEvolutionEngine(temp_memory_path)
    learned_skills = engine2.get_learned_skills()

    assert len(learned_skills) == 1
    assert learned_skills[0].skill_name == "SQL Injection Specialist (Learned)"


def test_skill_evolution_tracks_usage(temp_memory_path, sample_genome):
    """Test that skill usage is tracked."""
    engine = SkillEvolutionEngine(temp_memory_path)

    engine.learn_from_success(
        genome=sample_genome,
        case_id="sql_injection",
        fitness_score=0.92
    )

    skill_name = "SQL Injection Specialist (Learned)"
    engine.record_skill_usage(skill_name, success=True)
    engine.record_skill_usage(skill_name, success=True)
    engine.record_skill_usage(skill_name, success=False)

    skills = engine.get_learned_skills()
    assert skills[0].usage_count == 3
    assert skills[0].success_count == 2


def test_skill_evolution_prunes_underperformers(temp_memory_path, sample_genome):
    """Test that underperforming skills are pruned."""
    engine = SkillEvolutionEngine(temp_memory_path)

    # Learn a skill
    engine.learn_from_success(
        genome=sample_genome,
        case_id="sql_injection",
        fitness_score=0.92
    )

    skill_name = "SQL Injection Specialist (Learned)"

    # Record mostly failures
    engine.record_skill_usage(skill_name, success=False)
    engine.record_skill_usage(skill_name, success=False)
    engine.record_skill_usage(skill_name, success=False)
    engine.record_skill_usage(skill_name, success=True)

    # Prune underperformers (success rate = 25% < 50%)
    engine.prune_underperforming_skills(min_success_rate=0.5, min_usage=3)

    assert len(engine.get_learned_skills()) == 0


def test_skill_evolution_statistics(temp_memory_path, sample_genome):
    """Test that evolution statistics are calculated correctly."""
    engine = SkillEvolutionEngine(temp_memory_path)

    engine.learn_from_success(
        genome=sample_genome,
        case_id="sql_injection",
        fitness_score=0.92
    )

    skill_name = "SQL Injection Specialist (Learned)"
    engine.record_skill_usage(skill_name, success=True)
    engine.record_skill_usage(skill_name, success=True)
    engine.record_skill_usage(skill_name, success=False)

    stats = engine.get_skill_statistics()

    assert stats["total_learned_skills"] == 1
    assert stats["total_usage"] == 3
    assert stats["total_success"] == 2
    assert abs(stats["average_success_rate"] - 0.6667) < 0.01


def test_skill_evolution_export_to_catalog(temp_memory_path, sample_genome, tmp_path):
    """Test that learned skills can be exported to catalog format."""
    engine = SkillEvolutionEngine(temp_memory_path)

    engine.learn_from_success(
        genome=sample_genome,
        case_id="sql_injection",
        fitness_score=0.92
    )

    output_path = tmp_path / "exported_skills.json"
    engine.export_to_skill_catalog(output_path)

    assert output_path.exists()
    data = json.loads(output_path.read_text())
    assert len(data) == 1
    assert data[0]["skill_name"] == "SQL Injection Specialist (Learned)"
    assert data[0]["success_score"] == 0.92
    assert "usage_stats" in data[0]
