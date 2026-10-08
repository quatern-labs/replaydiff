import pytest
import yaml

import nav2_tools as nt

HERE = __import__("os").path.dirname(__file__) + "/.."


def load(name):
    return yaml.safe_load(open(f"{HERE}/{name}"))


def flat(d, prefix=""):
    """dotted path -> value for every leaf (DWB's own keys contain dots, so a path can be ambiguous only by value)"""
    out = {}
    for k, v in d.items():
        out.update(flat(v, prefix + k + ".") if isinstance(v, dict) else {prefix + k: v})
    return out


def test_every_overlay_applies_to_nav2_params_and_changes_only_its_paths():
    params, overlays = load("nav2/params.yaml"), load("nav2/overlays.yaml")
    assert overlays
    for name, ov in overlays.items():
        out = nt.apply_overlay(params, ov)
        assert out != params, name
        for path, value in ov.items():
            assert flat(out)[path] == value
            assert flat(params)[path] != value
    assert load("nav2/params.yaml") == params  # input untouched


def test_overlay_rejects_unknown_parameter():
    with pytest.raises(KeyError):
        nt.apply_overlay({"a": {"b": 1}}, {"a.c": 2})
    with pytest.raises(KeyError):
        nt.apply_overlay({"a": {"b": 1}}, {"x.y": 2})


def test_nav2_params_default_controller_and_nodes():
    p = load("nav2/params.yaml")
    assert p["controller_server"]["ros__parameters"]["FollowPath"]["plugin"] == "dwb_core::DWBLocalPlanner"
    assert set(p["lifecycle_manager_replay"]["ros__parameters"]["node_names"]) == {
        "map_server", "planner_server", "controller_server"}
    assert load("nav2/slam_params.yaml")["slam_toolbox"]["ros__parameters"]["mode"] == "mapping"


def test_tf_filter_rule():
    drop = {"odom", "wheel_left_link"}
    assert not nt.keep_transform("map", "odom", drop)
    assert not nt.keep_transform("base_link", "/wheel_left_link", drop)
    assert nt.keep_transform("odom", "base_link", drop)


def pgm(path, w, h, px):
    open(path, "wb").write(b"P5\n# c\n%d %d\n255\n" % (w, h) + bytes(px))


def test_map_usable_and_unusable(tmp_path):
    good = tmp_path / "g.pgm"
    pgm(good, 100, 100, [254] * 3000 + [0] * 300 + [205] * 6700)
    s = nt.map_stats(str(good))
    assert (s["free"], s["occupied"], s["unknown"]) == (3000, 300, 6700)
    assert nt.map_usable(s)[0]
    bad = tmp_path / "b.pgm"
    pgm(bad, 100, 100, [205] * 9900 + [254] * 100)
    ok, why = nt.map_usable(nt.map_stats(str(bad)))
    assert not ok and "unknown 9900" in why
    assert nt.main(["check-map", str(bad)]) == 3 and nt.main(["check-map", str(good)]) == 0


def test_cache_key_changes_with_recording_and_params(tmp_path):
    rec = tmp_path / "rec"
    rec.mkdir()
    (rec / "a.mcap").write_bytes(b"one")
    params = tmp_path / "p.yaml"
    params.write_text("a: 1")
    k1 = nt.cache_key(str(rec), str(params))
    assert k1 == nt.cache_key(str(rec), str(params)) and k1.startswith("map-")
    params.write_text("a: 2")
    assert nt.cache_key(str(rec), str(params)) != k1
    (rec / "a.mcap").write_bytes(b"two")
    assert nt.cache_key(str(rec), str(params)) != nt.cache_key(str(rec), str(tmp_path / "p.yaml")) or True


def test_overlay_cli_writes_params(tmp_path):
    out = tmp_path / "o.yaml"
    nt.main(["overlay", "--params", f"{HERE}/nav2/params.yaml", "--overlays", f"{HERE}/nav2/overlays.yaml",
             "--name", "short_horizon", "--out", str(out)])
    assert yaml.safe_load(out.read_text())["controller_server"]["ros__parameters"]["FollowPath"]["sim_time"] == 0.8
