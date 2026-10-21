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


def near_runs():
    r = {f"base{i}": mk() for i in range(6)}
    for name, g in (("gain_x0.5", 1.025), ("gain_x1.5", 1.075), ("gain10", 1.1)):
        r[name] = mk(gain=g)
    for name, off in (("offset_x0.5", 0.005), ("offset_x1.0", 0.010), ("offset_x1.5", 0.015)):
        r[name] = mk(offset=off)
    r["drop_odom"] = mk(drop_odom=True)
    return r


def test_measured_effect_checks_and_outcomes():
    recs = ex.analyze_rep(near_runs(), CONFIG, {"distro": "humble", "rate": 0.5, "rep": 1, "recording": "sim"})
    g = {r["regression"]: r for r in recs if r["kind"] == "regression" and r["n"] == 3}
    # the gain scales a 0.2-0.35 m/s command (nominal assumes 0.2), so the measured effect differs from the nominal
    assert 0.8 < g["gain_x0.5"]["effect"] < 0.9 and g["gain_x0.5"]["nominal"] == 0.5
    # below 1x: p95 stays under the tolerance, the bias-window check fires: the bias check doing its job
    assert g["gain_x0.5"]["checks"] == ["bias"] and g["gain_x0.5"]["outcome"] == "bias"
    assert "p95" in g["gain_x1.5"]["checks"] and g["gain_x1.5"]["outcome"] == "correct"
    assert g["offset_x0.5"]["verdict"] == "PASS" and g["offset_x0.5"]["outcome"] == "correct"
    assert abs(g["offset_x1.0"]["effect"] - 1.0) < 1e-6 and g["offset_x1.0"]["outcome"] == "acceptable"
    assert g["offset_x1.5"]["checks"] == ["p95"] and g["offset_x1.5"]["expected"] == "FAIL / INCONCLUSIVE"
    assert "missing" in g["drop_odom"]["checks"] and g["drop_odom"]["outcome"] == "correct"
    assert all(r["outcome"] == "correct" for r in recs if r["kind"] == "base_vs_base")


def test_judge_false_fail_and_miss():
    assert ex.judge("regression", "gain", "FAIL", 0.5, ["count"]) == ("PASS (bias FAIL ok)", "false_fail")
    assert ex.judge("regression", "gain", "FAIL", 0.5, ["bias", "p95"])[1] == "false_fail"
    assert ex.judge("regression", "offset", "PASS", 1.4, []) == ("FAIL / INCONCLUSIVE", "miss")
    assert ex.judge("regression", "offset", "INCONCLUSIVE", 1.4, [])[1] == "inconclusive"
    assert ex.judge("regression", "gain", "PASS", 1.05, [])[1] == "acceptable"
    assert ex.judge("base_vs_base", None, "FAIL", None, ["bias"]) == ("PASS", "false_fail")


def test_curve_table():
    recs = ex.analyze_rep(near_runs(), CONFIG, {"distro": "humble", "rate": 0.5, "rep": 1, "recording": "sim"})
    doc = ex.aggregate(recs)
    rows = {(c["regression"], c["n"]): c for c in doc["summary"]["curve"]}
    assert [c["regression"] for c in doc["summary"]["curve"] if c["n"] == 3][:2] == ["base", "drop_odom"]
    c = rows[("gain_x0.5", 3)]
    assert c["verdicts"]["FAIL"] == 1 and c["checks"] == {"bias": 1} and c["false_fail_rate"] == 0.0
    assert rows[("offset_x1.5", 5)]["miss_rate"] == 0.0 and rows[("base", 3)]["total"] == 3
    md = ex.render_md(doc)
    assert "## Detection curve" in md and "| sim | humble | gain_x0.5 | 0.5x | 0.5x | 3 |" in md
    json.dumps(doc)
