"""Benchmark cases for dependency-upgrade safety reviews.

Each case is a manifest diff (pip or npm) with an expected set of CVE / GHSA
ids the review should cite, plus the package list extracted from the diff so
the fitness function can ground CVE references against OSV.

Scoring shape mirrors the code-review benchmark scorer: concept groups +
required ids + severity. The deltas vs the generic baseline are what we
report; absolute numbers are biased by my own scorer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from ...schemas import ReviewOutput


@dataclass(frozen=True)
class DepUpgradeCase:
    """A deterministic dep-upgrade benchmark case."""

    case_id: str
    title: str
    diff: str
    expected_filepath: str  # manifest path the review should land in
    expected_severity: str  # at least one expected finding at this level
    expected_vuln_ids: tuple[str, ...] = ()
    packages: tuple[tuple[str, str, str], ...] = ()  # (ecosystem, pkg, version) for fitness
    concept_groups: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class DepUpgradeScore:
    case_id: str
    score: float
    matched_vuln_ids: int
    expected_vuln_ids: int
    severity_match: bool
    concept_score: float
    notes: str


DEP_UPGRADE_CASES: dict[str, DepUpgradeCase] = {
    "requests_cve_upgrade": DepUpgradeCase(
        case_id="requests_cve_upgrade",
        title="Pip upgrade of `requests` crossing CVE-2023-32681 (Proxy-Authorization leak)",
        expected_filepath="requirements.txt",
        expected_severity="High",
        expected_vuln_ids=("CVE-2023-32681",),
        packages=(
            ("PyPI", "requests", "2.25.0"),
            ("PyPI", "requests", "2.31.0"),
        ),
        concept_groups=(
            ("cve", "ghsa", "advisory"),
            ("requests", "urllib3"),
            ("proxy-authorization", "header leak", "redirect"),
            ("upgrade", "fix", "patched", "fixed in"),
        ),
        diff="""diff --git a/requirements.txt b/requirements.txt
index 1234567..89abcdef 100644
--- a/requirements.txt
+++ b/requirements.txt
@@ -1,3 +1,3 @@
-requests==2.25.0
+requests==2.31.0
 flask==2.3.3
""",
    ),
    "lodash_prototype_pollution_fix": DepUpgradeCase(
        case_id="lodash_prototype_pollution_fix",
        title="npm upgrade of `lodash` crossing CVE-2019-10744 (prototype pollution)",
        expected_filepath="package.json",
        expected_severity="High",
        expected_vuln_ids=("CVE-2019-10744",),
        packages=(
            ("npm", "lodash", "4.17.10"),
            ("npm", "lodash", "4.17.21"),
        ),
        concept_groups=(
            ("cve", "ghsa", "advisory"),
            ("lodash",),
            ("prototype pollution", "__proto__", "defaultsdeep"),
            ("upgrade", "fix", "patched"),
        ),
        diff="""diff --git a/package.json b/package.json
index 1234567..89abcdef 100644
--- a/package.json
+++ b/package.json
@@ -3,7 +3,7 @@
   "version": "1.0.0",
   "dependencies": {
     "express": "^4.18.0",
-    "lodash": "4.17.10",
+    "lodash": "4.17.21",
     "winston": "^3.10.0"
   }
 }
""",
    ),
    "numpy_major_bump": DepUpgradeCase(
        case_id="numpy_major_bump",
        title="numpy 1.x -> 2.x major bump (ABI break, deprecation removals)",
        expected_filepath="requirements.txt",
        expected_severity="High",
        expected_vuln_ids=(),
        packages=(
            ("PyPI", "numpy", "1.26.4"),
            ("PyPI", "numpy", "2.0.0"),
        ),
        concept_groups=(
            ("major version", "breaking", "abi", "binary compatibility"),
            ("numpy",),
            ("deprecation", "removed", "removed in 2.0"),
            ("test", "regression", "migration guide"),
        ),
        diff="""diff --git a/requirements.txt b/requirements.txt
