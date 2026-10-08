#!/usr/bin/env python3
"""Two small ROS 2 nodes for the nav2 replay loop (CI only, needs ROS 2).

  tf     republishes the bag's /tf_in as /tf without the frames in --drop-children (regenerated live or by the
         localisation), and /tf_static_in as a latched /tf_static, plus a static identity map->odom (the map is
         built in the odometry frame, so the two coincide at the start of the window).
  goals  waits for /clock to reach each goal's offset (sim time, no timers), then calls nav2's ComputePathToPose and
         FollowPath for it; goals come from <recording>/../goals.yaml: [{t, x, y, yaw}], map frame.
"""
import argparse
import math
import sys
import time

import rclpy
import yaml
from geometry_msgs.msg import TransformStamped
from nav2_msgs.action import ComputePathToPose, FollowPath
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from tf2_msgs.msg import TFMessage

from nav2_tools import keep_transform


class TfRelay(Node):
    def __init__(self, drop):
        super().__init__("tf_relay", parameter_overrides=[])
        self.drop = drop
        self.static = {}
        latched = QoSProfile(depth=100, durability=DurabilityPolicy.TRANSIENT_LOCAL, reliability=ReliabilityPolicy.RELIABLE)
        self.tf_pub = self.create_publisher(TFMessage, "/tf", 100)
        self.static_pub = self.create_publisher(TFMessage, "/tf_static", latched)
        self.create_subscription(TFMessage, "/tf_in", self.on_tf, 100)
        self.create_subscription(TFMessage, "/tf_static_in", self.on_static, latched)
        ident = TransformStamped()
        ident.header.frame_id, ident.child_frame_id = "map", "odom"
        ident.transform.rotation.w = 1.0
        self.static[("map", "odom")] = ident
        self.static_pub.publish(TFMessage(transforms=list(self.static.values())))

    def on_tf(self, msg):
        kept = [t for t in msg.transforms if keep_transform(t.header.frame_id, t.child_frame_id, self.drop)]
        if kept:
            self.tf_pub.publish(TFMessage(transforms=kept))

    def on_static(self, msg):
        for t in msg.transforms:
            if keep_transform(t.header.frame_id, t.child_frame_id, self.drop):
                self.static[(t.header.frame_id, t.child_frame_id)] = t
        self.static_pub.publish(TFMessage(transforms=list(self.static.values())))


def run_goals(node, goals):
    plan_client = ActionClient(node, ComputePathToPose, "compute_path_to_pose")
    follow_client = ActionClient(node, FollowPath, "follow_path")
    for c in (plan_client, follow_client):
        if not c.wait_for_server(timeout_sec=120):
            node.get_logger().error("nav2 action server did not come up")
            return 1
    ok = 0
    for g in goals:
        while node.get_clock().now().nanoseconds / 1e9 < g["t"]:  # /clock from the bag
            rclpy.spin_once(node, timeout_sec=0.1)
        pose = plan_client_goal = ComputePathToPose.Goal()
        pose.goal.header.frame_id = "map"
        pose.goal.pose.position.x, pose.goal.pose.position.y = float(g["x"]), float(g["y"])
        pose.goal.pose.orientation.z = math.sin(g.get("yaw", 0.0) / 2)
        pose.goal.pose.orientation.w = math.cos(g.get("yaw", 0.0) / 2)
        pose.use_start = False
        fut = plan_client.send_goal_async(plan_client_goal)
        rclpy.spin_until_future_complete(node, fut)
        res = fut.result().get_result_async()
        rclpy.spin_until_future_complete(node, res)
        path = res.result().result.path
        if not path.poses:
            node.get_logger().error(f"no plan to goal {g}")
            continue
        follow = FollowPath.Goal()
        follow.path, follow.controller_id, follow.goal_checker_id = path, "FollowPath", "general_goal_checker"
        fut = follow_client.send_goal_async(follow)
        rclpy.spin_until_future_complete(node, fut)
        done = fut.result().get_result_async()
        rclpy.spin_until_future_complete(node, done, timeout_sec=60)
        ok += 1
    node.get_logger().info(f"sent {ok} of {len(goals)} goals")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["tf", "goals"])
    ap.add_argument("--drop-children", default="odom,wheel_left_link,wheel_right_link")
    ap.add_argument("--goals", default="")
    a, ros_args = ap.parse_known_args()
    rclpy.init(args=ros_args)
    code = 0
    if a.mode == "tf":
        node = TfRelay(set(a.drop_children.split(",")))
        rclpy.spin(node)
    else:
        node = Node("goal_sender")
        code = run_goals(node, yaml.safe_load(open(a.goals)))
    node.destroy_node()
    rclpy.try_shutdown()
    return code


if __name__ == "__main__":
    sys.exit(main())
