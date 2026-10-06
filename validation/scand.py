"""SCAND (ROS 1 bag) -> ROS 2 MCAP for the validation experiment's real-robot recording. Pure Python with rosbags
(Apache-2.0), no ROS install; the real bag is converted in CI only, the unit tests use a tiny synthetic ROS 1 bag.

convert() keeps only the mapped topics inside a time window, renames them to the experiment's names (TOPIC_MAP is the
one place where SCAND names are mapped), converts ROS 1 -> CDR and writes a rosbag2 MCAP. Camera/image topics are
never written. The raw point cloud is written only with keep_cloud, to the local intermediate bag that
pointcloud_to_laserscan reads; check_derived() refuses any image or point-cloud topic in the recording that is
uploaded (privacy rule, validation/RECORDINGS.md).
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys
from pathlib import Path

# SCAND (ROS 1) topic -> experiment topic. Jackal defaults, to be confirmed with `rosbag info` on the pinned bag.
TOPIC_MAP = {
    "/jackal_velocity_controller/odom": "/odom",
    "/bluetooth_teleop/cmd_vel": "/cmd_vel",
    "/tf": "/tf",
    "/tf_static": "/tf_static",
    "/velodyne_points": "/velodyne_points",  # intermediate bag only
}
DERIVED_TOPICS = {"/odom", "/cmd_vel", "/scan", "/tf", "/tf_static"}  # all the uploaded recording may contain
DENY_TYPES = re.compile(r"Image|Camera|PointCloud|Velodyne|theora", re.IGNORECASE)


def _typestore(reader):
    """The bag's own ROS 1 message definitions with the ROS 2 Header (no seq), as rosbags' converter does."""
    from rosbags.typesys import Stores, get_typestore

    ts = get_typestore(Stores.EMPTY)
    ts.register({**reader.typestore.fielddefs,
                 "std_msgs/msg/Header": get_typestore(Stores.ROS2_HUMBLE).fielddefs["std_msgs/msg/Header"]})
    return ts


def convert(src: str, dst: str, start: float, duration: float, topic_map: dict = TOPIC_MAP,
            keep_cloud: bool = False) -> dict[str, int]:
    """Write [bag start + start, + duration) of the mapped topics to the rosbag2 MCAP directory dst. /tf_static
    messages from before the window are kept (they are latched), stamped at the window start. Returns counts."""
    from rosbags.convert.converter import LATCH
    from rosbags.highlevel import AnyReader
    from rosbags.rosbag2 import StoragePlugin, Writer

    counts: dict[str, int] = {}
    with AnyReader([Path(src)]) as reader:
        t0 = reader.start_time + int(start * 1e9)
        t1 = t0 + int(duration * 1e9)
        conns = [c for c in reader.connections if c.topic in topic_map
                 and (not DENY_TYPES.search(c.msgtype) or keep_cloud and "PointCloud2" in c.msgtype)]
        ts = _typestore(reader)
        out = {}
        with Writer(dst, version=8, storage_plugin=StoragePlugin.MCAP) as w:
            for c in conns:
                name = topic_map[c.topic]
                if name not in out:
                    out[name] = w.add_connection(name, c.msgtype, typestore=ts,
                                                 offered_qos_profiles=LATCH if name == "/tf_static" else [])
            for c, t, raw in reader.messages(connections=conns, stop=t1):
                name = topic_map[c.topic]
                if t < t0 and name != "/tf_static":
                    continue
                w.write(out[name], max(t, t0), ts.ros1_to_cdr(raw, c.msgtype))
                counts[name] = counts.get(name, 0) + 1
    return counts


def check_derived(path: str) -> list[str]:
    """Topics of the recording at path (rosbag2 dir or .mcap); raises ValueError on an image or point-cloud topic or
    any topic outside DERIVED_TOPICS. Run before the recording is uploaded."""
    from mcap.reader import make_reader

    files = [path] if path.endswith(".mcap") else sorted(glob.glob(os.path.join(path, "*.mcap")))
    if not files:
        raise ValueError(f"no .mcap in {path}")
    topics = set()
    for f in files:
        with open(f, "rb") as fh:
            summary = make_reader(fh).get_summary()
        for ch in summary.channels.values():
            schema = summary.schemas.get(ch.schema_id)
            if DENY_TYPES.search(schema.name if schema else "") or ch.topic not in DERIVED_TOPICS:
                raise ValueError(f"refusing {ch.topic} ({schema.name if schema else '?'}): not a derived topic")
            topics.add(ch.topic)
    return sorted(topics)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("convert", help="ROS 1 bag -> trimmed, renamed rosbag2 MCAP")
    p.add_argument("src")
    p.add_argument("dst")
    p.add_argument("--start", type=float, required=True, help="window start, s after the bag start")
    p.add_argument("--duration", type=float, required=True, help="window length, s")
    p.add_argument("--keep-cloud", action="store_true", help="also write the point cloud (local intermediate only)")
    p = sub.add_parser("check", help="refuse a recording with image / point-cloud / unexpected topics")
    p.add_argument("path")
    a = ap.parse_args(argv)
    if a.cmd == "convert":
        print(convert(a.src, a.dst, a.start, a.duration, keep_cloud=a.keep_cloud))
    else:
        print("derived recording topics:", " ".join(check_derived(a.path)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
