from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ReviewGenome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    persona_name: str = Field(
        ...,
        description="The specialized persona for this reviewer.",
    )
    focus_areas: List[str] = Field(
        ...,
        description="Specific areas of the code to scrutinize.",
    )
    specific_checks: List[str] = Field(
        ...,
        description="Exact instructions or checklists for this reviewer to follow.",
    )
    source_skills: List[str] = Field(
        default_factory=list,
        description="Skill names that influenced this reviewer.",
    )
    risk_profile: List[str] = Field(
        default_factory=list,
        description="Risk areas inherited from selected skills or environment signals.",
    )


class GenomeCluster(BaseModel):
    model_config = ConfigDict(extra="forbid")

    genomes: List[ReviewGenome] = Field(
        ...,
        description="The cluster of differentiated genomes for parallel review.",
    )


class CodeComment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filepath: str = Field(..., description="The exact filepath where the issue was found.")
    line_number: int = Field(
        ...,
        description="The exact 1-based line number where the issue appears.",
    )
    issue_description: str = Field(
        ...,
        description="Detailed description of the issue or vulnerability.",
    )
    suggested_fix: str = Field(
        ...,
        description="A complete, concrete suggestion for how to fix the issue.",
    )
    severity: str = Field(..., description="'Low', 'Medium', or 'High'.")


class ReviewOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comments: List[CodeComment] = Field(
        default_factory=list,
        description="A list of specific code comments.",
    )
    overall_summary: str = Field(
        ...,
        description="A high-level summary of this specific review session.",
    )


class EvaluationScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float = Field(
        ...,
        description="A score from 0.0 to 1.0 evaluating the review's quality and accuracy.",
    )
    feedback: str = Field(
        ...,
        description="Constructive feedback on what the review missed or got wrong.",
    )


class StressTestProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hypothetical_bugs: List[str] = Field(
        ...,
        description="Likely bugs this persona should look out for.",
    )


class LearnedTrait(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trigger_context: str = Field(
        ...,
        description="A brief description of when this trait is useful.",
    )
    trait_instruction: str = Field(
        ...,
        description="The specific checklist item or rule to enforce.",
    )


class SelectedSkill(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_name: str
    trigger_context: str
    trait_instruction: str
    total_score: float = 0.0
    matched_terms: List[str] = Field(default_factory=list)
    matched_fields: Dict[str, List[str]] = Field(default_factory=dict)
    reason: str = ""
    source_case: Optional[str] = None
    success_score: Optional[float] = None
    fallback: bool = False
    risk_profile: List[str] = Field(default_factory=list)
    context_plan: List[str] = Field(default_factory=list)
    checklist: List[str] = Field(default_factory=list)
    test_templates: List[str] = Field(default_factory=list)


class ToolUseEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    iteration: int
    reviewer: str
    tool_name: str
    path: str
    success: bool
    characters_returned: int = 0
    error: Optional[str] = None


class DeterministicPenalty(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    amount: float
    filepath: Optional[str] = None
    line_number: Optional[int] = None
    reason: str


class MutationDelta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    added_reviewers: List[str] = Field(default_factory=list)
    removed_reviewers: List[str] = Field(default_factory=list)
    changed_reviewer_names: List[str] = Field(default_factory=list)
    changed_focus_areas: Dict[str, Dict[str, List[str]]] = Field(default_factory=dict)
    changed_specific_checks: Dict[str, Dict[str, List[str]]] = Field(default_factory=dict)
    changed_source_skills: Dict[str, Dict[str, List[str]]] = Field(default_factory=dict)
    changed_risk_areas: Dict[str, Dict[str, List[str]]] = Field(default_factory=dict)


class IterationTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    iteration: int
    reviewer_architecture_before: List[ReviewGenome] = Field(default_factory=list)
    pruned_reviewer_architecture: List[ReviewGenome] = Field(default_factory=list)
    stress_profiles: Dict[str, StressTestProfile] = Field(default_factory=dict)
    draft_review_summaries: Dict[str, str] = Field(default_factory=dict)
    peer_finalized_review_summaries: Dict[str, str] = Field(default_factory=dict)
    final_synthesized_review_summary: str = ""
    fitness_score: float = 0.0
    deterministic_penalties: List[DeterministicPenalty] = Field(default_factory=list)
    evaluator_comments: str = ""
    mutation_applied: bool = False
    mutation_reason: str = ""
    mutation_delta: Optional[MutationDelta] = None


class SpecializationState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    mode: Literal["review", "benchmark"]
    case_id: Optional[str] = None
    timestamp: str
    target_score: float
    max_iterations: int
    model: str
    stop_reason: str = ""
    environment: Dict[str, Any] = Field(default_factory=dict)
    selected_skills: List[SelectedSkill] = Field(default_factory=list)
    initial_reviewer_genomes: List[ReviewGenome] = Field(default_factory=list)
    reviewer_skill_map: Dict[str, List[str]] = Field(default_factory=dict)
    tool_use: List[ToolUseEvent] = Field(default_factory=list)
    iterations: List[IterationTrace] = Field(default_factory=list)
    outputs: Dict[str, Any] = Field(default_factory=dict)
