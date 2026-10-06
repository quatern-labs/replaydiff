#!/usr/bin/env bash
# Proves the nav2 wait bound with stub processes (no ROS): a ros2 that ignores SIGTERM and blocks must still end the
# wait with exit 1 and the ERROR line within 60 s (NAV2_WAIT_S=20), leaving no stub running; and a ros2 that reports
# /odom and navigate_to_pose must pass. Needs coreutils `timeout`.
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
command -v timeout >/dev/null || { echo "SKIP: coreutils timeout not on PATH"; exit 77; }
tmp="$(mktemp -d "${TMPDIR:-/tmp}/wait_nav2.XXXXXX")"
sim=""
trap '[ -n "$sim" ] && kill -KILL "$sim" 2>/dev/null; pkill -KILL -f "sleep 6137" 2>/dev/null; rm -rf "$tmp"' EXIT
mkdir -p "$tmp/hang" "$tmp/ok"
printf '#!/usr/bin/env bash\ntrap "" TERM\nsleep 6137\n' > "$tmp/hang/ros2"
cat > "$tmp/ok/ros2" <<'STUB'
#!/usr/bin/env bash
case "$1" in
  topic) echo /odom ;;
  action) echo /navigate_to_pose ;;
esac
STUB
chmod +x "$tmp/hang/ros2" "$tmp/ok/ros2"
echo "sim log line" > "$tmp/sim.log"
fail() { echo "FAIL: $*"; exit 1; }

# stub simulation: ignores SIGTERM, stays alive
( trap '' TERM; exec sleep 6139 ) & sim=$!
start=$SECONDS
out="$(PATH="$tmp/hang:$PATH" NAV2_WAIT_S=20 NAV2_HEARTBEAT_S=5 "$here/wait_nav2.sh" "$sim" "$tmp/sim.log" test 2>&1)"; rc=$?
took=$((SECONDS - start))
echo "$out"
[ "$rc" -eq 1 ] || fail "hang case: exit $rc, want 1"
[ "$took" -lt 60 ] || fail "hang case took ${took} s, want < 60"
echo "$out" | grep -q '^ERROR: nav2 did not come up' || fail "hang case: no ERROR line"
echo "$out" | grep -q 'still waiting for nav2' || fail "hang case: no heartbeat line"
echo "$out" | grep -q 'sim log line' || fail "hang case: no sim.log tail"
sleep 1
! pgrep -f "sleep 6137" >/dev/null || fail "hang case: stub ros2 still running"
echo "hang case ok (${took} s)"

start=$SECONDS
PATH="$tmp/ok:$PATH" NAV2_WAIT_S=20 "$here/wait_nav2.sh" "$sim" "$tmp/sim.log" test || fail "pass case: nonzero exit"
[ $((SECONDS - start)) -lt 20 ] || fail "pass case too slow"
echo "pass case ok"
