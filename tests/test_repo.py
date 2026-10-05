"""Repo hygiene checks: recordings stay out of git, the workflow parses."""
import pathlib
import subprocess

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_gitignore_blocks_recordings():
    for p in ("a.mcap", "x/y.mcap", "runs/a", "results/a.json", "bag/x.db3"):
        r = subprocess.run(["git", "check-ignore", "-q", p], cwd=ROOT)
        assert r.returncode == 0, p


def test_workflows_parse():
    for f in (ROOT / ".github" / "workflows").glob("*.yml"):
        doc = yaml.safe_load(f.read_text())
        assert "jobs" in doc, f


def test_tolerance_file_loads():
    import compare_proto
    cfg = compare_proto.load_config(str(ROOT / "validation" / "tolerances.yaml"))
    assert set(cfg["topics"]) == {"/sut/cmd_vel", "/sut/odom"}
