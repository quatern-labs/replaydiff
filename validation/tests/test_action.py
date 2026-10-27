"""action.yml: structure, and its compare step run as a shell script on the synthetic fixture."""
import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

from replaydiff.cli import main
from synth import CLI_TOLERANCES, write_mcap

ACTION = Path(__file__).resolve().parents[2] / "action.yml"


def steps():
    return {s.get("name", s.get("uses")): s for s in yaml.safe_load(ACTION.read_text())["runs"]["steps"]}


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    d = tmp_path_factory.mktemp("action")
    for i in range(3):
        write_mcap(d / f"base{i}.mcap", seed=i)
    write_mcap(d / "same.mcap", seed=7)
    write_mcap(d / "gain30.mcap", seed=7, gain=1.3)
    write_mcap(d / "offset2cm.mcap", seed=7, offset=0.02)
    (d / "tol.yaml").write_text(CLI_TOLERANCES)
    return d


def run_step(d, head, inconclusive="fail", base=None):
    base = base or " ".join(str(d / f"base{i}.mcap") for i in range(3))
    out = d / f"out-{head}-{inconclusive}-{len(base)}"
    out.mkdir()
    env = {**os.environ, "BASE": base, "HEAD": str(d / head), "TOLERANCES": str(d / "tol.yaml"),
           "INCONCLUSIVE": inconclusive, "RUNNER_TEMP": str(out), "GITHUB_OUTPUT": str(out / "gh_out"),
           "GITHUB_STEP_SUMMARY": str(out / "summary")}
    subprocess.run(["bash", "-e", "-c", steps()["Compare"]["run"]], env=env, check=True, capture_output=True)
    outputs = dict(l.split("=", 1) for l in (out / "gh_out").read_text().split("\n") if l)
    return outputs, out


def test_structure():
    a = yaml.safe_load(ACTION.read_text())
    assert a["runs"]["using"] == "composite"
    assert {"base", "head", "tolerances", "inconclusive", "comment"} <= set(a["inputs"])
    s = steps()
    assert "pull_request" in s["Post PR comment"]["if"]
    assert s["actions/upload-artifact@v4"]["with"]["name"] == "replaydiff-report"
    assert "exit ${{ steps.compare.outputs.exit_code }}" in s["Exit with the tool's code"]["run"]


@pytest.mark.parametrize("head,verdict,code", [("same.mcap", "PASS", "0"), ("gain30.mcap", "FAIL", "1"),
                                               ("offset2cm.mcap", "FAIL", "1")])
def test_compare_step_verdicts_match_cli(runs, head, verdict, code):
    outputs, out = run_step(runs, head)
    assert (outputs["verdict"], outputs["exit_code"]) == (verdict, code)
    assert int(code) == main(["compare", "--base", *[str(runs / f"base{i}.mcap") for i in range(3)], "--head",
                              str(runs / head), "--tolerances", str(runs / "tol.yaml")])
    md = (out / "replaydiff" / "report.md").read_text()
    assert "replaydiff: " in md and verdict in md and md.count("\n|---|") == 1
    assert md in (out / "summary").read_text()
    assert json.loads((out / "replaydiff" / "report.json").read_text())["verdict"] == verdict


def test_inconclusive_input(runs):
    one = str(runs / "base0.mcap")  # a single base run: no noise floor, so INCONCLUSIVE (exit 2)
    outputs, _ = run_step(runs, "same.mcap", base=one)
    assert (outputs["verdict"], outputs["exit_code"]) == ("INCONCLUSIVE", "2")
    assert run_step(runs, "same.mcap", inconclusive="pass", base=one)[0]["exit_code"] == "0"


def test_error_is_never_turned_into_a_pass(runs):
    outputs, _ = run_step(runs, "same.mcap", inconclusive="pass", base=str(runs / "nope.mcap"))
    assert (outputs["verdict"], outputs["exit_code"]) == ("ERROR", "2")
