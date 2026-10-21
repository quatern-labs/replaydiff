#!/usr/bin/env bash
# One nav2 replay: nav2's controller_server (default Humble DWB), planner_server and map_server on the replayed
# recording (/scan /odom /tf /clock from the bag, use_sim_time on every node), the recorded goals sent from a launch
# event handler, nav2's /cmd_vel (remapped to /sut/cmd_vel) recorded. Regressions are overlays on nav2's own params.
# Usage: nav2_replay_once.sh <distro> <recording_dir> <map.yaml> <goals.yaml> <out_dir> <rate> [overlay name from nav2/overlays.yaml]
set -euo pipefail
distro="${1:?}"; rec="${2:?}"; map="${3:?}"; goals="${4:?}"; out="${5:?}"; rate="${6:?}"; overlay="${7:-}"
here="$(cd "$(dirname "$0")" && pwd)"
v="$here/.."
set +u
source "/opt/ros/${distro}/setup.bash"
set -u
rm -rf "$out"
mkdir -p "$(dirname "$out")"
params="$out.params.yaml"
python3 "$v/nav2_tools.py" overlay --params "$v/nav2/params.yaml" --overlays "$v/nav2/overlays.yaml" --name "$overlay" --out "$params"
pids=()
cleanup() { for p in "${pids[@]:-}"; do kill -TERM "$p" 2>/dev/null || true; done; }
trap cleanup EXIT
ros2 bag record -s mcap --use-sim-time -o "$out" /sut/cmd_vel /local_plan > "$out.record.log" 2>&1 &
recpid=$!; pids+=("$recpid")
sleep 4
# returns when the goal sender (started by the bag play's launch event) has finished; the launch is then stopped
ros2 launch "$here/nav2_replay.launch.py" params:="$params" map:="$map" recording:="$rec" rate:="$rate" goals:="$goals" \
  > "$out.launch.log" 2>&1 &
launch=$!; pids+=("$launch")
while kill -0 "$launch" 2>/dev/null && ! grep -q "sent .* goals" "$out.launch.log" 2>/dev/null; do sleep 2; done
sleep 3
kill -INT "$launch" 2>/dev/null || true
kill -INT "$recpid" 2>/dev/null || true
wait "$recpid" 2>/dev/null || true
ls "$out"/*.mcap >/dev/null
