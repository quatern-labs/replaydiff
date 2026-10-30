"""docs/usage.md stays consistent with the CLI help and action.yml."""
import io
import pathlib
import re
from contextlib import redirect_stdout

import pytest
import yaml

from replaydiff import compare

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC = (ROOT / "docs" / "usage.md").read_text()


def _help() -> str:
    buf = io.StringIO()
    with redirect_stdout(buf), pytest.raises(SystemExit):
        compare.main(["--help"])
    return buf.getvalue()


def test_every_flag_in_doc_is_in_help():
    flags = set(re.findall(r"`(--[a-z][a-z-]*)`", DOC))
    assert {"--base", "--head", "--tolerances", "--json"} <= flags
    help_text = _help()
    for flag in flags:
        assert flag in help_text, flag


def test_every_help_flag_is_in_doc():
    for flag in set(re.findall(r"--[a-z][a-z-]*", _help())) - {"--help"}:
        assert f"`{flag}`" in DOC, flag


def test_every_action_input_is_in_doc():
    inputs = yaml.safe_load((ROOT / "action.yml").read_text())["inputs"]
    for name in inputs:
        assert f"`{name}`" in DOC, name


def test_readme_links_usage_doc():
    assert "](docs/usage.md)" in (ROOT / "README.md").read_text()


def _require_step():
    steps = yaml.safe_load((ROOT / "action.yml").read_text())["runs"]["steps"]
    return next(s for s in steps if s.get("id") == "require-tolerances")


def _run_require(value: str):
    import subprocess

    return subprocess.run(
        ["bash", "-c", _require_step()["run"]],
        env={"RD_TOLERANCES": value, "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True,
    )


def test_action_fails_clearly_without_tolerances():
    r = _run_require("")
    assert r.returncode == 2
    assert "missing required input 'tolerances'" in r.stdout


def test_action_accepts_tolerances():
    assert _run_require("replaydiff.yaml").returncode == 0


def test_require_step_runs_first_and_reads_both_inputs():
    step = _require_step()
    assert yaml.safe_load((ROOT / "action.yml").read_text())["runs"]["steps"][0]["id"] == step["id"]
    assert step["env"]["RD_TOLERANCES"] == "${{ inputs.tolerances || inputs.config }}"
