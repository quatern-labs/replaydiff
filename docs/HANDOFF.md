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

## Prior Art and README Updates

- docs/design.md: added RoboTrace and ros2_watch rows to prior-art table; "Conclusion:" scoped to the tools listed, removed unsourced claims.
- README.md: description line is "Replay-based differential testing for ROS 2".
- pyproject.toml: description set to the same line.
- Wording check: no first/only/unique/novel claims; all hits are ordinary uses.
- Open: confirm darshan-stack/ros2_watch is the intended repo.

## PR #2: Near-tolerance Core (split PR #2, slice 1)

- Re-landed c691f69 from rd-near-tolerance-try1: near-tolerance parameter overlays (0.5x–1.5x of fixed tolerances), measured effect size per run, detection-curve report, `near` job set in validation.yml (Humble only). Tolerances unchanged.
- Conflicts in validation.yml and README.md resolved onto main's Humble-default matrix (`include_jazzy` input).
- State: `validation/tests/test_experiment.py` passes offline (6 passed). ROS/CI parts unverified until Actions runs.
- Next: SCAND conversion (scand.py + tests), scand-pin job, remaining handoffs/pyproject/validation.yml bits.

## Nav2 Controller Loop Implementation

- **PR #3 attempt 2** (rd-021): merged try1; no further changes beyond try1's work. Everything from attempt 1 built (nav2 params, overlays, replay launch, SLAM Toolbox map build, docs).
- Built on main, independent of near-tolerance: nav2 `controller_server` (default Humble DWB) + `planner_server` + `map_server` params (`validation/nav2/params.yaml`), regressions as overlays on nav2's own parameters (`nav2/overlays.yaml`).
- `nav2_tools.py` (overlay, TF rule, map usability check, map cache key; unit-tested offline), `ci/nav2_replay.launch.py` (goal sender started by launch event handlers) + `ci/nav2_replay_nodes.py` (TF relay, goal sender), `ci/nav2_replay_once.sh`, `tolerances_nav2.yaml`.
- `ci/build_map.sh` builds map with SLAM Toolbox (LGPL-2.1, CI-time tool from ROS apt repo; parameters in `nav2/slam_params.yaml`, cache key = recording + params hash).
- `gen_recording.sh` records `/clock`, saves sim map, writes `goals.yaml`; `setup_ros.sh` gained `nav2` and `slam` modes. Docs: README section, RECORDINGS.md (maps, SLAM Toolbox license).
- State: `make test` green (offline helpers only). ROS side unverified until CI runs.
- Still waits: wiring into workflow and `run_experiment.sh` (rewritten by PR #2), SCAND run (prepare-recording job, pinned bag/window, SLAM map cached), `/tf` frames to drop (--drop-children default is TurtleBot3's) and map→odom assumption (identity). Needs PR #2 merged and SCAND pin.

## PR #4: Prepare-recording

- Added `validation/prepare_recording.py` + tests: sha256 verify against pin, cache key from file id + sha256 + trim window, `prepare()` pipeline (verify, convert with cloud kept, `/scan` step, `scand.py check`-style check, cache store, re-check on hit). `laserscan_commands()` for pointcloud_to_laserscan ros2 commands. `key`/`verify` CLI. Steps injected; tests need no ROS/rosbags. Raw-cloud intermediate always removed.
- Did not touch workflow or `scand.py` (`scand.py` convert/check_derived not on main yet; `prepare()` takes convert/check as callables).
- State: function written and tested, offline helpers green. `ros2 bag record` of `/scan` merged with converted topics unverified.
- Still waits on user: how CI gets SCAND bag (Dataverse returns 403 to GitHub runners), download step, prepare-recording workflow job (cache step, artifact upload), pinned file id/sha256, real bag topic map. Next: add `prepare` job wiring once decision lands.
