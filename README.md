# replaydiff

Replay-based differential testing for ROS 2

Replay the same ROS 2 recording (MCAP) through two versions of your code and find out whether the behavior changed.

replaydiff runs a recording through your stack at two git refs, records the outputs, compares them topic by topic
against a per-topic tolerance file, and exits 0 (same behavior within tolerance), 1 (regression) or 2 (can't tell:
the replay is too noisy for the tolerance you set, or something failed). It is built to run in CI on pull requests.

**Status: early prototype.** `replaydiff compare` works today, on recordings you already have, for Twist and
Odometry topics, with a per-topic YAML tolerance file, a noise floor measured from several base runs, and exit codes
0/1/2. It needs no ROS install. Not built yet: the replay step (running a recording through two git refs), the other
comparators and the GitHub Action. The design is in [docs/design.md](docs/design.md).

Planned for the first release (Twist and Odometry exist; the rest is not built yet):
- Comparators for `geometry_msgs/Twist`, `nav_msgs/Odometry`, `nav_msgs/Path`, `sensor_msgs/JointState` and `/tf`.
- A YAML tolerance file with absolute/relative limits, matching modes and warmup windows.
- A measured noise floor (the base version replayed several times), so timing jitter can't pass as a regression
  and can't hide one either.
- A GitHub Action that posts the report on the pull request.

Replay and recording use [replay_testing](https://github.com/polymathrobotics/replay_testing).

## License
Apache License 2.0. See [LICENSE](LICENSE).

## Install

From a git checkout of this repository (Python 3.10 or newer; nothing is published to PyPI yet):

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install .
```

## 30-second example

This generates a tiny synthetic recording set (about 140 KB, no ROS needed): three replays of the old code, one replay
of new code that behaves the same, and one where the speed command is 30% higher. Then it compares each against the
base runs.

```bash
python examples/quickstart/generate.py runs/quickstart
replaydiff compare --base runs/quickstart/base0.mcap runs/quickstart/base1.mcap runs/quickstart/base2.mcap --head runs/quickstart/same.mcap --tolerances examples/quickstart/tolerances.yaml; echo "exit code: $?"
replaydiff compare --base runs/quickstart/base0.mcap runs/quickstart/base1.mcap runs/quickstart/base2.mcap --head runs/quickstart/slower.mcap --tolerances examples/quickstart/tolerances.yaml; echo "exit code: $?"
```

Output (copied from a real run):

```text
verdict       topic                quantity                 noise      head       tol
PASS          /cmd_vel             rate                         -         0       0.1
PASS          /cmd_vel             linear.x             0.0002836 0.0002572      0.01
PASS          /odom                rate                         -         0       0.1
PASS          /odom                pose.translation     0.0002998 0.0002588      0.01
VERDICT PASS
exit code: 0
verdict       topic                quantity                 noise      head       tol
PASS          /cmd_vel             rate                         -         0       0.1
FAIL          /cmd_vel             linear.x             0.0002836   0.07468      0.01  head p95 0.07468 > tolerance 0.01 vs every base run; window bias 0.07467 > 0.005 and > 3x base spread 1.99e-05
PASS          /odom                rate                         -         0       0.1
PASS          /odom                pose.translation     0.0002998 0.0002588      0.01
VERDICT FAIL
exit code: 1
```

The recordings are generated, not committed (`*.mcap` is gitignored); the same generator is used by the tests.

## Usage

```
replaydiff compare --base base0.mcap base1.mcap base2.mcap --head head.mcap --tolerances tolerances.yaml
```

Exit 0: same within tolerance. 1: regression. 2: can't tell (noisy base runs, too few base runs) or something failed.
`--json` prints the report as JSON. Comparing needs no ROS install. Compared today: Twist, Odometry.
