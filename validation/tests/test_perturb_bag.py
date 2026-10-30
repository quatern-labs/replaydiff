"""perturb_bag on a tiny synthetic rosbag2, then through the compare step: self -> exit 0, perturbed -> exit 1."""
import glob
from pathlib import Path

import pytest
pytest.importorskip("rosbags")
from rosbags.rosbag2 import StoragePlugin, Writer
from rosbags.typesys import Stores, get_typestore

import compare_proto
import perturb_bag

TS = get_typestore(Stores.ROS2_HUMBLE)
TWIST = "geometry_msgs/msg/Twist"
T0 = 1_000 * 10**9
CONFIG = """
version: 1
defaults: {match: nearest, max_dt: 0.02, skip_first: 1.0, stat: p95}
rate: {rel: 0.10}
topics:
  /cmd_vel:
    fields:
      linear.x: {abs: 0.01}
"""


def synth_bag(path: Path) -> None:
    """20 s at 20 Hz: /cmd_vel with linear.x = 0.2, /other with linear.x = 1.0."""
    with Writer(path, version=8, storage_plugin=StoragePlugin.MCAP) as w:
        conns = {t: w.add_connection(t, TWIST, typestore=TS) for t in ("/cmd_vel", "/other")}
        for k in range(400):
            for topic, x in (("/cmd_vel", 0.2), ("/other", 1.0)):
                msg = TS.types[TWIST](linear=TS.types["geometry_msgs/msg/Vector3"](x=x, y=0.0, z=0.0),
                                      angular=TS.types["geometry_msgs/msg/Vector3"](x=0.0, y=0.0, z=0.0))
                w.write(conns[topic], T0 + k * 5 * 10**7, bytes(TS.serialize_cdr(msg, TWIST)))


def mcap_of(d: Path) -> str:
    return glob.glob(str(d / "*.mcap"))[0]


@pytest.fixture
def bags(tmp_path):
    synth_bag(tmp_path / "orig")
    return tmp_path


def test_only_the_named_field_of_the_named_topic_changes(bags):
    assert perturb_bag.perturb(str(bags / "orig"), str(bags / "p"), "/cmd_vel", "linear.x", 0.05) == 400
    orig = compare_proto.read_mcap(mcap_of(bags / "orig"))
    pert = compare_proto.read_mcap(mcap_of(bags / "p"))
    assert set(pert) == {"/cmd_vel", "/other"}
    first = lambda r, t: r[t].msgs[0]
    assert first(pert, "/cmd_vel").linear.x == pytest.approx(0.25)
    assert first(pert, "/cmd_vel").angular.z == 0.0
    assert first(pert, "/other").linear.x == first(orig, "/other").linear.x == 1.0
    assert list(pert["/cmd_vel"].t_log) == list(orig["/cmd_vel"].t_log)  # log times kept


def test_compare_self_passes_and_perturbed_fails(bags, tmp_path):
    perturb_bag.perturb(str(bags / "orig"), str(bags / "p"), "/cmd_vel", "linear.x", 0.05)
    cfg = tmp_path / "tol.yaml"
    cfg.write_text(CONFIG)
    o, p = mcap_of(bags / "orig"), mcap_of(bags / "p")
    assert compare_proto.main(["--config", str(cfg), "--base", o, o, "--head", o]) == 0
    assert compare_proto.main(["--config", str(cfg), "--base", o, o, "--head", p]) == 1


def test_bad_topic_or_field_is_an_error(bags):
    with pytest.raises(ValueError, match="not in"):
        perturb_bag.perturb(str(bags / "orig"), str(bags / "a"), "/nope", "linear.x", 1.0)
    with pytest.raises(Exception):
        perturb_bag.perturb(str(bags / "orig"), str(bags / "b"), "/cmd_vel", "linear.q", 1.0)
