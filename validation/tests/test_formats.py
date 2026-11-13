"""--junit, --export-mcap and --plots of `replaydiff compare` (no ROS install)."""
import json
import xml.etree.ElementTree as ET

import pytest
from mcap.reader import make_reader

from replaydiff.cli import main
from synth import CLI_TOLERANCES, write_mcap


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    d = tmp_path_factory.mktemp("fmt")
    for i in range(3):
        write_mcap(d / f"base{i}.mcap", seed=i)
    write_mcap(d / "gain30.mcap", seed=7, gain=1.3)
    (d / "tol.yaml").write_text(CLI_TOLERANCES)
    return d


def compare(d, *extra):
    base = [str(d / f"base{i}.mcap") for i in range(3)]
    return main(["compare", "--base", *base, "--head", str(d / "gain30.mcap"), "--tolerances", str(d / "tol.yaml"),
                 "--json", str(d / "report.json"), *extra])


def test_junit_one_testcase_per_quantity_matching_verdicts(runs):
    assert compare(runs, "--junit", str(runs / "junit.xml")) == 1
    results = json.loads((runs / "report.json").read_text())["results"]
    suite = ET.parse(runs / "junit.xml").getroot()
    cases = suite.findall("testcase")
    assert [(c.get("classname"), c.get("name")) for c in cases] == [(r["topic"], r["quantity"]) for r in results]
    for c, r in zip(cases, results):
        assert (c.find("failure") is not None) == (r["verdict"] == "FAIL")
        assert (c.find("error") is not None) == (r["verdict"] == "INCONCLUSIVE")
    assert int(suite.get("tests")) == len(results)
    assert int(suite.get("failures")) == sum(r["verdict"] == "FAIL" for r in results) > 0


def test_export_mcap_writes_readable_error_topics(runs):
    out = runs / "err.mcap"
    compare(runs, "--export-mcap", str(out))
    with open(out, "rb") as f:
        reader = make_reader(f)
        summary = reader.get_summary()
        topics = {c.topic for c in summary.channels.values()}
        assert topics and all(t.startswith("/replaydiff/error/") for t in topics)
        assert any("cmd_vel" in t for t in topics)
        msgs = [json.loads(m.data) for _s, _c, m in reader.iter_messages()]
    assert msgs and all({"error", "tolerance"} <= m.keys() for m in msgs)
    assert max(abs(m["error"]) for m in msgs) > 0.01  # the gain regression shows in the error


def test_plots_writes_pngs(runs):
    pytest.importorskip("matplotlib")
    compare(runs, "--plots", str(runs / "plots"))
    pngs = list((runs / "plots").glob("*.png"))
    assert pngs and all(p.read_bytes()[:4] == b"\x89PNG" for p in pngs)


def test_plots_without_matplotlib_is_an_error_not_a_crash(runs, monkeypatch, capsys):
    monkeypatch.setitem(__import__("sys").modules, "matplotlib", None)
    assert compare(runs, "--plots", str(runs / "p2")) == 2
    assert "pip install replaydiff[plots]" in capsys.readouterr().err
