#!/usr/bin/env bash
# One repetition of the whole experiment for one distro and playback rate: 6 base replays (base0..base5) and one
# replay per injected regression, all on the same code, same recording, same rate. The N=3 and N=5 noise floors
# are both taken from these base runs. A failed replay is logged and skipped, so one flake can't hide the rest.
# Usage: run_experiment.sh <distro> <recording_dir> <rate> <runs_dir> <rep>
set -uo pipefail
distro="${1:?}"; rec="${2:?}"; rate="${3:?}"; runs="${4:?}"; rep="${5:?}"
here="$(cd "$(dirname "$0")" && pwd)"
d="$runs/rep$rep"
mkdir -p "$d"
start=$(date +%s)
declare -A overlays=(
  [gain10]="-p velocity_gain:=1.1"
  [gain30]="-p velocity_gain:=1.3"
  [offset2cm]="-p odom_offset_x:=0.02"
  [drop_odom]="-p publish_odom:=false"
)
run() {  # name, overlay args...
  local name="$1"; shift
  "$here/replay_once.sh" "$distro" "$rec" "$d/$name" "$rate" "$@" || echo "REPLAY FAILED: $name (see $d/$name.*.log)"
}
for i in 0 1 2 3 4 5; do run "base$i"; done
for name in gain10 gain30 offset2cm drop_odom; do
  # shellcheck disable=SC2086
  run "$name" ${overlays[$name]}
done
echo $(( $(date +%s) - start )) > "$runs/wall_seconds.txt"
echo "repetition $rep took $(( $(date +%s) - start )) s"
