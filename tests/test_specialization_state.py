from reviewstem.schemas import ReviewGenome, SelectedSkill, SpecializationState
from reviewstem.state import compare_genomes, new_run_id, utc_timestamp


def test_specialization_state_serializes_to_json():
    state = SpecializationState(
        run_id=new_run_id("unit"),
        mode="benchmark",
        case_id="unit",
        timestamp=utc_timestamp(),
        target_score=0.9,
        max_iterations=2,
        model="test-model",
        selected_skills=[
            SelectedSkill(
                skill_name="Unit Skill",
                trigger_context="unit",
                trait_instruction="check unit behavior",
                total_score=1.0,
            )
        ],
    )

    payload = state.model_dump_json()

    assert "runtime" not in payload
    assert "Unit Skill" in payload


def test_compare_genomes_reports_changed_checks_and_reviewers():
    old = [
        ReviewGenome(
            persona_name="Security Reviewer",
            focus_areas=["auth"],
            specific_checks=["check middleware"],
        )
    ]
    new = [
        ReviewGenome(
            persona_name="Security Reviewer",
            focus_areas=["auth", "routing"],
            specific_checks=["check middleware", "check mount order"],
        ),
        ReviewGenome(
            persona_name="Cache Reviewer",
            focus_areas=["cache"],
            specific_checks=["check invalidation"],
        ),
    ]

    delta = compare_genomes(old, new)

    assert delta.added_reviewers == ["Cache Reviewer"]
    assert "Security Reviewer" in delta.changed_focus_areas
    assert "Security Reviewer" in delta.changed_specific_checks
