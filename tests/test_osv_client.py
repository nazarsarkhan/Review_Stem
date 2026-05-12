"""Tests for the OSV client cache and CVE alias lookup.

No live network calls. We pre-seed the cache directory and assert the
client reads from it and resolves CVE aliases correctly.
"""

import json
from pathlib import Path

from reviewstem.domains.dep_upgrade.osv_client import OSVClient, OSVVuln


def _seed(cache_dir: Path, key: str, vulns: list[dict]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / key).write_text(json.dumps(vulns), encoding="utf-8")


def test_query_returns_cached_vulns(tmp_path):
    _seed(
        tmp_path,
        "PyPI__requests__2.25.0.json",
        [{"id": "GHSA-test", "aliases": ["CVE-2099-99999"], "summary": "x", "severity": []}],
    )
    osv = OSVClient(cache_dir=tmp_path, offline=True)
    vulns = osv.query("PyPI", "requests", "2.25.0")
    assert len(vulns) == 1
    assert vulns[0].id == "GHSA-test"
    assert "CVE-2099-99999" in vulns[0].aliases


def test_has_vuln_id_matches_alias(tmp_path):
    _seed(
        tmp_path,
        "npm__lodash__4.17.10.json",
        [{"id": "GHSA-jf85", "aliases": ["CVE-2019-10744"]}],
    )
    osv = OSVClient(cache_dir=tmp_path, offline=True)
    assert osv.has_vuln_id("npm", "lodash", "4.17.10", "CVE-2019-10744") is True
    assert osv.has_vuln_id("npm", "lodash", "4.17.10", "CVE-9999-9999") is False


def test_has_vuln_id_matches_primary_id(tmp_path):
    _seed(tmp_path, "PyPI__pkg__1.0.0.json", [{"id": "OSV-2024-1", "aliases": []}])
    osv = OSVClient(cache_dir=tmp_path, offline=True)
    assert osv.has_vuln_id("PyPI", "pkg", "1.0.0", "osv-2024-1") is True


def test_offline_mode_returns_empty_for_uncached(tmp_path):
    osv = OSVClient(cache_dir=tmp_path, offline=True)
    assert osv.query("PyPI", "missing", "1.0.0") == []


def test_vuln_from_dict_extracts_fixed_in():
    payload = {
        "id": "X-1",
        "summary": "s",
        "severity": [{"type": "CVSS_V3", "score": "CVSS:3.1/..."}],
        "affected": [
            {"ranges": [{"events": [{"introduced": "0"}, {"fixed": "2.0"}]}]},
            {"ranges": [{"events": [{"fixed": "3.0"}]}]},
        ],
    }
    v = OSVVuln.from_dict(payload)
    assert "2.0" in v.fixed_in and "3.0" in v.fixed_in


def test_cache_key_handles_scoped_npm_package(tmp_path):
    # @types/node should produce a filename safe path
    osv = OSVClient(cache_dir=tmp_path, offline=True)
    key = osv._key("npm", "@types/node", "1.0.0")
    assert "/" not in key
    assert "@" not in key
