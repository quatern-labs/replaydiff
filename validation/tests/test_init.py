"""`replaydiff init` on a synthetic MCAP (no ROS install)."""
import yaml
import pytest

from replaydiff.cli import main
from synth import write_mcap


@pytest.fixture(scope="module")
def files(tmp_path_factory):
    d = tmp_path_factory.mktemp("init")
    for i in range(3):
        write_mcap(d / f"base{i}.mcap", seed=i, tf=True)
    write_mcap(d / "head.mcap", seed=7, tf=True)
    return d


def init(d, out, *extra):
    return main(["init", "--recording", str(d / "base0.mcap"), "--out", str(d / out), *extra])


def test_lists_topics_and_types_unmeasured(files):
    assert init(files, "plain.yaml") == 0
    text = (files / "plain.yaml").read_text()
    cfg = yaml.safe_load(text)
    assert set(cfg["topics"]) == {"/cmd_vel", "/odom", "/plan", "/joint_states", "/tf"}
    assert "fields" in cfg["topics"]["/cmd_vel"] and "pose" in cfg["topics"]["/odom"]
    assert cfg["topics"]["/tf"]["pairs"][0]["parent"] == "odom"
    assert "measured, review" not in text.replace("`# measured, review`", "")


def test_measured_tolerances_marked_and_load_in_compare(files, capsys):
    base = [str(files / f"base{i}.mcap") for i in range(3)]
    assert init(files, "m.yaml", "--base", *base) == 0
    text = (files / "m.yaml").read_text()
    assert "# measured, review" in text.split("\n", 5)[-1]
    cfg = yaml.safe_load(text)
    assert 0 < cfg["topics"]["/cmd_vel"]["fields"]["linear.x"]["abs"] < 0.01
    assert main(["compare", "--base", *base, "--head", str(files / "head.mcap"),
                 "--tolerances", str(files / "m.yaml"), "--json"]) == 0
    assert '"verdict": "PASS"' in capsys.readouterr().out


def test_refuses_overwrite_and_single_base(files, capsys):
    assert init(files, "plain.yaml") == 2
    assert init(files, "x.yaml", "--base", str(files / "base1.mcap")) == 2
    assert "error" in capsys.readouterr().err
