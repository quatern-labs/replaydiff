"""Path comparator: resampled mean/Hausdorff/endpoint distance and pose count delta (synthetic MCAP, no ROS)."""
import json

import pytest

from replaydiff.cli import main
from synth import CLI_TOLERANCES, write_mcap


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    d = tmp_path_factory.mktemp("path")
    for i in range(3):
        write_mcap(d / f"base{i}.mcap", seed=i)
    write_mcap(d / "same.mcap", seed=7)
    write_mcap(d / "end_off.mcap", seed=7, path_end_shift=0.1)
    write_mcap(d / "extra.mcap", seed=7, path_extra=1)
    (d / "tol.yaml").write_text(CLI_TOLERANCES)
    return d


def run_cli(d, head, capsys):
    base = [str(d / f"base{i}.mcap") for i in range(3)]
    code = main(["compare", "--base", *base, "--head", str(d / head), "--tolerances", str(d / "tol.yaml"), "--json"])
    return code, json.loads(capsys.readouterr().out)


def path_failed(rep):
    return {r["quantity"] for r in rep["results"] if r["topic"] == "/plan" and r["verdict"] == "FAIL"}


def test_equal_paths_exit_0(runs, capsys):
    code, rep = run_cli(runs, "same.mcap", capsys)
    assert code == 0 and path_failed(rep) == set()


def test_endpoint_offset_exit_1(runs, capsys):
    code, rep = run_cli(runs, "end_off.mcap", capsys)
    assert code == 1 and "path.endpoint" in path_failed(rep)


def test_pose_count_delta_fails(runs, capsys):
    code, rep = run_cli(runs, "extra.mcap", capsys)
    assert code == 1 and "path.pose_count" in path_failed(rep)
