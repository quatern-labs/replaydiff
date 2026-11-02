"""Write a tiny demo for `replaydiff compare`: three base runs, a head that behaves the same, a head with a
regression on /odom only, and a tolerance file. Needs no ROS install.

usage: python examples/make_demo.py <output-dir>
"""
import sys
from pathlib import Path

import numpy as np
from mcap_ros2.writer import Writer

TOLERANCES = """\
defaults: {skip_first: 1.0, stat: p95}
rate: {rel: 0.10}
topics:
  /cmd_vel:
    fields: {linear.x: {abs: 0.01}}
  /odom:
    match: interpolate
    pose: {translation: 0.01}
"""

SEP = "=" * 80 + "\n"
VEC3 = "MSG: geometry_msgs/Vector3\nfloat64 x\nfloat64 y\nfloat64 z\n"
POINT = "MSG: geometry_msgs/Point\nfloat64 x\nfloat64 y\nfloat64 z\n"
QUAT = "MSG: geometry_msgs/Quaternion\nfloat64 x\nfloat64 y\nfloat64 z\nfloat64 w\n"
POSE = "MSG: geometry_msgs/Pose\ngeometry_msgs/Point position\ngeometry_msgs/Quaternion orientation\n"
TWIST = "MSG: geometry_msgs/Twist\ngeometry_msgs/Vector3 linear\ngeometry_msgs/Vector3 angular\n"
HEADER = "MSG: std_msgs/Header\nbuiltin_interfaces/Time stamp\nstring frame_id\n"
TIME = "MSG: builtin_interfaces/Time\nint32 sec\nuint32 nanosec\n"
TWIST_DEF = "geometry_msgs/Vector3 linear\ngeometry_msgs/Vector3 angular\n" + SEP + VEC3
ODOM_DEF = ("std_msgs/Header header\ngeometry_msgs/PoseWithCovariance pose\ngeometry_msgs/TwistWithCovariance twist\n"
            + SEP + HEADER + SEP + TIME + SEP + "MSG: geometry_msgs/PoseWithCovariance\ngeometry_msgs/Pose pose\n"
            + SEP + POSE + SEP + POINT + SEP + QUAT + SEP
            + "MSG: geometry_msgs/TwistWithCovariance\ngeometry_msgs/Twist twist\n" + SEP + TWIST + SEP + VEC3)


def xyz(x=0.0, y=0.0, z=0.0):
    return {"x": x, "y": y, "z": z}


def write_run(path, seed, odom_offset=0.0):
    """One replay run: /cmd_vel and /odom at 5 Hz for 20 s. The seed gives each run its own tiny noise."""
    rng = np.random.default_rng(seed)
    with open(path, "wb") as f:
        w = Writer(f)
        twist = w.register_msgdef("geometry_msgs/msg/Twist", TWIST_DEF)
        odom = w.register_msgdef("nav_msgs/msg/Odometry", ODOM_DEF)
        for t in np.arange(1.0, 21.0, 0.2):
            ns = int(t * 1e9)
            w.write_message("/cmd_vel", twist, {"linear": xyz(0.2 + rng.normal(0, 1e-4)), "angular": xyz()},
                            log_time=ns, publish_time=ns)
            stamp = {"sec": int(t), "nanosec": int(round((t % 1) * 1e9))}
            pose = {"position": xyz(0.2 * t + odom_offset + rng.normal(0, 1e-4)),
                    "orientation": {"x": 0, "y": 0, "z": 0, "w": 1}}
            w.write_message("/odom", odom, {
                "header": {"stamp": stamp, "frame_id": "odom"}, "pose": {"pose": pose},
                "twist": {"twist": {"linear": xyz(0.2), "angular": xyz()}}}, log_time=ns, publish_time=ns)
        w.finish()


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    out = Path(argv[0])
    out.mkdir(parents=True, exist_ok=True)
    for i in range(3):
        write_run(out / f"base{i}.mcap", seed=i)
    write_run(out / "head_same.mcap", seed=10)
    write_run(out / "head_regressed.mcap", seed=10, odom_offset=0.05)  # /odom 5 cm off, /cmd_vel unchanged
    (out / "tolerances.yaml").write_text(TOLERANCES)
    print(f"wrote 5 MCAPs and tolerances.yaml to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
