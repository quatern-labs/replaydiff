#!/usr/bin/env bash
# Bounded wait for nav2 in the headless simulation (topic /odom and action navigate_to_pose).
# Usage: wait_nav2.sh <sim_pid> <sim_log> <distro>      exit 0: up; exit 1: not up (ERROR line + tail of sim_log)
#
# The bound holds whatever a child does:
#  - every ros2 CLI call runs under `timeout -k 5 15` (SIGKILL after the grace; a bare `timeout` sends SIGTERM once
#    and waits, and a ros2 process that survives SIGTERM then blocks forever) and writes to a file, not a pipe;
#  - the probe loop runs in its own process group, and this script only sleeps and polls it, so a stuck iteration
#    cannot delay the deadline: at the deadline the group is SIGKILLed.
# NAV2_WAIT_S (default 240) and NAV2_HEARTBEAT_S (default 30) are overridable for tests only.
set -uo pipefail
sim_pid="${1:?sim_pid}"
sim_log="${2:?sim_log}"
distro="${3:?distro}"
limit="${NAV2_WAIT_S:-240}"
hb="${NAV2_HEARTBEAT_S:-30}"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/wait_nav2.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
echo "starting" > "$tmp/pending"

probe_loop() {
  while :; do
    echo "topic /odom" > "$tmp/pending"
    timeout -k 5 15 ros2 topic list > "$tmp/topics" 2>/dev/null || true
    if grep -q '^/odom$' "$tmp/topics"; then
      echo "action navigate_to_pose" > "$tmp/pending"
      timeout -k 5 15 ros2 action list > "$tmp/actions" 2>/dev/null || true
      if grep -q navigate_to_pose "$tmp/actions"; then exit 0; fi
    fi
    if ! kill -0 "$sim_pid" 2>/dev/null; then echo "simulation process exited early" >&2; exit 2; fi
    sleep 2
  done
}

echo "waiting for nav2 (up to ${limit} s)"
set -m
probe_loop &
loop=$!
set +m
start=$SECONDS
last=$start
reason=""
while kill -0 "$loop" 2>/dev/null; do
  now=$SECONDS
  if [ $((now - start)) -ge "$limit" ]; then
    kill -KILL -- "-$loop" 2>/dev/null || true
    kill -KILL "$loop" 2>/dev/null || true
    reason="deadline"
    break
  fi
  if [ $((now - last)) -ge "$hb" ]; then
    echo "still waiting for nav2: $((now - start)) s elapsed, pending: $(cat "$tmp/pending")"
    last=$now
  fi
  sleep 1
done
rc=0
wait "$loop" 2>/dev/null || rc=$?
[ -z "$reason" ] && [ "$rc" -eq 0 ] && exit 0
echo "ERROR: nav2 did not come up within ${limit} s (waited for topic /odom and action navigate_to_pose, distro ${distro}; pending: $(cat "$tmp/pending"))." >&2
echo "--- last 60 lines of ${sim_log} ---" >&2
tail -n 60 "$sim_log" >&2 || true
exit 1
