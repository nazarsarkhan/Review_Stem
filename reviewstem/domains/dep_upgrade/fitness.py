"""Fitness function for dependency-upgrade reviews.

Shares the LLM-grader + deterministic-penalty shape of the code review
fitness, but the grounding checks operate over manifest references and
OSV/GHSA identifiers rather than filesystem paths and line numbers.

Penalties:
- hallucinated_cve   (-0.20): cited CVE id is not present in OSV for the
                              named (ecosystem, package, version).
- bad_semver         (-0.10): cited version string is not parseable.
- non_manifest_file  (-0.10): finding cites a file that is not a manifest.
- vague_finding      (-0.10): description is < 24 chars or generic.
- missing_fix_action (-0.10): High/Critical finding lacks a concrete fix.
- duplicate          (-0.05): same (package, vuln_id) cited twice.
"""

from __future__ import annotations

import re
from pathlib import Path

from ...llm_client import LLMClient
from ...logger import logger
from ...schemas import DeterministicPenalty, EvaluationScore, ReviewOutput
from .osv_client import OSVClient

VULN_ID_RE = re.compile(r"\b(?:CVE-\d{4}-\d{4,7}|GHSA(?:-[0-9a-z]{4}){3}|OSV-\d{4}-\d+)\b", re.IGNORECASE)
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z\.-]+)?$")
MANIFEST_NAMES = {
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "requirements.txt",
    "pyproject.toml",
    "poetry.lock",
    "Pipfile",
    "Pipfile.lock",
    "Cargo.toml",
    "Cargo.lock",
    "go.mod",
    "go.sum",
}


class DepUpgradeFitness:
    """Same interface as FitnessFunction.evaluate(); OSV-aware grounding."""

    def __init__(
        self,
        llm: LLMClient,
        osv: OSVClient | None = None,
        manifest_packages: list[tuple[str, str, str]] | None = None,
    ):
        """
        Args:
            llm: LLM client for the grader call.
            osv: OSV client; if None a fresh cache-backed client is created.
            manifest_packages: list of (ecosystem, package, version) tuples
                derived from the actual manifest diff; CVE references in the
                review are validated against these.
        """
        self.llm = llm
        self.osv = osv or OSVClient()
        self.manifest_packages = manifest_packages or []
        self.last_penalties: list[DeterministicPenalty] = []

    async def evaluate(self, review: ReviewOutput) -> EvaluationScore:
        penalties: list[DeterministicPenalty] = []
        seen: set[tuple[str, str]] = set()

        if not review.comments:
            penalties.append(
                DeterministicPenalty(
                    code="empty_review",
                    amount=0.30,
                    reason="Review contained no comments.",
                )
            )

        for comment in review.comments:
            issue = comment.issue_description or ""
            fix = comment.suggested_fix or ""
            severity = (comment.severity or "").lower()

            cited_vulns = VULN_ID_RE.findall(issue + " " + fix)
            for vid in cited_vulns:
                key = (comment.filepath, vid.upper())
                if key in seen:
                    penalties.append(
                        DeterministicPenalty(
                            code="duplicate",
                            amount=0.05,
                            filepath=comment.filepath,
                            line_number=comment.line_number,
                            reason=f"Duplicate citation of {vid}.",
                        )
                    )
                    continue
                seen.add(key)
                if self.manifest_packages and not self._cve_is_real(vid):
                    penalties.append(
                        DeterministicPenalty(
                            code="hallucinated_cve",
                            amount=0.20,
                            filepath=comment.filepath,
                            line_number=comment.line_number,
                            reason=f"{vid} not found in OSV for any package in this diff.",
                        )
                    )

            for version_match in re.findall(r"\b\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?\b", issue + " " + fix):
                if not SEMVER_RE.match(version_match):
                    penalties.append(
                        DeterministicPenalty(
                            code="bad_semver",
                            amount=0.10,
                            filepath=comment.filepath,
                            reason=f"Version {version_match!r} is not parseable semver.",
                        )
                    )

            if not self._is_manifest_path(comment.filepath):
                penalties.append(
                    DeterministicPenalty(
                        code="non_manifest_file",
                        amount=0.10,
                        filepath=comment.filepath,
                        line_number=comment.line_number,
                        reason="Finding cites a file that is not a recognized dependency manifest.",
                    )
                )

            if _is_vague(issue):
                penalties.append(
                    DeterministicPenalty(
                        code="vague_finding",
                        amount=0.10,
                        filepath=comment.filepath,
                        line_number=comment.line_number,
                        reason="Issue description is short or generic.",
                    )
                )

            if severity in {"high", "critical"} and len(fix.strip()) < 20:
                penalties.append(
                    DeterministicPenalty(
                        code="missing_fix_action",
                        amount=0.10,
                        filepath=comment.filepath,
                        line_number=comment.line_number,
                        reason="High-severity finding lacks a concrete fix.",
                    )
                )

        prompt = f"""
        You are evaluating a dependency-upgrade safety review. Grade 0.0-1.0.

        Review Data:
        {review.model_dump_json(indent=2)}

        Criteria:
        - Accuracy: Are CVEs / breaking changes correctly identified?
        - Specificity: Does it name versions, CVE/GHSA ids, and fixed-in versions?
        - Actionability: Are suggested fixes concrete (pin to vX.Y.Z, run `pip-audit`, etc.)?
        - Completeness: Does it cover security, breaking changes, license, and pinning?
        - Grounding: Does it cite real CVEs and real package versions?

        Provide a score and brief constructive feedback.
        """
        evaluation = await self.llm.parse(prompt, schema=EvaluationScore, stage="dep_fitness_evaluate")

        deterministic = sum(p.amount for p in penalties)
        evaluation.score = max(0.0, evaluation.score - deterministic)
        self.last_penalties = penalties
        if deterministic > 0:
            evaluation.feedback += " [Dep-upgrade penalties applied: " + ", ".join(p.code for p in penalties) + "]"

        logger.info("DepUpgradeFitness: score=%.2f penalties=%d", evaluation.score, len(penalties))
        return evaluation

    def _cve_is_real(self, vuln_id: str) -> bool:
        for ecosystem, pkg, version in self.manifest_packages:
            if self.osv.has_vuln_id(ecosystem, pkg, version, vuln_id):
                return True
        return False

    def _is_manifest_path(self, path: str) -> bool:
        name = Path(path).name
        return name in MANIFEST_NAMES


def _is_vague(text: str) -> bool:
    lowered = text.strip().lower()
    if len(lowered) < 24:
        return True
    for phrase in ("fix this", "issue here", "vulnerable", "could be improved", "consider updating"):
        if phrase in lowered and len(lowered) < 60:
            return True
    return False
