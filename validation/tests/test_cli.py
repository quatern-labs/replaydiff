"""`replaydiff compare` end to end on a small synthetic MCAP fixture (no ROS install)."""
import json

import pytest

from replaydiff.cli import main
from synth import CLI_TOLERANCES, write_mcap


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    d = tmp_path_factory.mktemp("runs")
    for i in range(3):
        write_mcap(d / f"base{i}.mcap", seed=i)
    write_mcap(d / "same.mcap", seed=7)
    write_mcap(d / "gain30.mcap", seed=7, gain=1.3)
    write_mcap(d / "offset2cm.mcap", seed=7, offset=0.02)
    write_mcap(d / "plan_off.mcap", seed=7, path_shift=0.3)
    write_mcap(d / "joint_off.mcap", seed=7, joint_shift=0.05)
    write_mcap(d / "joint_missing.mcap", seed=7, joints=("a",))
    (d / "tol.yaml").write_text(CLI_TOLERANCES)
    assert sum(p.stat().st_size for p in d.glob("*.mcap")) < 200_000
    return d


def run_cli(d, head, *extra):
    base = [str(d / f"base{i}.mcap") for i in range(3)]
    return main(["compare", "--base", *base, "--head", str(d / head), "--tolerances", str(d / "tol.yaml"), *extra])


def test_same_within_tolerance_exits_0(runs, capsys):
    assert run_cli(runs, "same.mcap") == 0
    assert "VERDICT PASS" in capsys.readouterr().out


@pytest.mark.parametrize("head,quantity", [("gain30.mcap", "linear.x"), ("offset2cm.mcap", "pose.translation"),
                                           ("plan_off.mcap", "path."),
                                           ("joint_off.mcap", "b.position"),
                                           ("joint_missing.mcap", "joint_set")])
def test_injected_regression_exits_1(runs, capsys, head, quantity):
    assert run_cli(runs, head, "--json") == 1
    rep = json.loads(capsys.readouterr().out)
    assert rep["verdict"] == "FAIL"
    failed = {r["quantity"] for r in rep["results"] if r["verdict"] == "FAIL"}
    assert failed and all(q.startswith(quantity) for q in failed)


def test_cli_exit_code_matches_evaluate(runs):
    from replaydiff import compare as cp
    cfg = __import__("yaml").safe_load(CLI_TOLERANCES)
    for head in ("same.mcap", "gain30.mcap", "offset2cm.mcap"):
        base = [cp.read_mcap(str(runs / f"base{i}.mcap")) for i in range(3)]
        assert cp.evaluate(base, cp.read_mcap(str(runs / head)), cfg).exit_code == run_cli(runs, head)


def test_unreadable_input_exits_2(runs, capsys):
    assert main(["compare", "--base", str(runs / "nope.mcap"), str(runs / "base0.mcap"),
                 "--head", str(runs / "same.mcap"), "--tolerances", str(runs / "tol.yaml")]) == 2
    assert "error" in capsys.readouterr().err


def test_single_base_run_exits_2(runs):
    assert main(["compare", "--base", str(runs / "base0.mcap"), "--head", str(runs / "same.mcap"),
                 "--tolerances", str(runs / "tol.yaml")]) == 2


def test_usage_without_subcommand_exits_2():
    assert main([]) == 2


def test_joint_states_matched_by_name_not_index(runs, capsys):
    # odd seeds publish the joints in reverse order; the equal run must still pass, with effort ignored
    assert run_cli(runs, "same.mcap", "--json") == 0
    rows = {(r["topic"], r["quantity"]) for r in json.loads(capsys.readouterr().out)["results"]}
    assert {("/joint_states", "a.position"), ("/joint_states", "b.velocity")} <= rows
    assert not any(q.endswith("effort") for _, q in rows)
