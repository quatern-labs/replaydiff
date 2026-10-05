#!/usr/bin/env bash
# Generate the public input recording headlessly: TurtleBot3 (waffle) + nav2 in simulation, two fixed goals
# (20 s each, about 40 s of data, to keep replay time small); records /odom /scan /tf /tf_static /cmd_vel /plan
# with sim time as the log time.
# Usage: gen_recording.sh <distro> <out_dir>      (writes <out_dir>/recording/*.mcap)
set -euo pipefail
distro="${1:?distro}"
out="${2:?out_dir}"
here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1090
source "/opt/ros/${distro}/setup.bash"
export TURTLEBOT3_MODEL=waffle
export LIBGL_ALWAYS_SOFTWARE=1
mkdir -p "$out"
rm -rf "$out/recording"
pids=()
cleanup() {
  for p in "${pids[@]:-}"; do kill -INT "$p" 2>/dev/null || true; done
  sleep 3
  for p in "${pids[@]:-}"; do kill -TERM "$p" 2>/dev/null || true; done
}
trap cleanup EXIT

xvfb-run -a -s "-screen 0 1280x1024x24" \
  ros2 launch nav2_bringup tb3_simulation_launch.py headless:=True use_rviz:=False > "$out/sim.log" 2>&1 &
pids+=($!)

echo "waiting for nav2 (up to 240 s)"
for _ in $(seq 1 120); do
  if ros2 topic list 2>/dev/null | grep -q '^/odom$' && ros2 action list 2>/dev/null | grep -q navigate_to_pose; then break; fi
  sleep 2
done
sleep 20

ros2 bag record -s mcap --use-sim-time -o "$out/recording" /odom /scan /tf /tf_static /cmd_vel /plan > "$out/record.log" 2>&1 &
rec=$!
pids+=("$rec")
sleep 3

# initial pose, then a fixed goal sequence (positions in the standard nav2 TurtleBot3 world, map frame)
ros2 topic pub --once /initialpose geometry_msgs/msg/PoseWithCovarianceStamped \
  "{header: {frame_id: map}, pose: {pose: {position: {x: -2.0, y: -0.5, z: 0.0}, orientation: {w: 1.0}}}}" >/dev/null
sleep 5
goals=("-1.0 -0.5" "0.0 0.5")
for g in "${goals[@]}"; do
  set -- $g
  timeout 20 ros2 action send_goal /navigate_to_pose nav2_msgs/action/NavigateToPose \
    "{pose: {header: {frame_id: map}, pose: {position: {x: $1, y: $2, z: 0.0}, orientation: {w: 1.0}}}}" \
    >> "$out/goals.log" 2>&1 || echo "goal $g did not finish in 20 s (recording continues)" >> "$out/goals.log"
done
sleep 2
kill -INT "$rec" 2>/dev/null || true
wait "$rec" 2>/dev/null || true
ls -la "$out/recording"
python3 "$here/recording_info.py" "$out/recording"
