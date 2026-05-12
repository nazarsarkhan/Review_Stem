"""Dependency upgrade safety review domain.

Input: a manifest diff (package.json / requirements.txt / pyproject.toml).
Output: a structured review flagging CVEs introduced or fixed, breaking
changes, transitive bloat, license shifts, and pinning quality.

Reuses the existing stem-cell pipeline (stem_cell, motor_cortex,
mutation_engine, immune_system) with a domain-specific skill catalog,
fitness function, and benchmark suite.
"""

from .benchmark import DEP_UPGRADE_CASES, DepUpgradeCase, score_dep_review
from .fitness import DepUpgradeFitness
from .osv_client import OSVClient, OSVVuln

__all__ = [
    "DEP_UPGRADE_CASES",
    "DepUpgradeCase",
    "DepUpgradeFitness",
    "OSVClient",
    "OSVVuln",
    "score_dep_review",
]
