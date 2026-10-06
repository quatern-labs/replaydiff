#!/usr/bin/env bash
# Install what the experiment needs on top of the official ros:<distro> Docker image (ROS 2 ros-base preinstalled,
# running as root, so no sudo; a plain runner with sudo also works).
# Usage: setup_ros.sh <distro> [sim]   ("sim" also installs TurtleBot3 + nav2 + Gazebo for recording generation)
set -euo pipefail
distro="${1:?distro}"
SUDO=""
if [ "$(id -u)" -ne 0 ]; then SUDO="sudo"; fi
export DEBIAN_FRONTEND=noninteractive
$SUDO apt-get update
pkgs=(
  "ros-${distro}-rosbag2" "ros-${distro}-rosbag2-storage-mcap" "ros-${distro}-nav-msgs" "ros-${distro}-geometry-msgs"
  python3-numpy python3-yaml python3-pip
)
if [ "${2:-}" = "sim" ]; then
  pkgs+=("ros-${distro}-nav2-bringup" xvfb)
  if [ "$distro" = humble ]; then
    pkgs+=("ros-${distro}-turtlebot3-gazebo" "ros-${distro}-gazebo-ros-pkgs")
    # A host runner image ships libunwind-14-dev, which conflicts with the libunwind-dev that libgoogle-glog-dev
    # (a gazebo dependency) needs. The ros:humble container has none, so this is a no-op there; kept for plain runners.
    $SUDO apt-get purge -y 'libunwind-[0-9]*-dev' || true
  else
    pkgs+=("ros-${distro}-nav2-minimal-tb3-sim" "ros-${distro}-ros-gz")
  fi
fi
$SUDO apt-get install -y --no-install-recommends "${pkgs[@]}"
# analysis dependencies (Apache-2.0 / MIT / BSD): mcap, mcap-ros2-support, numpy, PyYAML
python3 -m pip install --user --break-system-packages mcap mcap-ros2-support 2>/dev/null \
  || python3 -m pip install --user mcap mcap-ros2-support
