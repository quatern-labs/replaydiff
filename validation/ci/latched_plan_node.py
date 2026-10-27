#!/usr/bin/env python3
"""Latched Path publisher (CI only, needs ROS 2): republishes the replayed /plan_in as a transient-local /plan, so a
subscriber that joins after the bag played the plan still gets the newest one. Usage:
  latched_plan_node.py [--in /plan_in] [--out /plan]  (play the bag with --remap /plan:=/plan_in)"""
import argparse
import os
import sys

import rclpy
from nav_msgs.msg import Path
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from latched_plan import PlanLatch  # noqa: E402


class LatchedPlan(Node):
    def __init__(self, src, dst):
        super().__init__("latched_plan")
        self.latch = PlanLatch()
        latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL, reliability=ReliabilityPolicy.RELIABLE)
        self.pub = self.create_publisher(Path, dst, latched)
        self.create_subscription(Path, src, self.on_plan, QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE))

    def on_plan(self, msg):
        if self.latch.update(msg):
            self.pub.publish(msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", default="/plan_in")
    ap.add_argument("--out", dest="dst", default="/plan")
    args, ros_args = ap.parse_known_args()
    rclpy.init(args=ros_args)
    node = LatchedPlan(args.src, args.dst)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
