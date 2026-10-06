"""SCAND conversion on a tiny synthetic ROS 1 bag written with rosbags (no download, no ROS)."""
from pathlib import Path

import pytest
from rosbags.convert.converter import default_message
from rosbags.highlevel import AnyReader
from rosbags.rosbag1 import Writer
from rosbags.typesys import Stores, get_types_from_msg, get_typestore

import scand

TS = get_typestore(Stores.ROS1_NOETIC)
TS.register(get_types_from_msg("geometry_msgs/TransformStamped[] transforms", "tf2_msgs/msg/TFMessage"))
T0 = 1_600_000_000 * 10**9
TOPICS = {  # ROS 1 topic -> type
    "/jackal_velocity_controller/odom": "nav_msgs/msg/Odometry",
    "/bluetooth_teleop/cmd_vel": "geometry_msgs/msg/Twist",
    "/tf": "tf2_msgs/msg/TFMessage",
    "/tf_static": "tf2_msgs/msg/TFMessage",
    "/velodyne_points": "sensor_msgs/msg/PointCloud2",
    "/camera/rgb/image_raw/compressed": "sensor_msgs/msg/CompressedImage",
    "/joint_states": "sensor_msgs/msg/JointState",
}


def synth_bag(path: Path) -> None:
    """10 s at 10 Hz on every topic except /tf_static (once, at the start); odom x = time in s."""
    with Writer(path) as w:
        conns = {t: w.add_connection(t, ty, typestore=TS, latching=int(t == "/tf_static")) for t, ty in TOPICS.items()}
        for k in range(100):
            t = T0 + k * 10**8
            for topic, ty in TOPICS.items():
                if topic == "/tf_static" and k:
                    continue
                msg = default_message(TS, ty)
                if topic.endswith("odom"):
                    msg.pose.pose.position.x = k / 10
                    msg.header.stamp.sec, msg.header.seq = t // 10**9, k
                    msg.header.stamp.nanosec = t % 10**9
                w.write(conns[topic], t, TS.serialize_ros1(msg, ty))


@pytest.fixture
def bag(tmp_path):
    p = tmp_path / "scand.bag"
    synth_bag(p)
    return p


def read(path):
    out = {}
    with AnyReader([Path(path)]) as r:
        for c, t, raw in r.messages():
            out.setdefault(c.topic, []).append((t, r.deserialize(raw, c.msgtype)))
    return out


def test_convert_trims_renames_and_drops_camera(bag, tmp_path):
    counts = scand.convert(str(bag), str(tmp_path / "out"), start=3.0, duration=4.0)
    assert counts == {"/odom": 40, "/cmd_vel": 40, "/tf": 40, "/tf_static": 1}
    msgs = read(tmp_path / "out")
    assert set(msgs) == {"/odom", "/cmd_vel", "/tf", "/tf_static"}
    odom = msgs["/odom"]
    assert odom[0][0] == T0 + 3 * 10**9 and odom[-1][0] < T0 + 7 * 10**9
    assert [round(m.pose.pose.position.x, 3) for _, m in odom[:2]] == [3.0, 3.1]  # payload survives ROS 1 -> CDR
    assert odom[0][1].header.stamp.sec == (T0 + 3 * 10**9) // 10**9 and not hasattr(odom[0][1].header, "seq")
    assert msgs["/tf_static"][0][0] == T0 + 3 * 10**9  # latched transform kept, stamped at the window start
    assert scand.check_derived(str(tmp_path / "out")) == ["/cmd_vel", "/odom", "/tf", "/tf_static"]


def test_point_cloud_only_in_intermediate_and_refused_by_check(bag, tmp_path):
    counts = scand.convert(str(bag), str(tmp_path / "mid"), start=0.0, duration=2.0, keep_cloud=True)
    assert counts["/velodyne_points"] == 20 and "/camera/rgb/image_raw/compressed" not in read(tmp_path / "mid")
    with pytest.raises(ValueError, match="velodyne_points"):
        scand.check_derived(str(tmp_path / "mid"))


def test_topic_map_is_the_only_mapping(bag, tmp_path):
    counts = scand.convert(str(bag), str(tmp_path / "o"), 0.0, 1.0, topic_map={"/jackal_velocity_controller/odom": "/odom"})
    assert counts == {"/odom": 10}
