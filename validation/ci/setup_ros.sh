#!/usr/bin/env bash
# Install what the experiment needs on top of ros-base (ROS 2 already installed by ros-tooling/setup-ros).
# Usage: setup_ros.sh <distro> [sim]   ("sim" also installs TurtleBot3 + nav2 + Gazebo for recording generation)
set -euo pipefail
distro="${1:?distro}"
sudo apt-get update
pkgs=(
  "ros-${distro}-rosbag2" "ros-${distro}-rosbag2-storage-mcap" "ros-${distro}-nav-msgs" "ros-${distro}-geometry-msgs"
  python3-numpy python3-yaml python3-pip
)
if [ "${2:-}" = "sim" ]; then
  pkgs+=("ros-${distro}-nav2-bringup" xvfb)
  if [ "$distro" = humble ]; then
    pkgs+=("ros-${distro}-turtlebot3-gazebo" "ros-${distro}-gazebo-ros-pkgs")
    # The ubuntu-22.04 runner image ships libunwind-14-dev, which conflicts with the libunwind-dev that
    # libgoogle-glog-dev (a gazebo dependency) needs; remove it so apt can resolve.
    sudo apt-get remove -y libunwind-14-dev || true
  else
    pkgs+=("ros-${distro}-nav2-minimal-tb3-sim" "ros-${distro}-ros-gz")
  fi
fi
sudo apt-get install -y --no-install-recommends "${pkgs[@]}"
# analysis dependencies (Apache-2.0 / MIT / BSD): mcap, mcap-ros2-support, numpy, PyYAML
python3 -m pip install --user --break-system-packages mcap mcap-ros2-support 2>/dev/null \
  || python3 -m pip install --user mcap mcap-ros2-support
