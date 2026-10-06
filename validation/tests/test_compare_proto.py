import math
import numpy as np
import pytest

import compare_proto as cp
from synth import CONFIG, TIMES, cmd_series, odom_series, run


def vx(t):
    return 0.2 + 0.05 * math.sin(t / 3)


def make(offset=0.0, gain=1.0, jitter=None, seed=0, drop_cmd=False, drop_odom=False, times=TIMES):
    rng = np.random.default_rng(seed)
    cmd = None if drop_cmd else cmd_series(times, lambda t: gain * vx(t), jitter, rng)
    odm = None if drop_odom else odom_series(times, offset=offset, jitter=jitter, rng=rng)
    return run(cmd, odm)


def verdicts(report):
    return {(r.topic, r.quantity): r.verdict for r in report.results}


def test_identical_runs_pass():
    rep = cp.evaluate([make(), make(), make()], make(), CONFIG)
    assert rep.verdict == "PASS" and rep.exit_code == 0
    assert all(r.verdict == "PASS" for r in rep.results)
    assert {r.quantity for r in rep.results} >= {"linear.x", "pose.translation", "rate"}


def test_two_cm_offset_fails_on_translation_only():
    rep = cp.evaluate([make(), make(), make()], make(offset=0.02), CONFIG)
    v = verdicts(rep)
    assert rep.verdict == "FAIL" and rep.exit_code == 1
    assert v[("/odom", "pose.translation")] == "FAIL"
    assert v[("/cmd_vel", "linear.x")] == "PASS"
    assert rep.headline().quantity == "pose.translation"
    assert rep.headline().head_error == pytest.approx(0.02, abs=1e-6)


def test_gain_change_fails_and_bias_test_fires():
    rep = cp.evaluate([make(), make(), make()], make(gain=1.3), CONFIG)
    r = next(r for r in rep.results if r.quantity == "linear.x")
    assert r.verdict == "FAIL"
    assert r.bias is not None and r.bias > 0.005


def test_small_systematic_shift_caught_by_bias_not_p95():
    # 0.007 shift: under the 0.01 tolerance, over the 0.005 bias limit; base runs are exactly equal
    rep = cp.evaluate([make(), make(), make()], make(gain=1.0, jitter=None), CONFIG)
    assert rep.verdict == "PASS"
    shifted = make()
    shifted["/cmd_vel"] = cmd_series(TIMES, lambda t: vx(t) + 0.007)
    rep = cp.evaluate([make(), make(), make()], shifted, CONFIG)
    r = next(r for r in rep.results if r.quantity == "linear.x")
    assert r.verdict == "FAIL" and r.head_error < 0.01
    assert any("window bias" in s for s in r.reasons)


def test_noisy_base_is_inconclusive_not_fail():
    bases = [make(jitter=0.01, seed=s) for s in (1, 2, 3)]  # p95 pair noise ~0.02 > 0.5 * 0.01
    rep = cp.evaluate(bases, make(gain=1.3, jitter=0.01, seed=9), CONFIG)
    r = next(r for r in rep.results if r.quantity == "linear.x")
    assert r.verdict == "INCONCLUSIVE" and r.noise > 0.005
    assert any("can't tell" in s for s in r.reasons)
    assert rep.verdict == "INCONCLUSIVE" and rep.exit_code == 2


def test_noise_never_widens_the_tolerance():
    # modest noise (below the 0.5 x tolerance gate) with a real 2 cm offset: still FAIL
    bases = [make(jitter=0.001, seed=s) for s in (1, 2, 3)]
    rep = cp.evaluate(bases, make(offset=0.02, jitter=0.001, seed=9), CONFIG)
    assert verdicts(rep)[("/odom", "pose.translation")] == "FAIL"


def test_missing_topic_fails_and_is_not_interpolated_over():
    rep = cp.evaluate([make(), make(), make()], make(drop_odom=True), CONFIG)
    v = verdicts(rep)
    assert rep.verdict == "FAIL"
    assert v[("/odom", "pose.translation")] == "FAIL"
    assert v[("/odom", "rate")] == "FAIL"
    assert v[("/cmd_vel", "linear.x")] == "PASS"


