"""Write a perturbed copy of a rosbag2 recording: add an offset to one numeric field of one topic.

For the public-bag end-to-end check: the job compares a bag with itself (must pass) and with a perturbed copy made
here (must fail). Topic, field and offset are arguments, so the tool does not depend on which bag is used. Pure Python
with rosbags (Apache-2.0), no ROS install. Messages of other topics are copied unchanged, log times are kept.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _field_owner(msg, path: str):
    """(object, attribute name) for a dotted field path such as `linear.x` or `pose.pose.position.x`."""
    *parents, leaf = path.split(".")
    obj = msg
    for p in parents:
        obj = getattr(obj, p)
    if not hasattr(obj, leaf) or not isinstance(getattr(obj, leaf), (int, float)):
        raise ValueError(f"{path} is not a numeric field")
    return obj, leaf


def perturb(src: str, dst: str, topic: str, field: str, offset: float) -> int:
    """Copy rosbag2 `src` to the new MCAP rosbag2 directory `dst`, adding `offset` to `field` of every `topic`
    message. Returns the number of perturbed messages; raises ValueError if the topic is absent or has none."""
    from rosbags.highlevel import AnyReader
    from rosbags.rosbag2 import StoragePlugin, Writer

    changed = 0
    with AnyReader([Path(src)]) as reader:
        if topic not in {c.topic for c in reader.connections}:
            raise ValueError(f"topic {topic} not in {src}")
        with Writer(dst, version=8, storage_plugin=StoragePlugin.MCAP) as w:
            out = {c.id: w.add_connection(c.topic, c.msgtype, typestore=reader.typestore,
                                          offered_qos_profiles=getattr(c.ext, "offered_qos_profiles", []))
                   for c in reader.connections}
            for c, t, raw in reader.messages():
                if c.topic == topic:
                    msg = reader.deserialize(raw, c.msgtype)
                    obj, leaf = _field_owner(msg, field)
                    setattr(obj, leaf, type(getattr(obj, leaf))(getattr(obj, leaf) + offset))
                    raw = bytes(reader.typestore.serialize_cdr(msg, c.msgtype))
                    changed += 1
                w.write(out[c.id], t, raw)
    if not changed:
        raise ValueError(f"no {topic} messages in {src}")
    return changed


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("src", help="rosbag2 directory")
    ap.add_argument("dst", help="output rosbag2 directory (must not exist)")
    ap.add_argument("--topic", required=True)
    ap.add_argument("--field", required=True, help="dotted field path, e.g. linear.x")
    ap.add_argument("--offset", type=float, required=True, help="added to the field of every message")
    a = ap.parse_args(argv)
    print(f"perturbed {perturb(a.src, a.dst, a.topic, a.field, a.offset)} messages on {a.topic}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
