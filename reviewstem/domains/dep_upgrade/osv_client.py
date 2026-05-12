"""OSV.dev REST client with on-disk caching.

OSV.dev is a free vulnerability database covering PyPI, npm, RubyGems, Go,
Maven, NuGet, crates.io, and OS distros. The single endpoint we use:

  POST https://api.osv.dev/v1/query
  body: {"package": {"name": "...", "ecosystem": "..."}, "version": "..."}
  returns: {"vulns": [{"id": "GHSA-...", "summary": "...", ...}, ...]}

Responses are cached on disk keyed by `(ecosystem, package, version)`.
Benchmark fixtures pin specific OSV/GHSA IDs so scoring stays deterministic
even when the live database changes; the cache is committed so reproducibility
does not require an internet connection.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
from urllib.request import Request, urlopen

from ...logger import logger

OSV_QUERY_URL = "https://api.osv.dev/v1/query"


@dataclass(frozen=True)
class OSVVuln:
    """A subset of the OSV record we care about for review."""

    id: str
    summary: str
    severity: str
    aliases: tuple[str, ...] = field(default_factory=tuple)
    fixed_in: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, payload: dict) -> "OSVVuln":
        sev = ""
        for entry in payload.get("severity", []) or []:
            if entry.get("type") in {"CVSS_V3", "CVSS_V2"} and entry.get("score"):
                sev = entry["score"]
                break
        if not sev:
            db_sev = payload.get("database_specific", {}).get("severity")
            if isinstance(db_sev, str):
                sev = db_sev
        fixed: list[str] = []
        for affected in payload.get("affected", []) or []:
            for r in affected.get("ranges", []) or []:
                for ev in r.get("events", []) or []:
                    if "fixed" in ev:
                        fixed.append(ev["fixed"])
        return cls(
            id=payload.get("id", ""),
            summary=payload.get("summary", "") or payload.get("details", "")[:200],
            severity=sev,
            aliases=tuple(payload.get("aliases", []) or []),
            fixed_in=tuple(fixed),
        )


class OSVClient:
    """Cached OSV.dev client.

    Tries the on-disk cache first. Falls back to a live HTTPS POST. Cache
    misses on the live path are tolerable and produce an empty result list
    (i.e. "we don't know of any CVE"), so the agent stays useful in
    offline / airgapped environments.
    """

    def __init__(
        self,
        cache_dir: Path | str = ".reviewstem/osv_cache",
        offline: bool = False,
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.offline = offline or os.getenv("REVIEWSTEM_OFFLINE") == "1"

    def _key(self, ecosystem: str, package: str, version: str) -> str:
        safe_pkg = package.replace("/", "__").replace("@", "_at_")
        return f"{ecosystem}__{safe_pkg}__{version}.json"

    def _cache_path(self, ecosystem: str, package: str, version: str) -> Path:
        return self.cache_dir / self._key(ecosystem, package, version)

    def _cache_get(self, ecosystem: str, package: str, version: str) -> list[dict] | None:
        path = self._cache_path(ecosystem, package, version)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("OSV cache read failed for %s: %s", path.name, e)
            return None

    def _cache_put(self, ecosystem: str, package: str, version: str, vulns: list[dict]) -> None:
        self._cache_path(ecosystem, package, version).write_text(
            json.dumps(vulns, indent=2), encoding="utf-8"
        )

    def query(self, ecosystem: str, package: str, version: str) -> list[OSVVuln]:
        """Look up vulnerabilities for one (ecosystem, package, version) triple."""
        cached = self._cache_get(ecosystem, package, version)
        if cached is not None:
            return [OSVVuln.from_dict(v) for v in cached]
        if self.offline:
            return []
        try:
            payload = json.dumps(
                {
                    "package": {"name": package, "ecosystem": ecosystem},
                    "version": version,
                }
            ).encode("utf-8")
            req = Request(
                OSV_QUERY_URL,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            vulns_raw = body.get("vulns", []) or []
            self._cache_put(ecosystem, package, version, vulns_raw)
            return [OSVVuln.from_dict(v) for v in vulns_raw]
        except Exception as e:
            logger.warning("OSV live query failed for %s/%s@%s: %s", ecosystem, package, version, e)
            self._cache_put(ecosystem, package, version, [])  # negative cache
            return []

    def query_many(self, triples: Iterable[tuple[str, str, str]]) -> dict[tuple[str, str, str], list[OSVVuln]]:
        """Batch convenience wrapper. OSV does not have a batch endpoint we use here."""
        return {triple: self.query(*triple) for triple in triples}

    def has_vuln_id(self, ecosystem: str, package: str, version: str, vuln_id: str) -> bool:
        """True if `vuln_id` (e.g. CVE-2023-32681 or GHSA-...) is in this version's vulns."""
        vid_norm = vuln_id.upper().strip()
        for v in self.query(ecosystem, package, version):
            ids_to_check = {v.id.upper()} | {a.upper() for a in v.aliases}
            if vid_norm in ids_to_check:
                return True
        return False
