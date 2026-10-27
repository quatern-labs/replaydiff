"""JointState comparator: per joint name, tolerance file, joint-set mismatch (synthetic MCAP, no ROS)."""
import json

import pytest

from replaydiff.cli import main
from synth import JOINT_TOLERANCES, write_mcap


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    d = tmp_path_factory.mktemp("joints")
    for i in range(3):
        write_mcap(d / f"base{i}.mcap", seed=i)
    write_mcap(d / "same.mcap", seed=7)
    write_mcap(d / "reordered.mcap", seed=7, joint_reverse=True)
    write_mcap(d / "elbow.mcap", seed=7, joint_offset=0.05)
    write_mcap(d / "nogripper.mcap", seed=7, joints=("shoulder", "elbow"))
    (d / "tol.yaml").write_text(JOINT_TOLERANCES)
    return d


def run_cli(d, head, capsys, tol="tol.yaml"):
    base = [str(d / f"base{i}.mcap") for i in range(3)]
    code = main(["compare", "--base", *base, "--head", str(d / head), "--tolerances", str(d / tol), "--json"])
    return code, json.loads(capsys.readouterr().out)


def failed(rep):
    return {r["quantity"] for r in rep["results"] if r["verdict"] == "FAIL"}


def test_same_passes_and_effort_is_ignored(runs, capsys):
    code, rep = run_cli(runs, "same.mcap", capsys)
    assert code == 0
    quantities = {r["quantity"] for r in rep["results"]}
    assert "joint.elbow.position" in quantities and not any(q.endswith("effort") for q in quantities)


def test_joint_order_does_not_matter(runs, capsys):
    assert run_cli(runs, "reordered.mcap", capsys)[0] == 0


def test_position_offset_fails_only_that_joint(runs, capsys):
    code, rep = run_cli(runs, "elbow.mcap", capsys)
    assert code == 1 and failed(rep) == {"joint.elbow.position"}


def test_missing_joint_fails_as_joint_set(runs, capsys):
    code, rep = run_cli(runs, "nogripper.mcap", capsys)
    assert code == 1 and "joint_set" in failed(rep)


def test_per_joint_tolerance_overrides_wildcard(runs, capsys):
    (runs / "loose.yaml").write_text(JOINT_TOLERANCES.replace("position: 0.01", "position: 0.2"))
    assert run_cli(runs, "elbow.mcap", capsys, "loose.yaml")[0] == 0
