import json

import experiment as ex
from synth import CONFIG, TIMES, cmd_series, odom_series, run


def mk(offset=0.0, gain=1.0, drop_odom=False):
    return run(cmd_series(TIMES, lambda t: gain * (0.2 + 0.05 * (t % 3)), None, None),
               None if drop_odom else odom_series(TIMES, offset=offset))


def runs():
    r = {f"base{i}": mk() for i in range(6)}
    r.update({"gain30": mk(gain=1.3), "offset2cm": mk(offset=0.02), "drop_odom": mk(drop_odom=True)})
    return r


def test_analyze_rep_counts_and_verdicts():
    recs = ex.analyze_rep(runs(), CONFIG, {"distro": "humble", "rate": 0.5, "rep": 1})
    b = [r for r in recs if r["kind"] == "base_vs_base"]
    g = [r for r in recs if r["kind"] == "regression"]
    assert len(b) == 3 + 1 and len(g) == 3 * 2  # N=3: heads base3..5; N=5: head base5
    assert all(r["verdict"] == "PASS" for r in b)
    assert all(r["verdict"] == "FAIL" for r in g)
    assert {r["n"] for r in recs} == {3, 5}


def test_summary_rates_and_success():
    recs = ex.analyze_rep(runs(), CONFIG, {"distro": "humble", "rate": 0.5, "rep": 1})
    doc = ex.aggregate(recs, 120.0)
    o = doc["summary"]["overall"]
    assert o["success"] and o["base_vs_base"]["false_fail_rate"] == 0.0
    assert o["regressions"]["inconclusive_rate"] == 0.0
    assert all(g["catch_rate"] == 1.0 for c in doc["summary"]["by_config"] for g in c["per_regression"].values())
    md = ex.render_md(doc)
    assert "offset2cm" in md and "humble" in md
    json.dumps(doc)  # serialisable


def test_summary_flags_false_fail_and_miss():
    base = {"distro": "d", "rate": 1.0, "rep": 1, "n": 3}
    recs = [
        {**base, "kind": "base_vs_base", "regression": None, "head": "base3", "verdict": "FAIL"},
        {**base, "kind": "regression", "regression": "x", "head": "x", "verdict": "PASS"},
        {**base, "kind": "regression", "regression": "y", "head": "y", "verdict": "INCONCLUSIVE"},
    ]
    s = ex.summarize(recs)["overall"]
    assert not s["success"] and s["base_vs_base"]["false_fail"] == 1
    assert s["regressions"]["missed"] == 1 and s["regressions"]["inconclusive_rate"] == 0.5
