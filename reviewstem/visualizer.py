import re
from pathlib import Path

from .logger import logger


class ReviewVisualizer:
    @staticmethod
    def generate_evolution_diagram(case_name: str, generations: list):
        """Generate a Mermaid.js diagram representing review strategy evolution."""
        diagram = ["graph TD"]

        for i, genome in enumerate(generations):
            persona = re.sub(r"[^A-Za-z0-9_]", "_", genome.persona_name)
            node_id = f"G{i}_{persona}"
            diagram.append(f'    {node_id}["Generation {i + 1}: {genome.persona_name}"]')

            if i > 0:
                prev_persona = re.sub(r"[^A-Za-z0-9_]", "_", generations[i - 1].persona_name)
                prev_id = f"G{i - 1}_{prev_persona}"
                diagram.append(f"    {prev_id} -->|Revision| {node_id}")

        safe_case_name = re.sub(r"[^A-Za-z0-9_.-]", "_", case_name)
        output_file = Path(f"evolution_graph_{safe_case_name}.mmd")
        output_file.write_text("\n".join(diagram), encoding="utf-8")
        logger.info("Evolution graph saved to %s", output_file)
