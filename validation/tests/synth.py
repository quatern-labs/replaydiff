"""Synthetic in-memory runs for the unit tests (no ROS, no files)."""
from types import SimpleNamespace as NS

import numpy as np

from replaydiff.compare import make_series


def vec(x=0.0, y=0.0, z=0.0):
    return NS(x=x, y=y, z=z)


def twist(vx, wz):
    return NS(linear=vec(vx), angular=vec(0, 0, wz))


def stamp(t):
    sec = int(t)
    return NS(sec=sec, nanosec=int(round((t - sec) * 1e9)))


def odom(t, x, vx=0.0):
    return NS(header=NS(stamp=stamp(t)),
              pose=NS(pose=NS(position=vec(x, 0, 0), orientation=NS(x=0.0, y=0.0, z=0.0, w=1.0))),
              twist=NS(twist=twist(vx, 0.0)))


def cmd_series(times, vx_fn, jitter=None, rng=None):
    """Twist stream; `jitter` perturbs the value, receive times are exact."""
    vals = [vx_fn(t) + (rng.normal(0, jitter) if jitter else 0.0) for t in times]
    return make_series((t, twist(v, 0.1)) for t, v in zip(times, vals))


def odom_series(times, speed=0.2, offset=0.0, jitter=None, rng=None):
    return make_series(
        (t, odom(t + 1.0, speed * t + offset + (rng.normal(0, jitter) if jitter else 0.0), speed))
        for t in times)


def run(cmd=None, odm=None):
    r = {}
    if cmd is not None:
        r["/cmd_vel"] = cmd
    if odm is not None:
        r["/odom"] = odm
    return r


TIMES = np.arange(1.0, 41.0, 0.05)  # 20 Hz, 40 s

CONFIG = {
    "defaults": {"skip_first": 1.0, "stat": "p95"},
    "rate": {"rel": 0.10},
    "topics": {
        "/cmd_vel": {
            "fields": {"linear.x": {"abs": 0.01}, "angular.z": {"abs": 0.03}},
            "bias": {"window": 2.0, "abs": 0.005},
        },
        "/odom": {
            "match": "interpolate",
            "pose": {"translation": 0.01, "rotation_deg": 1.0},
            "twist": {"linear": 0.02, "angular": 0.03},
        },
    },
}


# --- MCAP fixture for the CLI tests (a few KB; reduced message definitions: no covariances, no frame ids) ---
_SEP = "=" * 80 + "\n"
_V3 = "MSG: geometry_msgs/Vector3\nfloat64 x\nfloat64 y\nfloat64 z\n"
_Q = "MSG: geometry_msgs/Quaternion\nfloat64 x\nfloat64 y\nfloat64 z\nfloat64 w\n"
_P = "MSG: geometry_msgs/Point\nfloat64 x\nfloat64 y\nfloat64 z\n"
_POSE = "MSG: geometry_msgs/Pose\ngeometry_msgs/Point position\ngeometry_msgs/Quaternion orientation\n"
_TW = "MSG: geometry_msgs/Twist\ngeometry_msgs/Vector3 linear\ngeometry_msgs/Vector3 angular\n"
_HDR = "MSG: std_msgs/Header\nbuiltin_interfaces/Time stamp\nstring frame_id\n"
_TIME = "MSG: builtin_interfaces/Time\nint32 sec\nuint32 nanosec\n"
DEFS = {
    "geometry_msgs/msg/Twist": ("geometry_msgs/Vector3 linear\ngeometry_msgs/Vector3 angular\n" + _SEP + _V3),
    "nav_msgs/msg/Odometry": ("std_msgs/Header header\ngeometry_msgs/PoseWithCovariance pose\n"
                              "geometry_msgs/TwistWithCovariance twist\n" + _SEP + _HDR + _SEP + _TIME + _SEP
                              + "MSG: geometry_msgs/PoseWithCovariance\ngeometry_msgs/Pose pose\n" + _SEP + _POSE
                              + _SEP + _P + _SEP + _Q + _SEP
                              + "MSG: geometry_msgs/TwistWithCovariance\ngeometry_msgs/Twist twist\n" + _SEP + _TW
                              + _SEP + _V3),
    "nav_msgs/msg/Path": ("std_msgs/Header header\ngeometry_msgs/PoseStamped[] poses\n" + _SEP + _HDR + _SEP + _TIME
                          + _SEP + "MSG: geometry_msgs/PoseStamped\nstd_msgs/Header header\ngeometry_msgs/Pose pose\n"
                          + _SEP + _POSE + _SEP + _P + _SEP + _Q),
    "sensor_msgs/msg/JointState": ("std_msgs/Header header\nstring[] name\nfloat64[] position\nfloat64[] velocity\n"
                                   "float64[] effort\n" + _SEP + _HDR + _SEP + _TIME),
}


