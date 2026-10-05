"""Synthetic in-memory runs for the unit tests (no ROS, no files)."""
from types import SimpleNamespace as NS

import numpy as np

from compare_proto import make_series


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
