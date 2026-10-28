# SPDX-License-Identifier: Apache-2.0
"""/tf comparator: listed parent/child pairs, direct edges, translation and rotation angle (synthetic MCAP, no ROS)."""
import json

import pytest

from replaydiff.cli import main
from synth import TF_TOLERANCES, write_mcap


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    d = tmp_path_factory.mktemp("tf")
    for i in range(3):
        write_mcap(d / f"base{i}.mcap", seed=i, tf=True)
    write_mcap(d / "same.mcap", seed=7, tf=True)
    write_mcap(d / "shift2cm.mcap", seed=7, tf=True, tf_offset=0.02)
    write_mcap(d / "yaw3deg.mcap", seed=7, tf=True, tf_yaw_deg=3.0)
    (d / "tol.yaml").write_text(TF_TOLERANCES)
    return d


def run_cli(d, head, capsys, tol="tol.yaml"):
    base = [str(d / f"base{i}.mcap") for i in range(3)]
    code = main(["compare", "--base", *base, "--head", str(d / head), "--tolerances", str(d / tol), "--json"])
    return code, json.loads(capsys.readouterr().out)


def failed(rep):
    return {(r["topic"], r["quantity"]) for r in rep["results"] if r["verdict"] == "FAIL"}


def test_same_passes(runs, capsys):
    code, rep = run_cli(runs, "same.mcap", capsys)
    assert code == 0
    assert {r["topic"] for r in rep["results"]} == {"/tf odom->base_link", "/tf base_link->laser"}


def test_translation_regression_fails_only_that_pair(runs, capsys):
    code, rep = run_cli(runs, "shift2cm.mcap", capsys)
    assert code == 1 and failed(rep) == {("/tf odom->base_link", "pose.translation")}


def test_rotation_regression_fails(runs, capsys):
    code, rep = run_cli(runs, "yaw3deg.mcap", capsys)
    assert code == 1 and failed(rep) == {("/tf odom->base_link", "pose.rotation_deg")}


def test_pair_absent_from_head_fails(runs, capsys):
    (runs / "ghost.yaml").write_text(TF_TOLERANCES + "      - {parent: map, child: odom, translation: 0.1}\n")
    code, rep = run_cli(runs, "same.mcap", capsys, "ghost.yaml")
    assert code == 2 and not failed(rep)  # absent from every run: can't tell, not a pass
