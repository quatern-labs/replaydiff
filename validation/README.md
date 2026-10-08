# replaydiff validation experiment

Question (docs/design.md, "To validate before release"): does an N-replay noise floor, measured on a replayed
recording, let replaydiff catch injected regressions, and how often does it honestly say "can't tell"
(INCONCLUSIVE)? This is a standalone experiment, small on purpose, and may be rewritten later. It is not the
replaydiff CLI.

## Method

1. **Recording.** A TurtleBot3 + nav2 simulation is run headless in CI and recorded to MCAP (about 40 s), once per
   ROS distro. See [RECORDINGS.md](RECORDINGS.md): no permissively licensed public bag was found, so it is
   generated. The recording never enters git.
2. **System under test.** `ci/sut.py`, a small pure-pursuit controller written for this experiment. It reads the
   recorded `/odom` and `/plan` and publishes `/sut/cmd_vel` (Twist) and `/sut/odom` (the input odometry through a
   frame correction). It is **not** the nav2 controller: nav2's controller needs live costmaps, TF and action goals
   that a bag replay does not supply. The experiment needs a node that turns recorded inputs into cmd_vel and
   odometry outputs and has parameters to inject faults. This limits what the results say: they show how the
   method behaves on a ROS 2 replay with a real middleware, not how nav2 itself behaves.
3. **Replay.** `ros2 bag play --clock 1000 -r <rate> --topics /odom /scan /tf /tf_static /plan` (only the recorded
   inputs; the original `/cmd_vel` is not replayed), nodes with `use_sim_time`, outputs recorded with
   `ros2 bag record -s mcap --use-sim-time` so receive time is sim time. Rates 0.5x and 1.0x. Plain
   `ros2 bag play/record` rather than replay_testing: replay_testing's runner does the same play and record
   underneath, but adds a pytest/launch_testing layer and a v0.0.x dependency, and this experiment needs to
   overlay parameters on one SUT per run. The real driver is expected to use replay_testing (design.md).
4. **Runs.** Per distro, rate and repetition: 6 base replays of the same code (the N=3 noise floor uses base0-2, N=5
   uses base0-4), plus one replay per injected regression. Repetitions are independent CI jobs (3 per distro and
   rate, each on its own VM). Base-vs-base is judged by treating base3-5 (N=3) or base5 (N=5) as the "head": a
   run that is never part of the base set.
5. **Injected regressions** (parameter overlays on the same code). Controls, far past the tolerances: `gain10` and
   `gain30` (`velocity_gain` 1.1 / 1.3), `offset2cm` (`/sut/odom` x offset 0.02 m), `drop_odom` (`/sut/odom` not
   published). Near the tolerances (Humble only, in separate `near-tolerance` jobs with their own 6 base replays):
   `gain_x0.5/0.75/1.0/1.5` (`velocity_gain` 1.025 / 1.0375 / 1.05 / 1.075, about 0.5x-1.5x of the 0.01 m/s
   linear.x tolerance at the 0.2 m/s cruise) and `offset_x0.5/0.75/1.0/1.5` (x offset 0.005 / 0.0075 / 0.010 /
   0.015 m, 0.5x-1.5x of the 0.01 m translation tolerance).
6. **Detection curve.** The gain only scales the speed where the controller commands one, so each run's *measured*
   effect size is computed from the data: head-vs-base p95 / tolerance of the quantity the regression acts on.
   Verdicts are judged against it: below 0.9x a PASS is correct and a FAIL fired only by the bias-window check is
   the bias check doing its job (reported as such); 0.9x-1.1x any answer is acceptable; above 1.1x a PASS is a miss.
   A FAIL below 0.9x from any other check is a false FAIL. The report has one row per regression, rate and N with the
   measured effect, PASS / FAIL / INCONCLUSIVE counts, which check fired (p95, bias, count, missing), the correct
   answer and the false-FAIL / miss / INCONCLUSIVE rates.
7. **Compare.** `compare_proto.py` follows design.md: tolerance fixed, noise = worst base-vs-base p95 over all base
   pairs; noise > 0.5 x tolerance -> INCONCLUSIVE; else FAIL if head p95 > tolerance against every base run (the
   reported value is the smallest); bias-window test (mean signed error per 2 s window must exceed `bias.abs` and 3x
   the RMS of the base-vs-base window biases); message-count check (head count differs by more than 10% from every
   base run -> FAIL); a missing topic FAILs and is never interpolated over, and base gaps wider than `max_gap`
   are left unmatched. Overall: any FAIL -> FAIL, else any INCONCLUSIVE -> INCONCLUSIVE, else PASS.
   Not implemented in the prototype: Path/JointState/TF comparators, `sequence` matching, drift per metre,
   time-shift estimation. `rel` tolerances are applied as `max(0, |d| - rel*|ref|) <= abs`.

## Tolerances ([tolerances.yaml](tolerances.yaml)) and why

| Quantity | Tolerance | Why |
|---|---|---|
| `/sut/cmd_vel` linear.x | abs 0.01 m/s | 5% of the 0.2 m/s cruise speed: a 10% velocity gain change (0.02 m/s) must be able to fail |
| `/sut/cmd_vel` angular.z | abs 0.03 rad/s | looser, the commanded turn rate is jumpier |
| `/sut/cmd_vel` bias | window 2 s, abs 0.005 | catches a systematic shift under the p95 tolerance |
| `/sut/odom` translation | 0.01 m (interpolate, max_gap 0.2 s) | a 2 cm offset must fail |
| `/sut/odom` rotation | 1 deg | |
| `/sut/odom` twist | linear 0.02, angular 0.03 | |
| message rate | 10% | design.md default |
| skip_first | 1 s | startup transient |

The tolerances were chosen before the first run from the injected sizes, not tuned to the results. If the first
CI run shows them to be unreachable (everything INCONCLUSIVE), that is a finding to report, not a reason to
silently widen them.

## Run it

- Unit tests (offline, no ROS, under a minute): `make test`.
- Experiment: GitHub Actions, workflow `validation` (workflow_dispatch, or a pull request touching `validation/**`).
  Matrix: Humble on ubuntu-22.04 by default (Jazzy on ubuntu-24.04 only on a manual `workflow_dispatch` with `include_jazzy`, `continue-on-error`: known-failing, nav2 does not come up in the headless sim there), x rates 0.5 / 1.0 x 3 repetitions, 60 min cap per job.
  Plus the same 6 Humble-only `near-tolerance` jobs (artifacts `result-humble-<rate>-rep<n>-near`).
  Artifacts: `validation-results` (`results/validation.json`, `results/validation.md`), per-job `result-*`
  files, short-lived `recording-<distro>`.
- Compare two or more bags yourself:
  `python validation/compare_proto.py --config validation/tolerances.yaml --base b0.mcap b1.mcap b2.mcap --head h.mcap`
  (exit 0 pass, 1 FAIL, 2 INCONCLUSIVE).

## What would count as success

Every injected regression is caught (FAIL) or honestly reported INCONCLUSIVE, none passes, and there are zero
false FAILs on base-vs-base. The INCONCLUSIVE rate is reported next to it: a method that is INCONCLUSIVE on
everything is honest but useless, so a high rate is a result too, with the playback rate and N that reduce it.

## Known limits

- The ROS side (`ci/`) could not be run where it was written (no ROS, no Docker); the first CI run is its real test and
  may need fixes (simulation launch arguments per distro, topic names, timing).
- Simulated recording and a simple controller: see above.
- GitHub-hosted runners share CPU with other jobs, which is realistic for CI but makes absolute noise numbers
  runner-dependent.

## Results

Pending the first CI run.
