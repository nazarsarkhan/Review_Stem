from typing import List

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
