"""Pytest configuration shared across the suite.

Redirects pytest's tmp_path basetemp to a project-local directory so that
runs on Windows hosts whose %TEMP%\\pytest-of-* directory has restrictive
ACLs do not error out on every fixture that uses tmp_path.
"""

import os
from pathlib import Path

_project_tmp = Path(__file__).resolve().parent.parent / ".tmp_pytest"
_project_tmp.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("PYTEST_DEBUG_TEMPROOT", str(_project_tmp))
