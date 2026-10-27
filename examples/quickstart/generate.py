"""Write a tiny synthetic recording set for the README quickstart (no ROS install needed).

Usage: python examples/quickstart/generate.py OUT_DIR

Writes base0..base2.mcap (three replays of the "old" code: same behavior, small noise),
same.mcap (new code, same behavior) and slower.mcap (new code, /cmd_vel speed scaled by 1.3).
Each file holds /cmd_vel (Twist) and /odom (Odometry) for 20 s at 20 Hz, a few KB in total.
The recordings are generated, never committed (*.mcap is gitignored).
"""
import math
import pathlib
import sys

import numpy as np
from mcap_ros2.writer import Writer

SEP = "=" * 80 + "\n"
V3 = "MSG: geometry_msgs/Vector3\nfloat64 x\nfloat64 y\nfloat64 z\n"
TW = "MSG: geometry_msgs/Twist\ngeometry_msgs/Vector3 linear\ngeometry_msgs/Vector3 angular\n"
DEFS = {
    "geometry_msgs/msg/Twist": "geometry_msgs/Vector3 linear\ngeometry_msgs/Vector3 angular\n" + SEP + V3,
    "nav_msgs/msg/Odometry": (
        "std_msgs/Header header\ngeometry_msgs/PoseWithCovariance pose\n"
        "geometry_msgs/TwistWithCovariance twist\n" + SEP
        + "MSG: std_msgs/Header\nbuiltin_interfaces/Time stamp\nstring frame_id\n" + SEP
        + "MSG: builtin_interfaces/Time\nint32 sec\nuint32 nanosec\n" + SEP
        + "MSG: geometry_msgs/PoseWithCovariance\ngeometry_msgs/Pose pose\n" + SEP
        + "MSG: geometry_msgs/Pose\ngeometry_msgs/Point position\ngeometry_msgs/Quaternion orientation\n" + SEP
        + "MSG: geometry_msgs/Point\nfloat64 x\nfloat64 y\nfloat64 z\n" + SEP
        + "MSG: geometry_msgs/Quaternion\nfloat64 x\nfloat64 y\nfloat64 z\nfloat64 w\n" + SEP
        + "MSG: geometry_msgs/TwistWithCovariance\ngeometry_msgs/Twist twist\n" + SEP + TW + SEP + V3),
}


def xyz(x=0.0, y=0.0, z=0.0):
    return {"x": x, "y": y, "z": z}


def write_run(path, seed, gain=1.0, jitter=1e-4):
    rng = np.random.default_rng(seed)
    with open(path, "wb") as f:
        w = Writer(f)
        schema = {k: w.register_msgdef(k, v) for k, v in DEFS.items()}
        for t in np.arange(1.0, 21.0, 0.05):
            ns = int(t * 1e9)
            vx = gain * (0.2 + 0.05 * math.sin(t / 3)) + rng.normal(0, jitter)
            w.write_message("/cmd_vel", schema["geometry_msgs/msg/Twist"],
                            {"linear": xyz(vx), "angular": xyz(0, 0, 0.1)}, log_time=ns, publish_time=ns)
            stamp = {"sec": int(t + 1), "nanosec": int(round((t % 1) * 1e9))}
            w.write_message("/odom", schema["nav_msgs/msg/Odometry"], {
                "header": {"stamp": stamp, "frame_id": "odom"},
                "pose": {"pose": {"position": xyz(0.2 * t + rng.normal(0, jitter)),
                                  "orientation": {"x": 0, "y": 0, "z": 0, "w": 1}}},
                "twist": {"twist": {"linear": xyz(0.2), "angular": xyz()}}}, log_time=ns, publish_time=ns)
        w.finish()


def main(out):
    out = pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for i in range(3):
        write_run(out / f"base{i}.mcap", seed=i)
    write_run(out / "same.mcap", seed=7)
    write_run(out / "slower.mcap", seed=7, gain=1.3)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) == 2 else sys.exit(__doc__))
