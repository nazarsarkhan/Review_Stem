import json
import logging
from pathlib import Path
from typing import List

import openai
from pydantic import BaseModel, Field

from .config import ReviewStemConfig
from .llm_client import LLMClient
from .schemas import ReviewGenome, ReviewOutput, StressTestProfile, ToolUseEvent

logger = logging.getLogger("ReviewStem")


class ReadFileTool(BaseModel):
    """Reads a file from the repository to gain context."""

    filepath: str = Field(..., description="Path to the file relative to the repo root.")


class MotorCortex:
    def __init__(self, llm: LLMClient, repo_path: str = ".", config: ReviewStemConfig | None = None):
        self.llm = llm
        self.config = config or llm.config
        self.repo_path = Path(repo_path).resolve()
        self.file_read_limit = self.config.file_read_limit
        self.tool_events: list[ToolUseEvent] = []

    async def execute_draft_review(
        self,
        genome: ReviewGenome,
        diff: str,
        stress_profile: StressTestProfile,
        iteration: int = 0,
    ) -> ReviewOutput:
        """Execute the initial draft review with targeted risk validation."""
        logger.info("Draft review: executing as '%s'.", genome.persona_name)

        system_prompt = f"""
You are a highly specialized Reviewer Agent instantiated from the following genome:
{genome.model_dump_json(indent=2)}

You must conduct a strict code review based on your focus areas and specific checks.
You have tools to read files from the repository if the diff lacks sufficient context.

Risk areas to actively validate:
{stress_profile.model_dump_json(indent=2)}
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"Here is the diff to review:\n{diff}\n\nUse your tools if you need to inspect full files, otherwise return your final structured ReviewOutput.",
            },
        ]

        tools = [openai.pydantic_function_tool(ReadFileTool, name="read_file", description="Reads a repository file")]

        for _ in range(3):
            try:
                response = await self.llm.client.chat.completions.create(
                    model=self.llm.model,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                )
                self.llm._record_call("draft_review_tool_loop", response)
            except Exception as e:
                logger.error("Draft review tool loop failed: %s", e)
                break

            message = response.choices[0].message
            if message.tool_calls:
                messages.append(message)
                for tool_call in message.tool_calls:
                    if tool_call.function.name == "read_file":
                        args = json.loads(tool_call.function.arguments)
                        filepath = args.get("filepath", "")
                        content, event = self._read_file_event(filepath, genome.persona_name, iteration)
                        self.tool_events.append(event)
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": content,
                            }
                        )
            else:
                break

        messages.append({"role": "user", "content": "Conclude your draft review and return the ReviewOutput JSON."})
        output = await self.llm.parse(
            prompt="",
            schema=ReviewOutput,
            system_prompt=system_prompt,
            messages=messages,
            stage="draft_review_parse",
        )
        logger.info(
            "Draft review (%s) finished with %s comments.",
            genome.persona_name,
            len(output.comments),
        )
        return output

    async def finalize_review_with_peers(
        self,
        genome: ReviewGenome,
        draft: ReviewOutput,
        peers: List[ReviewOutput],
    ) -> ReviewOutput:
        """Refine the review by integrating findings from peer specialists."""
        logger.info("Final review: '%s' is reviewing peer drafts.", genome.persona_name)

        peer_jsons = [p.model_dump_json(indent=2) for p in peers]

        prompt = f"""
You are finalizing your code review. You are the '{genome.persona_name}'.

Your Draft Review:
{draft.model_dump_json(indent=2)}

Peer Reviews:
{peer_jsons}

Instructions:
1. Re-evaluate your draft in light of your peers' findings.
2. If a peer found a related issue that overlaps with your domain, integrate the insight.
3. Discard any of your own findings that a peer has proven to be false or better addressed.
4. Every comment must cite an exact 1-based line number.
5. Suggested fixes must be complete enough to apply, including all required arguments and placeholders.
   For SQL parameterization, do not write incomplete examples like `db.query('...', )`.
   A complete example is `await db.query('SELECT * FROM users WHERE name = $1', [name])`.
6. Output your final ReviewOutput matching your specific domain constraints.
"""
        final_output = await self.llm.parse(prompt, schema=ReviewOutput, stage="peer_finalize")
        logger.info(
            "Final review (%s) finished with %s comments.",
            genome.persona_name,
            len(final_output.comments),
        )
        return final_output

    def _read_file(self, filepath: str) -> str:
        return self._read_file_event(filepath, "unknown", 0)[0]

    def _read_file_event(self, filepath: str, reviewer: str, iteration: int) -> tuple[str, ToolUseEvent]:
        full_path = (self.repo_path / filepath).resolve()
        try:
            full_path.relative_to(self.repo_path)
        except ValueError:
            error = "requested path is outside the repository"
            return (
                f"Error reading file: {error}.",
                ToolUseEvent(
                    iteration=iteration,
                    reviewer=reviewer,
                    tool_name="read_file",
                    path=filepath,
                    success=False,
                    characters_returned=0,
                    error=error,
                ),
            )

        try:
            content = full_path.read_text(encoding="utf-8")
            clipped = content[: self.file_read_limit]
            return (
                clipped,
                ToolUseEvent(
                    iteration=iteration,
                    reviewer=reviewer,
                    tool_name="read_file",
                    path=filepath,
                    success=True,
                    characters_returned=len(clipped),
                ),
            )
        except Exception as e:
            return (
                f"Error reading file: {e}",
                ToolUseEvent(
                    iteration=iteration,
                    reviewer=reviewer,
                    tool_name="read_file",
                    path=filepath,
                    success=False,
                    characters_returned=0,
                    error=str(e),
                ),
            )