def test_dropped_messages_fail_rate_check_even_if_values_match():
    thinned = TIMES[np.arange(len(TIMES)) % 5 != 0]  # 20% fewer messages, remaining values identical
    head = make()
    head["/cmd_vel"] = cmd_series(thinned, vx)
    rep = cp.evaluate([make(), make(), make()], head, CONFIG)
    v = verdicts(rep)
    assert v[("/cmd_vel", "rate")] == "FAIL"
    assert rep.verdict == "FAIL"


def test_gap_in_base_is_not_interpolated_over():
    gap = TIMES[(TIMES < 10) | (TIMES > 20)]  # 10 s hole in every base run's odom
    bases = [make(), make(), make()]
    for b in bases:
        b["/odom"] = odom_series(gap)
    rep = cp.evaluate(bases, make(), CONFIG)
    r = next(r for r in rep.results if r.quantity == "pose.translation")
    assert r.unmatched > 100  # head messages inside the hole were left unmatched, not interpolated


def test_single_base_run_is_inconclusive():
    rep = cp.evaluate([make()], make(), CONFIG)
    assert rep.verdict == "INCONCLUSIVE"


def test_missing_topic_in_a_base_run_is_inconclusive():
    rep = cp.evaluate([make(), make(drop_odom=True), make()], make(), CONFIG)
    assert verdicts(rep)[("/odom", "*")] == "INCONCLUSIVE"


def test_rotation_angle_and_slerp():
    q = np.array([[0, 0, 0, 1.0]])
    half = math.radians(10) / 2
    qz = np.array([[0, 0, math.sin(half), math.cos(half)]])
    assert cp._quat_angle_deg(q, qz)[0] == pytest.approx(10.0, abs=1e-9)
    assert cp._quat_angle_deg(q, -q)[0] == pytest.approx(0.0, abs=1e-6)
    mid = cp._slerp(q, qz, np.array([0.5]))
    assert cp._quat_angle_deg(q, mid)[0] == pytest.approx(5.0, abs=1e-6)


def test_rel_tolerance_is_applied_like_isclose():
    q = cp.Quantity("x", lambda m: [m.linear.x], 0.0, rel=0.1)
    from synth import twist
    a = cp.make_series([(1.0, twist(1.0, 0))])
    b = cp.make_series([(1.0, twist(1.05, 0))])
    e = cp.pair_errors(a, b, q, {**cp.DEFAULTS}, 0.0, 10.0)
    assert e.err[0] == 0.0  # 0.05 <= 0.1 * 1.0
    b = cp.make_series([(1.0, twist(1.2, 0))])
    e = cp.pair_errors(a, b, q, {**cp.DEFAULTS}, 0.0, 10.0)
    assert e.err[0] == pytest.approx(0.1)


def test_mcap_round_trip(tmp_path):
    """Write real ROS 2 CDR messages to an MCAP and read them back through the reader."""
    writer_mod = pytest.importorskip("mcap_ros2.writer")
    path = tmp_path / "t.mcap"
    twist_def = ("geometry_msgs/Vector3 linear\ngeometry_msgs/Vector3 angular\n"
                 "================================================================================\n"
                 "MSG: geometry_msgs/Vector3\nfloat64 x\nfloat64 y\nfloat64 z\n")
    with open(path, "wb") as f:
        w = writer_mod.Writer(f)
        schema = w.register_msgdef("geometry_msgs/msg/Twist", twist_def)
        for i in range(5):
            w.write_message("/cmd_vel", schema, {"linear": {"x": 0.1 * i, "y": 0.0, "z": 0.0},
                                                 "angular": {"x": 0.0, "y": 0.0, "z": 0.5}},
                            log_time=int((1 + i * 0.1) * 1e9), publish_time=0)
        w.finish()
    r = cp.read_mcap(str(path))
    s = r["/cmd_vel"]
    assert len(s.msgs) == 5 and s.t_log[1] == pytest.approx(1.1)
    assert s.msgs[2].linear.x == pytest.approx(0.2) and cp.twist_of(s.msgs[2]).angular.z == 0.5
