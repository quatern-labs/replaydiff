# SPDX-License-Identifier: Apache-2.0
"""Release checks (no release is made): one version, a changelog Unreleased section, SPDX headers, LICENSE text."""
import hashlib
import pathlib
import re
import subprocess

import replaydiff
from replaydiff import cli

ROOT = pathlib.Path(__file__).resolve().parents[1]
APACHE_2_0_SHA256 = "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"


def pyproject_version():
    m = re.search(r'^version\s*=\s*"([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M)
    assert m
    return m.group(1)


def test_version_agrees(capsys):
    assert replaydiff.__version__ == pyproject_version()
    assert cli.main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"replaydiff {pyproject_version()}"


def test_dev_version_only():
    assert re.fullmatch(r"\d+\.\d+\.\d+\.dev\d+", pyproject_version())


def test_changelog_has_unreleased_section():
    text = (ROOT / "CHANGELOG.md").read_text()
    m = re.search(r"^## \[Unreleased\]\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    assert m, "no '## [Unreleased]' heading"
    items = [l for l in m.group(1).splitlines() if l.startswith("- ")]
    assert len(items) >= 5
    body = m.group(1).lower()
    for word in ("compare", "twist", "odometry", "path", "jointstate", "tf", "tolerance", "--json", "--markdown",
                 "--inconclusive", "github action"):
        assert word in body, word


def test_spdx_header_on_every_python_file():
    files = subprocess.check_output(["git", "ls-files", "*.py"], cwd=ROOT, text=True).split()
    files = [f for f in files if f.startswith(("replaydiff/", "validation/"))]
    assert files
    missing = []
    for f in files:
        head = (ROOT / f).read_text().splitlines()[:2]
        if "# SPDX-License-Identifier: Apache-2.0" not in head:
            missing.append(f)
    assert not missing, missing


def test_license_is_unmodified_apache_2_0_and_notice_exists():
    assert hashlib.sha256((ROOT / "LICENSE").read_bytes()).hexdigest() == APACHE_2_0_SHA256
    assert "Apache License, Version 2.0" in (ROOT / "NOTICE").read_text()
