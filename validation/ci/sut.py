#!/usr/bin/env python3
"""System under test for the replaydiff validation experiment (CI only, needs ROS 2).

A small pure-pursuit controller fed by recorded /odom and /plan, publishing /sut/cmd_vel (Twist) and /sut/odom
(the input odometry passed through a frame correction). It is deliberately not the nav2 controller: nav2's
controller needs live costmaps, TF and action goals, which a bag replay does not provide. The experiment only
needs a node that turns recorded inputs into /cmd_vel and odometry outputs and has parameters to inject
regressions. Regressions are parameter overlays on this same code:
  velocity_gain    1.0 -> 1.1 / 1.3   (gain regression)
  lookahead        lookahead distance, m
  odom_offset_x    0.0 -> 0.02        (2 cm offset)
  publish_odom     true -> false      (dropped topic)
"""
import math

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry, Path
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy


def yaw_of(q):
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))


class Sut(Node):
    def __init__(self):
        super().__init__("sut")
        self.gain = self.declare_parameter("velocity_gain", 1.0).value
        self.lookahead = self.declare_parameter("lookahead", 0.6).value
        self.offset_x = self.declare_parameter("odom_offset_x", 0.0).value
        self.publish_odom = self.declare_parameter("publish_odom", True).value
        self.v_cruise = self.declare_parameter("cruise_speed", 0.2).value
        self.path = []
        qos = QoSProfile(depth=50, reliability=ReliabilityPolicy.RELIABLE)
        self.cmd_pub = self.create_publisher(Twist, "/sut/cmd_vel", qos)
        self.odom_pub = self.create_publisher(Odometry, "/sut/odom", qos) if self.publish_odom else None
        self.create_subscription(Path, "/plan", self.on_plan, qos)
        self.create_subscription(Odometry, "/odom", self.on_odom, qos)

    def on_plan(self, msg):
        self.path = [(p.pose.position.x, p.pose.position.y) for p in msg.poses]

    def on_odom(self, msg):
        if self.odom_pub is not None:
            out = Odometry()
            out.header = msg.header
            out.child_frame_id = msg.child_frame_id
            out.pose = msg.pose
            out.twist = msg.twist
            out.pose.pose.position.x += self.offset_x
            self.odom_pub.publish(out)
        self.cmd_pub.publish(self.command(msg))

    def command(self, odom):
        cmd = Twist()
        if len(self.path) < 2:
            return cmd
        px, py = odom.pose.pose.position.x, odom.pose.pose.position.y
        yaw = yaw_of(odom.pose.pose.orientation)
        gx, gy = self.path[-1]
        dist_goal = math.hypot(gx - px, gy - py)
        if dist_goal < 0.1:
            return cmd
        nearest = min(range(len(self.path)), key=lambda i: math.hypot(self.path[i][0] - px, self.path[i][1] - py))
        target = self.path[-1]
        for x, y in self.path[nearest:]:
            if math.hypot(x - px, y - py) >= self.lookahead:
                target = (x, y)
                break
        alpha = math.atan2(target[1] - py, target[0] - px) - yaw
        alpha = math.atan2(math.sin(alpha), math.cos(alpha))
        v = self.gain * self.v_cruise * min(1.0, dist_goal / 0.5) * max(0.0, math.cos(alpha))
        cmd.linear.x = v
        cmd.angular.z = max(-1.0, min(1.0, 2.0 * self.v_cruise * math.sin(alpha) / max(self.lookahead, 0.05)))
        return cmd


def main():
    rclpy.init()
    node = Sut()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
