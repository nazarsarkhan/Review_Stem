"""Tests for the MutationEngine.

The engine is one LLM call wrapped in a prompt. The tests verify it
(a) passes the previous genomes, the failing review, and the evaluator
feedback through to the LLM, (b) returns whatever GenomeCluster the LLM
produces, and (c) does not crash when previous_genomes is empty.

No real network calls — we use a fake LLM client that records prompts and
returns a canned GenomeCluster.
"""

import asyncio

from reviewstem.mutation_engine import MutationEngine
from reviewstem.schemas import (
    EvaluationScore,
    GenomeCluster,
    ReviewGenome,
    ReviewOutput,
)


class RecordingLLM:
    """Fake LLMClient that captures prompts and returns canned outputs."""

    def __init__(self, returned: GenomeCluster):
        self.returned = returned
        self.prompts: list[str] = []
        self.call_count = 0

    async def parse(self, prompt, schema, **kwargs):
        self.prompts.append(prompt)
        self.call_count += 1
        return self.returned


def _run(coro):
    return asyncio.run(coro)


def _genome(name: str) -> ReviewGenome:
    return ReviewGenome(
        persona_name=name,
        focus_areas=["sql"],
        specific_checks=["parameterize all queries"],
        source_skills=[],
        risk_profile=[],
    )


def test_evolve_passes_previous_genomes_and_feedback_into_prompt():
    canned = GenomeCluster(genomes=[_genome("Tightened SQL Reviewer")])
    llm = RecordingLLM(returned=canned)
    engine = MutationEngine(llm)

    previous = [_genome("Original SQL Reviewer")]
    review = ReviewOutput(
        comments=[],
        overall_summary="Missed an obvious injection.",
    )
    evaluation = EvaluationScore(
        score=0.55,
        feedback="The reviewer ignored unsafe interpolation on line 12.",
    )

    out = _run(engine.evolve(previous, review, evaluation))

    assert out is canned
    assert llm.call_count == 1
    prompt = llm.prompts[0]
    assert "Original SQL Reviewer" in prompt
    assert "unsafe interpolation on line 12" in prompt
    assert "Missed an obvious injection" in prompt


def test_evolve_returns_llm_output_unchanged():
    canned = GenomeCluster(
        genomes=[_genome("A"), _genome("B")]
    )
    llm = RecordingLLM(returned=canned)
    engine = MutationEngine(llm)

    out = _run(
        engine.evolve(
            previous_genomes=[_genome("A")],
            review=ReviewOutput(overall_summary="x"),
            evaluation=EvaluationScore(score=0.4, feedback="f"),
        )
    )

    assert [g.persona_name for g in out.genomes] == ["A", "B"]


def test_evolve_handles_empty_previous_genomes():
    canned = GenomeCluster(genomes=[_genome("Fresh")])
    llm = RecordingLLM(returned=canned)
    engine = MutationEngine(llm)

    out = _run(
        engine.evolve(
            previous_genomes=[],
            review=ReviewOutput(overall_summary="empty"),
            evaluation=EvaluationScore(score=0.0, feedback="nothing to evolve"),
        )
    )

    assert out.genomes[0].persona_name == "Fresh"