def _xyz(x=0.0, y=0.0, z=0.0):
    return {"x": x, "y": y, "z": z}


def write_mcap(path, *, gain=1.0, offset=0.0, path_shift=0.0, seed=0, jitter=1e-4, times=TIMES[:400:4],
               joint_offset=0.0, joint_reverse=False, joints=("shoulder", "elbow", "gripper")):
    """Write /cmd_vel (Twist), /odom (Odometry), /plan (Path) and /joint_states to an MCAP. One call = one replay run: the
    seed gives each base run its own small noise; `gain`, `offset` and `path_shift` inject regressions."""
    import math
    from mcap_ros2.writer import Writer
    rng = np.random.default_rng(seed)
    with open(path, "wb") as f:
        w = Writer(f)
        sch = {k: w.register_msgdef(k, v) for k, v in DEFS.items()}
        for t in times:
            ns = int(t * 1e9)
            vx = gain * (0.2 + 0.05 * math.sin(t / 3)) + rng.normal(0, jitter)
            w.write_message("/cmd_vel", sch["geometry_msgs/msg/Twist"],
                            {"linear": _xyz(vx), "angular": _xyz(0, 0, 0.1)}, log_time=ns, publish_time=ns)
            x = 0.2 * t + offset + rng.normal(0, jitter)
            hdr = {"stamp": {"sec": int(t + 1), "nanosec": int(round((t % 1) * 1e9))}, "frame_id": "odom"}
            w.write_message("/odom", sch["nav_msgs/msg/Odometry"], {
                "header": hdr, "pose": {"pose": {"position": _xyz(x), "orientation": {"x": 0, "y": 0, "z": 0, "w": 1}}},
                "twist": {"twist": {"linear": _xyz(0.2), "angular": _xyz()}}}, log_time=ns, publish_time=ns)
            poses = [{"header": hdr, "pose": {"position": _xyz(0.5 * k, path_shift), "orientation": {
                "x": 0, "y": 0, "z": 0, "w": 1}}} for k in range(5)]
            names = list(joints)[::-1] if joint_reverse else list(joints)
            pos = {"shoulder": 0.5 * math.sin(t / 4), "elbow": 0.1 * t + joint_offset, "gripper": 0.02}
            w.write_message("/joint_states", sch["sensor_msgs/msg/JointState"], {
                "header": hdr, "name": names,
                "position": [pos[n] + rng.normal(0, jitter) for n in names],
                "velocity": [0.1 * rng.normal(0, 1) for _ in names], "effort": [5.0 * rng.normal(0, 1) for _ in names]},
                log_time=ns, publish_time=ns)
            w.write_message("/plan", sch["nav_msgs/msg/Path"], {"header": hdr, "poses": poses},
                            log_time=ns, publish_time=ns)
        w.finish()


CLI_TOLERANCES = """
defaults: {skip_first: 1.0, stat: p95}
rate: {rel: 0.10}
topics:
  /cmd_vel:
    fields: {linear.x: {abs: 0.01}}
    bias: {window: 2.0, abs: 0.005}
  /odom:
    match: interpolate
    pose: {translation: 0.01}
  /plan:
    match: sequence
    path: {mean_dist: 0.05, hausdorff: 0.20, endpoint: 0.05, resample: 0.05}
"""

JOINT_TOLERANCES = """
defaults: {skip_first: 1.0, stat: p95}
topics:
  /joint_states:
    match: interpolate
    joints: {"*": {position: 0.01, velocity: 1.0}, gripper: {position: 0.002}}
    ignore_fields: [effort]
"""
