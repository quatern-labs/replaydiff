# SPDX-License-Identifier: Apache-2.0
"""Release readiness: one version, a changelog, license headers, unmodified LICENSE."""
import hashlib
import pathlib
import re

import replaydiff
from replaydiff import cli

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPDX = "# SPDX-License-Identifier: Apache-2.0"
APACHE_2_SHA256 = "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"


def test_version_agrees(capsys):
    m = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M)
    assert m and m.group(1) == replaydiff.__version__
    assert cli.main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"replaydiff {replaydiff.__version__}"


def test_changelog_has_unreleased_section():
    text = (ROOT / "CHANGELOG.md").read_text()
    m = re.search(r"^## \[Unreleased\]\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    assert m, "CHANGELOG.md needs a '## [Unreleased]' section"
    body = m.group(1)
    assert "### Added" in body
    for word in ("compare", "Twist", "Odometry", "Path", "JointState", "/tf",
                 "--json", "--markdown", "--inconclusive", "GitHub Action"):
        assert word in body, word


def test_spdx_header_on_every_python_file():
    files = [p for d in ("replaydiff", "validation") for p in (ROOT / d).rglob("*.py")
             if "__pycache__" not in p.parts]
    assert files
    missing = [str(p.relative_to(ROOT)) for p in files
               if SPDX not in p.read_text().splitlines()[:2]]
    assert not missing, missing


def test_license_is_unmodified_apache_2():
    assert hashlib.sha256((ROOT / "LICENSE").read_bytes()).hexdigest() == APACHE_2_SHA256
    assert "Apache License, Version 2.0" in (ROOT / "NOTICE").read_text()
