# replaydiff design

Status: design only, nothing is implemented yet.

## What it does
Replay the same recorded MCAP through a ROS 2 workspace at two git refs (base, head), record the nodes' outputs
each time, compare the outputs topic by topic against a YAML tolerance file, and exit 0 (same behavior within
tolerance), 1 (regression) or 2 (inconclusive or error). Runs locally and as a GitHub Action on pull requests.

Who it's for: any ROS 2 team that changes a node (controller, planner, localization) and wants "did behavior on
this recording change, and by how much" in CI instead of eyeballing two plots in Foxglove.

## Prior art (from code, not READMEs)
From GitHub repository and code search and direct reads of each tool's source (October 2026).

| Tool | What the code actually does | Gap for this use |
|---|---|---|
| polymathrobotics/replay_testing (Apache-2.0, v0.0.4, CI on Humble/Jazzy/Kilted/Rolling) | FIXTURES -> RUN -> ANALYZE. `filter_mcap` strips output topics from the input; runner does `ros2 bag play -r <rate> [--clock 1000]` and `ros2 bag record -s mcap --all`; `@analyze` unittest classes read the run MCAP; JUnit output | One code version per run; no baseline, no git refs, no comparison, no tolerances. We build on it for replay+record |
| bagx `compare.py` | Aggregate quality metrics of two bags, fixed 1% threshold, improved/degraded/unchanged | No per-message matching, no per-topic tolerance file, no replay |
| rosbag-doctor `compare.py` (MIT) | TopicDelta: rate, max gap, type change; YAML policy, exit 0/1/2 | Timing metadata only, not message values. Closest precedent for policy file + exit codes; we copy the shape, not code |
| IamPhytan/rosbag-compare (ROS 1) | Topic presence | No values |
| MamoruAsagami/BagDiff | Java GUI viewer | Not CI |
| CPFL/ros2b2b | NDT-specific scripts | Not general |
| evo (trajectory eval) | `associate_trajectories` (t_max_diff 0.01 s), APE/RPE | Trajectories only, no replay, no exit gate. Precedent for matching and pose metrics |
| driving_log_replayer (Autoware) | Replay with scenario-specific aggregate evaluators | Autoware-bound, judges against criteria, not against a second code version |

Conclusion: no existing tool diffs message values between two code versions on the same recording with
per-topic tolerances and a CI exit code. Everything else in GitHub code search was one-off compare scripts
inside project repos.

