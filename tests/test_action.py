"""action.yml and tools/ci/action_compare.sh, offline (no GitHub runner)."""
import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "tools" / "ci" / "action_compare.sh"


def run_script(tmp_path, **env):
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    shim = bindir / "replaydiff"
    shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" -m replaydiff.cli "$@"\n')
    shim.chmod(0o755)
    out = tmp_path / "out"
    e = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}", "RUNNER_TEMP": str(tmp_path),
         "GITHUB_OUTPUT": str(out), "PYTHONPATH": str(ROOT)}
    e.pop("RD_TOLERANCES", None)
    e.update(env)
    p = subprocess.run(["bash", str(SCRIPT)], env=e, capture_output=True, text=True)
    return p, out.read_text() if out.exists() else ""


def test_action_declares_inputs_and_output():
    a = yaml.safe_load((ROOT / "action.yml").read_text())
    assert {"base", "head", "tolerances", "inconclusive", "comment", "python-version"} <= set(a["inputs"])
    assert a["inputs"]["tolerances"]["required"] is True
    assert "exit-code" in a["outputs"]


def test_missing_tolerances_fails_with_clear_message(tmp_path):
    p, out = run_script(tmp_path, RD_BASE="a.mcap b.mcap", RD_HEAD="h.mcap", RD_TOLERANCES="")
    assert p.returncode == 2
    assert "'tolerances' input is required" in p.stderr
    assert "exit-code=2" in out


def _demo(tmp_path):
    subprocess.run([sys.executable, str(ROOT / "examples" / "make_demo.py"), str(tmp_path / "runs")],
                   check=True, capture_output=True)
    d = tmp_path / "runs"
    return d, " ".join(str(d / f"base{i}.mcap") for i in range(3))


def test_pass_and_fail_exit_codes_and_markdown(tmp_path):
    d, base = _demo(tmp_path)
    p, out = run_script(tmp_path, RD_BASE=base, RD_HEAD=str(d / "head_same.mcap"),
                        RD_TOLERANCES=str(d / "tolerances.yaml"))
    assert p.returncode == 0 and "exit-code=0" in out
    p, out = run_script(tmp_path, RD_BASE=base, RD_HEAD=str(d / "head_regressed.mcap"),
                        RD_TOLERANCES=str(d / "tolerances.yaml"))
    assert p.returncode == 1 and "exit-code=1" in out
    assert "VERDICT FAIL" in (tmp_path / "replaydiff-report.md").read_text()


def test_inconclusive_flag(tmp_path):
    d, base = _demo(tmp_path)
    env = dict(RD_BASE=base.split()[0], RD_HEAD=str(d / "head_same.mcap"), RD_TOLERANCES=str(d / "tolerances.yaml"))
    # a single base run has no noise floor: INCONCLUSIVE
    assert run_script(tmp_path, **env)[0].returncode == 2
    p, out = run_script(tmp_path, RD_INCONCLUSIVE="pass", **env)
    assert p.returncode == 0 and "exit-code=0" in out
