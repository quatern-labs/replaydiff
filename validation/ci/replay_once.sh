#!/usr/bin/env bash
# One replay: play the recorded inputs at <rate> with /clock, run the system under test with use_sim_time and the
# given parameter overlay, record its outputs (/sut/cmd_vel, /sut/odom) with sim time as the log time.
# Usage: replay_once.sh <distro> <recording_dir> <out_dir> <rate> [ros param overlay, e.g. -p velocity_gain:=1.1]
set -euo pipefail
distro="${1:?distro}"; rec="${2:?recording}"; out="${3:?out}"; rate="${4:?rate}"; shift 4
here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1090
source "/opt/ros/${distro}/setup.bash"
rm -rf "$out"
mkdir -p "$(dirname "$out")"
pids=()
cleanup() { for p in "${pids[@]:-}"; do kill -TERM "$p" 2>/dev/null || true; done; }
trap cleanup EXIT

ros2 bag record -s mcap --use-sim-time -o "$out" /sut/cmd_vel /sut/odom > "$out.record.log" 2>&1 &
recpid=$!; pids+=("$recpid")
python3 "$here/sut.py" --ros-args -p use_sim_time:=true "$@" > "$out.sut.log" 2>&1 &
sutpid=$!; pids+=("$sutpid")
sleep 4   # discovery: recorder and SUT subscribed before the first message
# bag path first: --topics takes several values. Only the recorded inputs are replayed, never the original /cmd_vel.
ros2 bag play "$rec" --clock 1000 -r "$rate" --topics /odom /scan /tf /tf_static /plan > "$out.play.log" 2>&1
sleep 2
kill -INT "$recpid" 2>/dev/null || true
wait "$recpid" 2>/dev/null || true
kill -TERM "$sutpid" 2>/dev/null || true
wait "$sutpid" 2>/dev/null || true
pids=()
ls "$out"/*.mcap >/dev/null
