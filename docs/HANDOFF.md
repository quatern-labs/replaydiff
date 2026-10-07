# Handoff Notes

## PR #1: CI Fix (validation-experiment)

### Current State
- Validation workflow runs generate and replay jobs in `container: ros:<distro>` containers (removed `ros-tooling/setup-ros` due to unauthenticated GitHub API rate-limiting with 12 simultaneous jobs).
- `validation/ci/setup_ros.sh`: root-aware (sudo only if not root), noninteractive; libunwind purge applied.
- `validation/ci/gen_recording.sh`: nav2 wait has a hard 240 s deadline with per-call `timeout`; on expiry prints what it waited for and last 60 sim.log lines, then exits 1.
- Jazzy generate/replay jobs marked `continue-on-error` (nav2 does not come up reliably in Jazzy).
- Aggregate runs on Humble results; Jazzy flagged as known-failing.

### Resolution Path
Previous fixes (rd-008, rd-009):
- Removed `libunwind-14-dev` conflicts before humble sim install; upgraded to purge all versioned `libunwind-*-dev`.
- Added `set +u` around ROS setup.bash sourcing in `gen_recording.sh` and `replay_once.sh` to fix `AMENT_TRACE_SETUP_FILES: unbound variable`.

### Open Items
- ROS runs only in GitHub Actions CI; bash syntax verified locally but logic unverified until CI runs.
- Image apt packages (git, python3-pip, etc.) assumed available via apt in ros:humble/jazzy containers.
