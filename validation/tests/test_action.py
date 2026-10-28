"""action.yml shape and the report.md the action posts (no ROS, no GitHub)."""
from pathlib import Path

import yaml

from replaydiff.cli import main
from synth import CLI_TOLERANCES, write_mcap

ROOT = Path(__file__).resolve().parents[2]


def test_action_yml_is_a_composite_with_required_inputs():
    a = yaml.safe_load((ROOT / "action.yml").read_text())
    assert a["runs"]["using"] == "composite"
    assert {"base", "head", "config"} <= {k for k, v in a["inputs"].items() if v.get("required")}
    steps = a["runs"]["steps"]
    run = "\n".join(s.get("run", "") for s in steps)
    assert "replaydiff compare" in run and "--markdown report.md" in run
    comment = next(s for s in steps if "sticky-pull-request-comment" in s.get("uses", ""))
    assert comment["with"]["path"] == "report.md" and "pull_request" in comment["if"]
    assert steps[-1]["run"].rstrip().endswith('exit "$CODE"')


def _compare(tmp_path, head_kw):
    for i in range(3):
        write_mcap(tmp_path / f"base{i}.mcap", seed=i)
    write_mcap(tmp_path / "head.mcap", seed=7, **head_kw)
    (tmp_path / "tol.yaml").write_text(CLI_TOLERANCES)
    md = tmp_path / "report.md"
    code = main(["compare", "--base", *[str(tmp_path / f"base{i}.mcap") for i in range(3)],
                 "--head", str(tmp_path / "head.mcap"), "--tolerances", str(tmp_path / "tol.yaml"),
                 "--markdown", str(md)])
    return code, md.read_text()


def test_markdown_pass(tmp_path):
    code, md = _compare(tmp_path, {})
    assert code == 0 and md.startswith("### replaydiff: PASS") and "| verdict |" in md
    assert "quatern explain" not in md


def test_markdown_fail_has_only_the_explain_pointer(tmp_path):
    code, md = _compare(tmp_path, {"gain": 1.3})
    assert code == 1 and "### replaydiff: FAIL" in md and "linear.x" in md
    assert md.rstrip().endswith("See why: quatern explain <result>")
