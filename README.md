# replaydiff

Replay-based differential testing for ROS 2

Replay the same ROS 2 recording (MCAP) through two versions of your code and find out whether the behavior changed.

replaydiff runs a recording through your stack at two git refs, records the outputs, compares them topic by topic
against a per-topic tolerance file, and exits 0 (same behavior within tolerance), 1 (regression) or 2 (can't tell:
the replay is too noisy for the tolerance you set, or something failed). It is built to run in CI on pull requests.

**Status: early development.** `replaydiff compare` works on recordings you already have, for Twist, Odometry, Path, JointState and `/tf`, and the GitHub Action posts its report on the pull request. The replay step (running your stack at two git refs) is still planned. The design is in [docs/design.md](docs/design.md).

Planned for the first release:
- A YAML tolerance file with absolute/relative limits, matching modes and warmup windows.
- A measured noise floor (the base version replayed several times), so timing jitter can't pass as a regression
  and can't hide one either.
- The replay step, so the recordings are produced for you in CI.

## Install

From a git checkout (Python 3.10 or newer; compare needs no ROS install):

<!-- install -->
```bash
git clone https://github.com/quatern-labs/replaydiff.git
cd replaydiff
python -m venv .venv
. .venv/bin/activate
pip install .
```

## 30-second example

`examples/make_example.py` writes a small synthetic recording set (three base runs and a head run that drives 20%
faster, about 70 KB, no ROS needed). Then compare:

<!-- quickstart -->
```bash
python examples/make_example.py
replaydiff compare --base examples/recordings/base0.mcap examples/recordings/base1.mcap examples/recordings/base2.mcap --head examples/recordings/head.mcap --tolerances examples/tolerances.yaml
echo "exit code: $?"
```

Output:

<!-- quickstart-output -->
```text
wrote base0.mcap base1.mcap base2.mcap head.mcap to examples/recordings
verdict       topic                quantity                 noise      head       tol
PASS          /cmd_vel             rate                         -         0       0.1
FAIL          /cmd_vel             linear.x             0.0002666   0.04982      0.01  head p95 0.04982 > tolerance 0.01 vs every base run
PASS          /odom                rate                         -         0       0.1
FAIL          /odom                pose.translation     0.0003004    0.7621      0.01  head p95 0.7621 > tolerance 0.01 vs every base run
VERDICT FAIL
exit code: 1
```

The head run is faster than the base runs by more than the tolerance in `examples/tolerances.yaml`, so the verdict is FAIL and the exit code is 1.

Replay and recording use [replay_testing](https://github.com/polymathrobotics/replay_testing).

## License
Apache License 2.0. See [LICENSE](LICENSE).

## Usage

```
replaydiff compare --base base0.mcap base1.mcap base2.mcap --head head.mcap --tolerances tolerances.yaml
```

Exit 0: same within tolerance. 1: regression. 2: can't tell (noisy base runs, too few base runs) or something failed.
`--json` prints the report as JSON. Comparing needs no ROS install. Compared: Twist, Odometry, Path, JointState and `/tf`.
