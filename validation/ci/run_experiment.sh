#!/usr/bin/env bash
# One repetition of the whole experiment for one distro and playback rate: 6 base replays (base0..base5) and one
# replay per injected regression of the chosen set, all on the same code, same recording, same rate. The N=3 and
# N=5 noise floors are both taken from these base runs. A failed replay is logged and skipped, so one flake can't
# hide the rest. Sets: "controls" (far past the tolerances) and "near" (0.5x-1.5x of the tolerances; each set runs
# its own base replays in its own job, so no job gets longer).
# Usage: run_experiment.sh <distro> <recording_dir> <rate> <runs_dir> <rep> [controls|near]
set -uo pipefail
distro="${1:?}"; rec="${2:?}"; rate="${3:?}"; runs="${4:?}"; rep="${5:?}"; set_name="${6:-controls}"
here="$(cd "$(dirname "$0")" && pwd)"
d="$runs/rep$rep"
mkdir -p "$d"
start=$(date +%s)
declare -A overlays=(
  [gain10]="-p velocity_gain:=1.1"
  [gain30]="-p velocity_gain:=1.3"
  [offset2cm]="-p odom_offset_x:=0.02"
  [drop_odom]="-p publish_odom:=false"
  # near the tolerances: linear.x tolerance 0.01 m/s is 5% of the 0.2 m/s cruise, translation tolerance 0.01 m
  [gain_x0.5]="-p velocity_gain:=1.025"
  [gain_x0.75]="-p velocity_gain:=1.0375"
  [gain_x1.0]="-p velocity_gain:=1.05"
  [gain_x1.5]="-p velocity_gain:=1.075"
  [offset_x0.5]="-p odom_offset_x:=0.005"
  [offset_x0.75]="-p odom_offset_x:=0.0075"
  [offset_x1.0]="-p odom_offset_x:=0.010"
  [offset_x1.5]="-p odom_offset_x:=0.015"
)
case "$set_name" in
  controls) names=(gain10 gain30 offset2cm drop_odom) ;;
  near) names=(gain_x0.5 gain_x0.75 gain_x1.0 gain_x1.5 offset_x0.5 offset_x0.75 offset_x1.0 offset_x1.5) ;;
  *) echo "unknown set: $set_name" >&2; exit 2 ;;
esac
run() {  # name, overlay args...
  local name="$1"; shift
  "$here/replay_once.sh" "$distro" "$rec" "$d/$name" "$rate" "$@" || echo "REPLAY FAILED: $name (see $d/$name.*.log)"
}
for i in 0 1 2 3 4 5; do run "base$i"; done
for name in "${names[@]}"; do
  # shellcheck disable=SC2086
  run "$name" ${overlays[$name]}
done
echo $(( $(date +%s) - start )) > "$runs/wall_seconds.txt"
echo "repetition $rep took $(( $(date +%s) - start )) s"
