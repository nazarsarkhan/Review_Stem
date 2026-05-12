#!/usr/bin/env python3
"""
Quick setup script for OpenSpace MCP integration.

This script helps verify OpenSpace installation and configuration.
"""

import os
import subprocess
import sys
from pathlib import Path


def check_command(command: str, name: str) -> bool:
    """Check if a command is available."""
    try:
        result = subprocess.run(
            [command, "--help"],
            capture_output=True,
            timeout=2
        )
        if result.returncode == 0:
            print(f"[OK] {name} is installed")
            return True
        else:
            print(f"[X] {name} is not installed")
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print(f"[X] {name} is not installed")
        return False


def check_env_var(var: str, required: bool = False) -> bool:
    """Check if an environment variable is set."""
    value = os.getenv(var)
    if value:
        print(f"[OK] {var} is set")
        return True
    else:
        status = "[X]" if required else "[!]"
        req_text = "required" if required else "optional"
        print(f"{status} {var} is not set ({req_text})")
        return not required


def main():
    """Run OpenSpace setup checks."""
    print("=" * 60)
    print("ReviewStem OpenSpace MCP Integration Setup")
    print("=" * 60)
    print()

    # Check OpenSpace installation
    print("Checking OpenSpace installation...")
    try:
        result = subprocess.run(
            ["python", "-m", "openspace.mcp_server", "--help"],
            capture_output=True,
            timeout=2
        )
        if result.returncode == 0:
            print("[OK] OpenSpace MCP server is installed")
            openspace_installed = True
        else:
            print("[X] OpenSpace MCP server is not installed")
            openspace_installed = False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print("[X] OpenSpace MCP server is not installed")
        openspace_installed = False
    print()

    if not openspace_installed:
        print("OpenSpace is not installed. To install:")
        print()
        print("  git clone https://github.com/HKUDS/OpenSpace.git")
        print("  cd OpenSpace")
        print("  pip install -e .")
        print()
        return 1

    # Check environment variables
    print("Checking environment variables...")

    # Load .env if it exists
    env_file = Path(".env")
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv()
        print("[OK] Loaded .env file")
    else:
        print("[!] No .env file found (optional)")

    print()

    openai_ok = check_env_var("OPENAI_API_KEY", required=False)
    anthropic_ok = check_env_var("ANTHROPIC_API_KEY", required=False)
    openrouter_ok = check_env_var("OPENROUTER_API_KEY", required=False)
    check_env_var("OPENSPACE_API_KEY", required=False)
    check_env_var("OPENSPACE_WORKSPACE", required=False)
    check_env_var("OPENSPACE_HOST_SKILL_DIRS", required=False)

    # Check if at least one LLM provider is configured
    llm_ok = openai_ok or anthropic_ok or openrouter_ok
    if not llm_ok:
        print("[X] No LLM provider configured (need one of: OPENAI_API_KEY, ANTHROPIC_API_KEY, OPENROUTER_API_KEY)")
    else:
        providers = []
        if openai_ok:
            providers.append("OpenAI")
        if anthropic_ok:
            providers.append("Anthropic")
        if openrouter_ok:
            providers.append("OpenRouter")
        print(f"[OK] LLM provider(s) configured: {', '.join(providers)}")

    print()

    # Test OpenSpace connection
    if openspace_installed and llm_ok:
        print("Testing OpenSpace MCP connection...")
        try:
            # Try to import the MCP client
            from reviewstem.openspace_mcp import OpenSpaceMCPClient
            print("[OK] OpenSpace MCP client module loaded")

            # Note: We can't actually test the connection without starting the server
            print("[!] Full connection test requires running 'reviewstem review'")

        except ImportError as e:
            print(f"[X] Failed to import OpenSpace MCP client: {e}")
            print("  Make sure ReviewStem is installed: pip install -e .")
        print()

    # Summary
    print("=" * 60)

    if openspace_installed and llm_ok:
        print("[OK] OpenSpace MCP integration is ready!")
        print()
        print("Next steps:")
        print("  1. Run: reviewstem review")
        print("  2. Check logs for 'OpenSpace MCP: Retrieved N skills'")
        print("  3. If OpenSpace is used, you'll see skill sources marked as 'openspace'")
        print()
        print("Documentation:")
        print("  - OPENSPACE_MCP_INTEGRATION.md - Complete integration guide")
        print("  - README.md - Quick start and configuration")
        return 0
    else:
        print("[!] OpenSpace MCP integration is not ready")
        print()
        print("Missing requirements:")
        if not openspace_installed:
            print("  - Install OpenSpace (see above)")
        if not llm_ok:
            print("  - Set at least one LLM API key in .env:")
            print("    • OPENAI_API_KEY (for OpenAI models)")
            print("    • ANTHROPIC_API_KEY (for Claude models)")
            print("    • OPENROUTER_API_KEY (for OpenRouter)")
        print()
        print("Note: ReviewStem will work without OpenSpace (uses Epigenetics fallback)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
