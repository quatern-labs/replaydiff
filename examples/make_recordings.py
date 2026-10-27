"""Write a tiny synthetic recording set for the README example (needs no ROS install).

Each file is one replay run of a robot driving at about 0.2 m/s: /cmd_vel (geometry_msgs/Twist) and /odom
(nav_msgs/Odometry), 10 Hz for 40 s. base0-2 are the same code replayed three times (each with its own small
noise), head_same.mcap is a new version with the same behavior, head_regressed.mcap a new version that drives
30% faster. The files are generated, not committed (recordings stay out of git).

usage: python examples/make_recordings.py [OUTPUT_DIR]   (default: the examples/ directory next to this file)
"""
import math
import os
import pathlib
import sys

import numpy as np
from mcap_ros2.writer import Writer

SEP = "=" * 80 + "\n"
V3 = "MSG: geometry_msgs/Vector3\nfloat64 x\nfloat64 y\nfloat64 z\n"
POSE = "MSG: geometry_msgs/Pose\ngeometry_msgs/Point position\ngeometry_msgs/Quaternion orientation\n"
TWIST = "MSG: geometry_msgs/Twist\ngeometry_msgs/Vector3 linear\ngeometry_msgs/Vector3 angular\n"
HEADER = "MSG: std_msgs/Header\nbuiltin_interfaces/Time stamp\nstring frame_id\n"
TIME = "MSG: builtin_interfaces/Time\nint32 sec\nuint32 nanosec\n"
POINT = "MSG: geometry_msgs/Point\nfloat64 x\nfloat64 y\nfloat64 z\n"
QUAT = "MSG: geometry_msgs/Quaternion\nfloat64 x\nfloat64 y\nfloat64 z\nfloat64 w\n"
DEFS = {
    "geometry_msgs/msg/Twist": "geometry_msgs/Vector3 linear\ngeometry_msgs/Vector3 angular\n" + SEP + V3,
    "nav_msgs/msg/Odometry": (
        "std_msgs/Header header\ngeometry_msgs/PoseWithCovariance pose\ngeometry_msgs/TwistWithCovariance twist\n"
        + SEP + HEADER + SEP + TIME
        + SEP + "MSG: geometry_msgs/PoseWithCovariance\ngeometry_msgs/Pose pose\n" + SEP + POSE + SEP + POINT
        + SEP + QUAT
        + SEP + "MSG: geometry_msgs/TwistWithCovariance\ngeometry_msgs/Twist twist\n" + SEP + TWIST + SEP + V3),
}


def xyz(x=0.0, y=0.0, z=0.0):
    return {"x": x, "y": y, "z": z}


def write_run(path, seed, gain=1.0):
    rng = np.random.default_rng(seed)
    with open(path, "wb") as f:
        w = Writer(f)
        schemas = {k: w.register_msgdef(k, v) for k, v in DEFS.items()}
        for t in np.arange(1.0, 41.0, 0.1):
            ns = int(t * 1e9)
            vx = gain * (0.2 + 0.05 * math.sin(t / 3)) + rng.normal(0, 1e-4)
            w.write_message("/cmd_vel", schemas["geometry_msgs/msg/Twist"],
                            {"linear": xyz(vx), "angular": xyz(0, 0, 0.1)}, log_time=ns, publish_time=ns)
            header = {"stamp": {"sec": int(t), "nanosec": int(round((t % 1) * 1e9))}, "frame_id": "odom"}
            w.write_message("/odom", schemas["nav_msgs/msg/Odometry"], {
                "header": header,
                "pose": {"pose": {"position": xyz(0.2 * t + rng.normal(0, 1e-4)),
                                  "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}}},
                "twist": {"twist": {"linear": xyz(0.2), "angular": xyz()}}}, log_time=ns, publish_time=ns)
        w.finish()


def main(argv):
    out = pathlib.Path(argv[0]) if argv else pathlib.Path(__file__).resolve().parent
    out.mkdir(parents=True, exist_ok=True)
    for i in range(3):
        write_run(out / f"base{i}.mcap", seed=i)
    write_run(out / "head_same.mcap", seed=10)
    write_run(out / "head_regressed.mcap", seed=10, gain=1.3)
    print(f"wrote 5 recordings to {os.path.relpath(out)}")


if __name__ == "__main__":
    main(sys.argv[1:])
