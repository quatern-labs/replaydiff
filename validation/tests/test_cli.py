# SPDX-License-Identifier: Apache-2.0
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
                                           ("plan_off.mcap", "path.")])
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


def test_markdown_report_and_inconclusive_flag(runs, tmp_path):
    md = tmp_path / "report.md"
    assert run_cli(runs, "gain30.mcap", "--markdown", str(md)) == 1
    text = md.read_text()
    assert text.startswith("### replaydiff: FAIL") and "VERDICT FAIL" in text
    assert run_cli(runs, "same.mcap", "--inconclusive", "pass") == 0


def test_inconclusive_pass_turns_2_into_0_but_not_errors(runs):
    one = ["--base", str(runs / "base0.mcap"), "--head", str(runs / "same.mcap"), "--tolerances", str(runs / "tol.yaml")]
    assert main(["compare", *one, "--inconclusive", "pass"]) == 0
    bad = ["--base", str(runs / "nope.mcap"), str(runs / "base0.mcap"), "--head", str(runs / "same.mcap"),
           "--tolerances", str(runs / "tol.yaml")]
    assert main(["compare", *bad, "--inconclusive", "pass"]) == 2


def test_action_yml_shape():
    import pathlib
    import yaml
    a = yaml.safe_load((pathlib.Path(__file__).parents[2] / "action.yml").read_text())
    assert a["runs"]["using"] == "composite"
    assert {"base", "head", "config"} <= {k for k, v in a["inputs"].items() if v.get("required")}
    assert all("run" in s or "uses" in s for s in a["runs"]["steps"])
    assert "exit" in a["runs"]["steps"][-1]["run"]