## Architecture
```
replaydiff run --recording drive.mcap --base origin/main --head HEAD --config replaydiff.yaml
  1. for ref in (base, head):  git worktree add -> colcon build (cached by ref sha) -> source install
  2. replay_testing run per ref  (same filtered input, same runner args) -> out-<ref>-<i>.mcap
     base is replayed N times (default 3) for the noise floor, head once (or N with --repeat)
  3. replaydiff compare out-base-*.mcap out-head.mcap --config replaydiff.yaml
       -> report.json, report.md, junit.xml, exit code
```
- `compare` is usable alone on any two (or 2+N) MCAPs, so teams with their own replay setup can use only it.
- replay_testing is used as a library/CLI dependency, unmodified. Our driver generates the replay test file
  (fixture = the recording, run = the user's launch file, no analyze stage) so users write no Python.
- Inputs fixed per run: same filtered MCAP, same playback rate, same QoS overrides, same params. The report
  records both ref shas, the recording's hash, ROS distro, rmw and runner args.
- Language: Python (rosbag2_py / mcap reader), packaged as a ROS 2 package and a pip package.

## Timestamp matching
- Time base: `header.stamp` when the message has one and the stack runs on sim time (`--clock`); otherwise the
  record (receive) time, flagged in the report as noisier. Per-topic override: `stamp: header|receive`.
  (Open question: confirm which time replay_testing's reader yields; see "Open questions and risks".)
- Times are made relative to the first input message of the recording, so both runs share an origin.
- Matching per topic, configurable:
  - `nearest` (default): each head message pairs with the base message nearest in time within `max_dt`
    (default 0.02 s); unmatched messages count separately.
  - `interpolate`: base value linearly interpolated at the head stamp (slerp for orientations), for
    continuous signals like odom and joint_states. Only between two base samples within `max_gap`.
  - `sequence`: i-th with i-th, for event topics like path where timing matters less than content.
- Warmup and trim: `skip_first` / `skip_last` seconds per topic (startup transients, shutdown).

## Tolerance file (YAML)
```yaml
version: 1
defaults:
  match: nearest
  max_dt: 0.02          # s
  skip_first: 1.0       # s
  stat: p95             # p95 | max | mean, applied to per-message errors
  noise_repeats: 3
topics:
  /cmd_vel:
    type: geometry_msgs/msg/Twist          # or TwistStamped (checked against the bag)
    fields:
      linear.x:  {abs: 0.02, rel: 0.05}
      angular.z: {abs: 0.03}
    bias: {window: 2.0, abs: 0.01}          # systematic-shift test, see "Output jitter"
  /odom:
    type: nav_msgs/msg/Odometry
    match: interpolate
    pose: {translation: 0.05, rotation_deg: 2.0, drift_per_m: 0.01}
    twist: {linear: 0.05, angular: 0.05}
  /plan:
    type: nav_msgs/msg/Path
    match: sequence
    path: {mean_dist: 0.05, hausdorff: 0.20, endpoint: 0.05, resample: 0.05}
  /joint_states:
    type: sensor_msgs/msg/JointState
    match: interpolate
    joints: {"*": {position: 0.01, velocity: 0.05}, gripper_joint: {position: 0.002}}
    ignore_fields: [effort]
  /tf:
    pairs:
      - {parent: odom, child: base_link, translation: 0.05, rotation_deg: 2.0}
rate: {rel: 0.10}        # per-topic message rate may differ by 10%
count: {missing_topic: fail, new_topic: warn}
ignore: [/rosout, /parameter_events, /diagnostics]
```
- abs and rel combine as `|d| <= abs + rel * |base|` (numpy `isclose` semantics, documented).
- Angles are wrapped to [-pi, pi]; quaternions compared as rotation angle of q_base^-1 * q_head.
- A topic not listed is compared only for presence, type and rate unless `strict: true`.
- `replaydiff init --recording out.mcap` writes a starter file from the topics and types it finds, with the
  tolerances measured from the base noise floor rounded up, marked `# measured, review`.

## Comparators (first release)
| Type | Compared | Metric |
|---|---|---|
| geometry_msgs Twist / TwistStamped | listed components | per-message abs/rel error, stat over the topic |
| nav_msgs Odometry | pose, twist | translation error and rotation angle (APE-like); drift per metre travelled (RPE-like); twist like Twist |
| nav_msgs Path | whole path per message | resample both at `resample` m; mean point distance, Hausdorff, endpoint distance; pose count delta |
| sensor_msgs JointState | by joint name, not index | position/velocity/effort per joint; joint-set mismatch is a failure |
| tf2_msgs TFMessage (/tf, /tf_static) | listed parent/child pairs, direct edges only | translation, rotation angle; /tf_static compared once as a set |
| any other type | presence, type, rate, count | no value diff; listed as "not compared" |
Every comparator is a small class with `match()`, `errors()` and a stat, so others can add types later.

## Output jitter: absorbing timing noise without hiding regressions
Replay of the same code is not deterministic: `ros2 bag play` has no back-pressure and drops or delays
messages when nodes lag, executors interleave callbacks differently, `use_sim_time` is honoured unevenly, and
/tf_static replay is unreliable. Deterministic replay exists only for single-process stacks with a patched
rclcpp (RSLCPP, arXiv 2601.07052). So the tool must measure noise rather than assume it away.

Reduce it (runner defaults):
- Sim time: `--clock` publishing from the bag, `use_sim_time:=true` set for every node by the generated launch.
- Playback at 0.5x by default (`playback_rate`), reliable QoS overrides for the compared topics, /tf_static
  republished latched by the driver before playback starts.
- Same machine, both refs back to back, builds done before any replay (no build load during replay).

Measure it (noise floor):
- Replay the base ref N times (default 3). For every compared quantity, base-vs-base error gives the noise
  floor: `noise = stat(errors between base runs)`.

Decide with it, without letting it widen the tolerance:
- The YAML tolerance is the fixed limit. Noise never raises it.
- If `noise > 0.5 * tolerance` for a quantity, that quantity is INCONCLUSIVE: the recording or the replay is
  too noisy to tell a regression of that size. Exit 2, with the measured noise and a suggestion (slower
  playback, interpolate matching, or a deliberate wider tolerance in the YAML, which shows in the PR diff).
- Otherwise head vs base: FAIL if `stat(head errors) > tolerance`, measured against each base run; the
  reported value is the smallest of them (benefit of the doubt for timing noise only).
- Timing-only effects are separated from value changes: a value compared by `interpolate` is insensitive to a
  few ms of shift; a whole-output time shift (estimated by cross-correlation on one continuous topic) is
  reported as its own number with its own `max_shift` tolerance, so "same output, 30 ms later" is visible but
  not counted as a value regression.

Catch real regressions that hide inside tolerance:
- Bias test: per time window (`bias.window`), the mean signed head-minus-base error. Noise averages out,
  a systematic shift does not. FAIL if any window's mean bias exceeds `bias.abs` and exceeds 3x the base-vs-base
  window bias spread.
- Drift test (odom, tf): error per metre travelled, so a slow drift that stays under the absolute tolerance
  for a short recording still fails.
- Missing, extra and dropped messages are counted, never interpolated over: a head run that publishes 10%
  fewer /cmd_vel messages fails the rate check even if every matched value agrees.
- p95 by default rather than max, with `max` available per field; the report always shows max, p95 and the
  worst timestamps, so a single spike is visible even when it doesn't fail.

Exit codes: 0 pass; 1 at least one FAIL; 2 no FAIL but at least one INCONCLUSIVE, or a tool/build/replay
error. CI treats 2 as failed by default (`--inconclusive=pass` to change).

To validate before release (not known yet): run base-vs-base on public recordings (nav2 / TurtleBot demos)
to see real noise floors, and inject known regressions (gain change, 2 cm offset, dropped topic) to check
they are caught. The N-replay noise floor is new; no prior tool we found does it, so it needs this evidence.

## Reports
- `report.md`: verdict table per topic/quantity (base noise, head error, tolerance, verdict), worst moments
  with timestamps, notes on unmatched messages and time shift. Fits a PR comment.
- `report.json`: everything, machine-readable. `junit.xml`: one testcase per topic quantity.
- Optional `--plots` (matplotlib PNGs) and `--export-mcap` (head-minus-base error topics) for Foxglove.

## GitHub Action
```yaml
- uses: quatern-labs/replaydiff@v0
  with:
    recording: test/data/drive.mcap          # or a URL / LFS path
    launch: my_pkg/launch/replay.launch.py
    config: replaydiff.yaml
    base: ${{ github.event.pull_request.base.sha }}
    distro: jazzy
```
- Composite action in a `ros:<distro>` container: checkout with full history, rosdep, colcon build per ref
  with ccache keyed by ref sha, replay, compare, upload report artifacts, post or update one PR comment with
  report.md (only with `pull-requests: write`), exit with the tool's code.
- Recordings are large: documented paths are Git LFS, release assets or an S3/HTTP URL (replay_testing already
  has S3 fixtures). The tool never commits recordings.

## Open questions and risks
- replay_testing is small (one org, 29 stars, v0.0.x). Risk: API churn or abandonment. Mitigation: pin a version;
  the driver touches only its runner and fixture API; `compare` doesn't depend on it at all.
- Which timestamp replay_testing's reader yields (record time vs header stamp); decide the default after checking.
- Multi-process stacks will stay nondeterministic; the inconclusive verdict is the honest answer there.
- /tf_static and latched topics under replay need a test on Humble and Jazzy.
- Build time per ref in CI (two full colcon builds): ccache and building only packages changed between refs
  (`colcon build --packages-up-to` of changed packages) are the levers.
