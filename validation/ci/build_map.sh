#!/usr/bin/env bash
# Build a map offline from a recording's derived /scan and odometry/TF with SLAM Toolbox (LGPL-2.1, CI-time tool from
# the ROS apt repo, its own process; see setup_ros.sh slam). Mapping mode, parameters in validation/nav2/slam_params.yaml
# (resolution 0.05 m, max range 12 m, scan every 0.2 m / 0.2 rad of travel, loop closing, Ceres). Then nav2's map_saver.
# The map is derived data: cached in CI under the key `nav2_tools.py cache-key` prints (recording + SLAM params hash),
# never committed. Exits 3 when the map is not usable (window too short or featureless: see nav2_tools.map_usable).
# Usage: build_map.sh <distro> <recording_dir> <out_dir> [rate]      (writes <out_dir>/map.yaml and map.pgm)
set -euo pipefail
distro="${1:?distro}"; rec="${2:?recording}"; out="${3:?out}"; rate="${4:-1.0}"
here="$(cd "$(dirname "$0")" && pwd)"
v="$here/.."
set +u
source "/opt/ros/${distro}/setup.bash"
set -u
mkdir -p "$out"
pids=()
cleanup() { for p in "${pids[@]:-}"; do kill -TERM "$p" 2>/dev/null || true; done; }
trap cleanup EXIT
echo "cache key: $(python3 "$v/nav2_tools.py" cache-key "$rec" "$v/nav2/slam_params.yaml")"

ros2 run slam_toolbox async_slam_toolbox_node --ros-args --params-file "$v/nav2/slam_params.yaml" \
  -p use_sim_time:=true > "$out/slam.log" 2>&1 &
pids+=($!)
sleep 5
# inputs only; the recording's own map->odom (localisation) is not replayed, SLAM Toolbox publishes its own
ros2 bag play "$rec" --clock 1000 -r "$rate" --topics /odom /scan /tf /tf_static --remap /tf:=/tf_in /tf_static:=/tf_static_in > "$out/play.log" 2>&1 &
play=$!
# slam_toolbox needs odom->base_link on /tf: relay the bag's /tf without map->odom
python3 "$here/nav2_replay_nodes.py" tf --drop-children odom --no-map-odom --ros-args -p use_sim_time:=true > "$out/tf.log" 2>&1 &
pids+=($!)
wait "$play"
sleep 3
ros2 run nav2_map_server map_saver_cli -f "$out/map" --ros-args -p use_sim_time:=true > "$out/saver.log" 2>&1
python3 "$v/nav2_tools.py" check-map "$out/map.pgm"
