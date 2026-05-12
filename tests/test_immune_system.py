"""Tests for ImmuneSystem.synthesize_and_criticize.

The synthesizer takes a list of draft reviews and returns one. The tests
verify it forwards every draft's content into the LLM prompt and returns
the LLM's final ReviewOutput unchanged.
"""

import asyncio

from reviewstem.immune_system import ImmuneSystem
from reviewstem.schemas import CodeComment, ReviewOutput


class RecordingLLM:
    def __init__(self, returned: ReviewOutput):
        self.returned = returned
        self.prompts: list[str] = []
        self.call_count = 0

    async def parse(self, prompt, schema, **kwargs):
        self.prompts.append(prompt)
        self.call_count += 1
        return self.returned


def _run(coro):
    return asyncio.run(coro)


def test_synthesizer_forwards_every_draft_into_prompt():
    draft_a = ReviewOutput(
        comments=[
            CodeComment(
                filepath="a.ts",
                line_number=10,
                issue_description="Reviewer A finding about SQL injection in users query",
                suggested_fix="Use parameterized queries with explicit placeholders",
                severity="High",
            )
        ],
        overall_summary="Draft from reviewer A",
    )
    draft_b = ReviewOutput(
        comments=[
            CodeComment(
                filepath="b.ts",
                line_number=20,
                issue_description="Reviewer B finding about missing rate limiting on login",
                suggested_fix="Add express-rate-limit middleware to the route",
                severity="Medium",
            )
        ],
        overall_summary="Draft from reviewer B",
    )

    final = ReviewOutput(comments=[draft_a.comments[0]], overall_summary="Synthesized")
    llm = RecordingLLM(returned=final)
    immune = ImmuneSystem(llm)

    out = _run(immune.synthesize_and_criticize([draft_a, draft_b]))

    assert out is final
    assert llm.call_count == 1
    prompt = llm.prompts[0]
    assert "Reviewer A finding about SQL injection" in prompt
    assert "Reviewer B finding about missing rate limiting" in prompt


def test_synthesizer_returns_empty_review_when_no_drafts_were_useful():
    empty = ReviewOutput(comments=[], overall_summary="No issues survived synthesis")
    llm = RecordingLLM(returned=empty)
    immune = ImmuneSystem(llm)

    out = _run(immune.synthesize_and_criticize([]))

    assert out.comments == []
    assert out.overall_summary == "No issues survived synthesis"