index 1234567..89abcdef 100644
--- a/requirements.txt
+++ b/requirements.txt
@@ -1,2 +1,2 @@
-numpy==1.26.4
+numpy==2.0.0
""",
    ),
    "flask_deprecation": DepUpgradeCase(
        case_id="flask_deprecation",
        title="Flask 1.1.x -> 2.x bump removes deprecated APIs",
        expected_filepath="requirements.txt",
        expected_severity="High",
        expected_vuln_ids=(),
        packages=(
            ("PyPI", "flask", "1.1.4"),
            ("PyPI", "flask", "2.0.0"),
        ),
        concept_groups=(
            ("flask",),
            ("major version", "breaking change"),
            ("deprecation", "removed", "removed in 2.0", "async views"),
            ("werkzeug", "dependency", "transitive"),
        ),
        diff="""diff --git a/requirements.txt b/requirements.txt
index 1234567..89abcdef 100644
--- a/requirements.txt
+++ b/requirements.txt
@@ -1,2 +1,2 @@
-flask==1.1.4
+flask==2.0.0
""",
    ),
    "event_stream_compromise": DepUpgradeCase(
        case_id="event_stream_compromise",
        title="Adds compromised `event-stream@3.3.6` (2018 supply-chain attack)",
        expected_filepath="package.json",
        expected_severity="Critical",
        expected_vuln_ids=("CVE-2018-1000620",),
        packages=(
            ("npm", "event-stream", "3.3.6"),
        ),
        concept_groups=(
            ("event-stream",),
            ("supply chain", "compromise", "malicious", "flatmap-stream"),
            ("remove", "do not use", "abandoned", "deprecated"),
            ("audit", "npm audit", "transitive"),
        ),
        diff="""diff --git a/package.json b/package.json
index 1234567..89abcdef 100644
--- a/package.json
+++ b/package.json
@@ -3,7 +3,8 @@
   "version": "1.0.0",
   "dependencies": {
     "express": "^4.18.0",
-    "winston": "^3.10.0"
+    "winston": "^3.10.0",
+    "event-stream": "3.3.6"
   }
 }
""",
    ),
    "pyyaml_unsafe_load": DepUpgradeCase(
        case_id="pyyaml_unsafe_load",
        title="PyYAML 5.x -> 6.x bump changes `load()` default behavior",
        expected_filepath="requirements.txt",
        expected_severity="High",
        expected_vuln_ids=(),
        packages=(
            ("PyPI", "PyYAML", "5.4.1"),
            ("PyPI", "PyYAML", "6.0.1"),
        ),
        concept_groups=(
            ("pyyaml", "yaml"),
            ("safe_load", "full_load", "unsafe", "load"),
            ("major version", "breaking", "default Loader"),
            ("deserialization", "code execution"),
        ),
        diff="""diff --git a/requirements.txt b/requirements.txt
index 1234567..89abcdef 100644
--- a/requirements.txt
+++ b/requirements.txt
@@ -1,2 +1,2 @@
-PyYAML==5.4.1
+PyYAML==6.0.1
""",
    ),
    "cryptography_breaking": DepUpgradeCase(
        case_id="cryptography_breaking",
        title="cryptography 3.x -> 41.x: pyOpenSSL removal, multi-year version jump",
        expected_filepath="requirements.txt",
        expected_severity="High",
        expected_vuln_ids=("CVE-2023-49083",),
        packages=(
            ("PyPI", "cryptography", "3.4.8"),
            ("PyPI", "cryptography", "41.0.0"),
        ),
        concept_groups=(
            ("cryptography",),
            ("major version", "breaking change", "abi"),
            ("openssl", "rust bindings"),
            ("upgrade", "migration", "deprecated"),
        ),
        diff="""diff --git a/requirements.txt b/requirements.txt
index 1234567..89abcdef 100644
--- a/requirements.txt
+++ b/requirements.txt
@@ -1,2 +1,2 @@
-cryptography==3.4.8
+cryptography==41.0.0
""",
    ),
    "axios_ssrf_upgrade": DepUpgradeCase(
        case_id="axios_ssrf_upgrade",
        title="axios 0.21.0 -> 1.6.0 crossing CVE-2024-39338 (SSRF)",
        expected_filepath="package.json",
        expected_severity="High",
        expected_vuln_ids=("CVE-2024-39338",),
        packages=(
            ("npm", "axios", "0.21.0"),
            ("npm", "axios", "1.6.0"),
        ),
        concept_groups=(
            ("cve", "ghsa", "advisory"),
            ("axios",),
            ("ssrf", "server-side request forgery"),
            ("upgrade", "fix"),
        ),
        diff="""diff --git a/package.json b/package.json
