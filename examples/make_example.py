"""Write the example recordings for the README quickstart: three base runs and one head run, as MCAP files.

    python examples/make_example.py [OUT_DIR]      (default: examples/recordings)

Synthetic data, generated here with a fixed seed (no ROS install, nothing downloaded): a /cmd_vel Twist and an
/odom Odometry stream, 10 Hz for 20 s. The base runs differ only by small noise; the head run drives 20% faster
than the base, so `replaydiff compare` reports a regression. Recordings are not committed (*.mcap is ignored).
"""
import math
import pathlib
import sys

import numpy as np
from mcap_ros2.writer import Writer

SEP = "=" * 80 + "\n"
V3 = "MSG: geometry_msgs/Vector3\nfloat64 x\nfloat64 y\nfloat64 z\n"
DEFS = {
    "geometry_msgs/msg/Twist": "geometry_msgs/Vector3 linear\ngeometry_msgs/Vector3 angular\n" + SEP + V3,
    "nav_msgs/msg/Odometry": (
        "std_msgs/Header header\ngeometry_msgs/PoseWithCovariance pose\n" + SEP
        + "MSG: std_msgs/Header\nbuiltin_interfaces/Time stamp\nstring frame_id\n" + SEP
        + "MSG: builtin_interfaces/Time\nint32 sec\nuint32 nanosec\n" + SEP
        + "MSG: geometry_msgs/PoseWithCovariance\ngeometry_msgs/Pose pose\n" + SEP
        + "MSG: geometry_msgs/Pose\ngeometry_msgs/Point position\ngeometry_msgs/Quaternion orientation\n" + SEP
        + "MSG: geometry_msgs/Point\nfloat64 x\nfloat64 y\nfloat64 z\n" + SEP
        + "MSG: geometry_msgs/Quaternion\nfloat64 x\nfloat64 y\nfloat64 z\nfloat64 w\n"),
}


def xyz(x=0.0, y=0.0, z=0.0):
    return {"x": x, "y": y, "z": z}


def write_run(path, seed, gain=1.0):
    rng = np.random.default_rng(seed)
    with open(path, "wb") as f:
        w = Writer(f)
        schemas = {k: w.register_msgdef(k, v) for k, v in DEFS.items()}
        x = 0.0
        for t in np.arange(0.0, 20.0, 0.1):
            ns = int(round(t * 1e9))
            speed = gain * (0.2 + 0.05 * math.sin(t / 3))
            x += speed * 0.1
            w.write_message("/cmd_vel", schemas["geometry_msgs/msg/Twist"],
                            {"linear": xyz(speed + rng.normal(0, 1e-4)), "angular": xyz()},
                            log_time=ns, publish_time=ns)
            header = {"stamp": {"sec": int(t), "nanosec": int(round((t % 1) * 1e9))}, "frame_id": "odom"}
            w.write_message("/odom", schemas["nav_msgs/msg/Odometry"], {
                "header": header,
                "pose": {"pose": {"position": xyz(x + rng.normal(0, 1e-4)),
                                  "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}}}},
                log_time=ns, publish_time=ns)
        w.finish()


def main(out="examples/recordings"):
    out = pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for i in range(3):
        write_run(out / f"base{i}.mcap", seed=i)
    write_run(out / "head.mcap", seed=7, gain=1.2)
    print(f"wrote base0.mcap base1.mcap base2.mcap head.mcap to {out}")


if __name__ == "__main__":
    main(*sys.argv[1:2])
