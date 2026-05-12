"""OpenSpace MCP client for ReviewStem.

This module provides integration with OpenSpace via the Model Context Protocol (MCP).
OpenSpace runs as an MCP server and provides skill search capabilities.
"""

import json
import os
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .logger import logger
from .schemas import SelectedSkill


class OpenSpaceMCPClient:
    """Client for OpenSpace MCP server.

    Connects to OpenSpace MCP server via stdio and provides skill search.
    """

    def __init__(
        self,
        workspace_dir: Optional[str] = None,
        host_skill_dirs: Optional[str] = None,
        api_key: Optional[str] = None
    ):
        """Initialize OpenSpace MCP client.

        Args:
            workspace_dir: OpenSpace workspace directory
            host_skill_dirs: Colon-separated list of skill directories
            api_key: OpenSpace cloud API key (optional)
        """
        self.session: Optional[ClientSession] = None

        # Build environment for MCP server
        env = os.environ.copy()

        if workspace_dir:
            env["OPENSPACE_WORKSPACE"] = workspace_dir

        if host_skill_dirs:
            env["OPENSPACE_HOST_SKILL_DIRS"] = host_skill_dirs

        if api_key:
            env["OPENSPACE_API_KEY"] = api_key

        self.server_params = StdioServerParameters(
            command="python",
            args=["-m", "openspace.mcp_server", "--transport", "stdio"],
            env=env
        )

    async def __aenter__(self):
        """Start MCP server and establish connection.

        Uses AsyncExitStack so that the stdio_client and ClientSession context
        managers (both of which wrap anyio task groups) are entered and exited
        from the same task — required by anyio's structured concurrency, and
        the pattern the MCP SDK README documents.
        """
        self._stack = AsyncExitStack()
        try:
            await self._stack.__aenter__()
            self.read, self.write = await self._stack.enter_async_context(
                stdio_client(self.server_params)
            )
            self.session = await self._stack.enter_async_context(
                ClientSession(self.read, self.write)
            )
            await self.session.initialize()
            logger.info("OpenSpace MCP server connected and initialized")
            return self
        except BaseException as e:
            logger.error(f"Failed to connect to OpenSpace MCP server: {e}")
            await self._stack.aclose()
            raise

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close MCP connection — unwinds the exit stack in LIFO order."""
        try:
            return await self._stack.__aexit__(exc_type, exc_val, exc_tb)
        finally:
            self.session = None
            logger.info("OpenSpace MCP server disconnected")

    async def search_skills(
        self,
        query: str,
        source: str = "all",
        limit: int = 5,
        auto_import: bool = True
    ) -> List[Dict[str, Any]]:
        """Search for relevant skills.

        Args:
            query: Search query describing the task or code change
            source: "local" (only local skills), "cloud" (only cloud), or "all"
            limit: Maximum number of results to return
            auto_import: Auto-download top public cloud skills (default: True)

        Returns:
            List of skill metadata dicts with keys:
            - skill_id: Unique skill identifier
            - name: Human-readable skill name
            - description: What the skill does
            - content: Full skill content (SKILL.md)
            - quality_score: Quality metric (0.0-1.0)
            - match_reason: Why this skill matched the query
            - source: "local" or "cloud"
        """
        if not self.session:
            raise RuntimeError("MCP session not initialized")

        try:
            result = await self.session.call_tool(
                "search_skills",
                arguments={
                    "query": query,
                    "source": source,
                    "limit": limit,
                    "auto_import": auto_import
                }
            )

            skills = json.loads(result.content[0].text)
            logger.info(f"OpenSpace: Found {len(skills)} skills for query")
            return skills

        except Exception as e:
            logger.error(f"OpenSpace skill search failed: {e}")
            return []


def convert_openspace_skills_to_selected(skills: List[Dict[str, Any]]) -> List[SelectedSkill]:
    """Convert OpenSpace skill format to ReviewStem SelectedSkill format.

    Args:
        skills: List of OpenSpace skill dicts

    Returns:
        List of SelectedSkill objects
    """
    selected_skills = []

    for skill in skills:
        selected_skills.append(SelectedSkill(
            skill_name=skill.get("name", "Unknown Skill"),
            trigger_context=skill.get("description", ""),
            trait_instruction=skill.get("content", ""),
            total_score=skill.get("quality_score", 0.0),
            reason=f"OpenSpace: {skill.get('match_reason', 'Matched query')}",
            source_case=skill.get("source", "openspace"),
            fallback=False,
        ))

    return selected_skills


async def load_skills_from_openspace(
    diff: str,
    repo_signals: str = "",
    limit: int = 5
) -> List[SelectedSkill]:
    """Load review skills from OpenSpace MCP server.

    Args:
        diff: Git diff to review
        repo_signals: Repository context/signals
        limit: Maximum number of skills to retrieve

    Returns:
        List of SelectedSkill objects
    """
    workspace = os.getenv("OPENSPACE_WORKSPACE", str(Path.cwd()))
    skill_dirs = os.getenv("OPENSPACE_HOST_SKILL_DIRS", str(Path.cwd() / "skills"))
    api_key = os.getenv("OPENSPACE_API_KEY")

    # Capture results outside the `with` block so a teardown error doesn't
    # discard skills that were successfully retrieved. The MCP stdio_client's
    # cleanup occasionally raises a TaskGroup error even after a clean call;
    # we want to keep the search results in that case.
    converted: List[SelectedSkill] = []
    try:
        async with OpenSpaceMCPClient(
            workspace_dir=workspace,
            host_skill_dirs=skill_dirs,
            api_key=api_key,
        ) as openspace:
            query = f"""
            Code review task for the following changes:

            Diff (first 500 chars):
            {diff[:500]}

            Repository context:
            {repo_signals[:200]}

            Find skills relevant for security review, code quality analysis, and test generation.
            """

            skills = await openspace.search_skills(
                query=query.strip(),
                source="local",  # Only search local to avoid cloud timeout
                limit=limit,
                auto_import=False,  # Don't auto-import to avoid delays
            )

            if skills:
                logger.info(f"OpenSpace: Retrieved {len(skills)} skills")
                converted = convert_openspace_skills_to_selected(skills)
            else:
                logger.warning("OpenSpace: No skills found")
    except Exception as e:
        if converted:
            logger.warning(
                f"OpenSpace teardown raised after successful retrieval; "
                f"keeping {len(converted)} skills. Error: {e}"
            )
        else:
            logger.error(f"OpenSpace MCP integration failed: {e}")
    return converted