index 1234567..89abcdef 100644
--- a/package.json
+++ b/package.json
@@ -3,7 +3,7 @@
   "version": "1.0.0",
   "dependencies": {
     "express": "^4.18.0",
-    "axios": "0.21.0",
+    "axios": "1.6.0",
     "winston": "^3.10.0"
   }
 }
""",
    ),
}


def select_dep_upgrade_cases(case_ids: str | None = None) -> list[DepUpgradeCase]:
    if not case_ids:
        return list(DEP_UPGRADE_CASES.values())
    out: list[DepUpgradeCase] = []
    for raw in case_ids.split(","):
        cid = raw.strip()
        if cid:
            out.append(DEP_UPGRADE_CASES[cid])
    return out


def extract_packages_from_diff(diff: str) -> list[tuple[str, str, str]]:
    """Heuristic: pull (ecosystem, name, version) triples from a manifest diff.

    Captures BOTH `+` (new) and `-` (old) lines so the fitness function can
    validate CVE references that mention either the version being introduced
    or the version being fixed by the upgrade.
    """
    triples: list[tuple[str, str, str]] = []
    pip_re = re.compile(r"^[+-]\s*([A-Za-z0-9_.\-]+)\s*==\s*([0-9][0-9A-Za-z\.\-+]*)\s*$")
    npm_re = re.compile(r'^[+-]\s*"([A-Za-z0-9@/_\-]+)"\s*:\s*"\^?~?([0-9][0-9A-Za-z\.\-+]*)"')
    seen: set[tuple[str, str, str]] = set()
    for line in diff.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue  # diff header lines
        m = pip_re.match(line)
        if m:
            triple = ("PyPI", m.group(1), m.group(2))
            if triple not in seen:
                triples.append(triple)
                seen.add(triple)
            continue
        m = npm_re.match(line)
        if m:
            triple = ("npm", m.group(1), m.group(2))
            if triple not in seen:
                triples.append(triple)
                seen.add(triple)
    return triples


def score_dep_review(case: DepUpgradeCase, review: ReviewOutput) -> DepUpgradeScore:
    """Score a dep-upgrade review against the case fixture.

    Components:
      - 0.30 if a finding lands in the manifest file the case names
      - 0.20 if its severity matches the case's expected_severity
      - 0.30 for concept group coverage
      - 0.20 weighted by fraction of expected vuln ids that appear in the review
    """
    text = _review_text(review).lower()

    matched_filepath = any(c.filepath == case.expected_filepath for c in review.comments)
    file_score = 0.30 if matched_filepath else 0.0

    severities = {(c.severity or "").lower() for c in review.comments}
    severity_match = case.expected_severity.lower() in severities
    sev_score = 0.20 if severity_match else 0.0

    if case.concept_groups:
        satisfied = sum(
            1 for group in case.concept_groups
            if any(term.lower() in text for term in group)
        )
        concept = 0.30 * satisfied / max(1, len(case.concept_groups))
    else:
        concept = 0.30  # cases with no required vocabulary get full credit

    matched_vulns = sum(1 for vid in case.expected_vuln_ids if vid.lower() in text)
    if case.expected_vuln_ids:
        vuln_score = 0.20 * matched_vulns / len(case.expected_vuln_ids)
    else:
        vuln_score = 0.20  # cases with no expected vulns (breaking-change only) get full credit

    total = round(file_score + sev_score + concept + vuln_score, 3)
    notes = "matched" if total >= 0.75 else "missing evidence"
    return DepUpgradeScore(
        case_id=case.case_id,
        score=total,
        matched_vuln_ids=matched_vulns,
        expected_vuln_ids=len(case.expected_vuln_ids),
        severity_match=severity_match,
        concept_score=round(concept, 3),
        notes=notes,
    )


def _review_text(review: ReviewOutput) -> str:
    pieces = [review.overall_summary or ""]
    for c in review.comments:
        pieces.extend([c.issue_description or "", c.suggested_fix or "", c.severity or ""])
    return "\n".join(pieces)


def dep_upgrade_benchmark_repo() -> Path:
    """Return the path to the dep-upgrade benchmark fixture directory."""
    return Path(__file__).parent / "fixtures"
