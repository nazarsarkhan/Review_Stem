import logging
import os
from pathlib import Path

logger = logging.getLogger("ReviewStem")


class Hippocampus:
    @staticmethod
    def generate_repo_map(repo_path: str = ".", max_files: int = 100) -> str:
        """Generate a lightweight tree of the local repository."""
        root_path = Path(repo_path).resolve()
        logger.info("Hippocampus: Generating repository map for '%s'", root_path)
        ignore_dirs = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build"}
        tree = []
        file_count = 0

        for root, dirs, files in os.walk(root_path):
            dirs[:] = [d for d in dirs if d not in ignore_dirs]

            current_path = Path(root)
            relative_path = current_path.relative_to(root_path)
            level = 0 if str(relative_path) == "." else len(relative_path.parts)
            indent = " " * 4 * level
            folder_name = current_path.name
            if folder_name and level > 0:
                tree.append(f"{indent}{folder_name}/")

            sub_indent = " " * 4 * (level + 1) if level > 0 else ""
            for filename in files:
                if filename.endswith((".py", ".ts", ".js", ".java", ".go", ".rs", ".md", ".json", ".yml")):
                    tree.append(f"{sub_indent}{filename}")
                    file_count += 1
                    if file_count >= max_files:
                        tree.append(f"{sub_indent}... (truncated due to size)")
                        logger.info("Hippocampus: Repo map truncated to prevent context saturation.")
                        return "\n".join(tree)

        return "\n".join(tree)
