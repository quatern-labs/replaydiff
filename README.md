# replaydiff

Replay-based differential testing for ROS 2

Replay the same ROS 2 recording (MCAP) through two versions of your code and find out whether the behavior changed.

replaydiff runs a recording through your stack at two git refs, records the outputs, compares them topic by topic
against a per-topic tolerance file, and exits 0 (same behavior within tolerance), 1 (regression) or 2 (can't tell:
the replay is too noisy for the tolerance you set, or something failed). It is built to run in CI on pull requests.

**Status: early development.** What works today: `replaydiff compare` takes recordings you already have (MCAP, one per replay run), compares them topic by topic against a tolerance file and exits 0, 1 or 2. It compares `geometry_msgs/Twist`, `nav_msgs/Odometry` and `nav_msgs/Path`, measures the noise floor from two or more base runs, and needs no ROS install. Not built yet: the replay step (running your stack at two git refs), the `sensor_msgs/JointState` and `/tf` comparators, and the GitHub Action. Nothing here has been run on real recordings yet; the example below uses synthetic ones. The design is in [docs/design.md](docs/design.md).

## Install

From a git checkout (Python 3.10 or newer; there is no PyPI package yet):

```console
git clone https://github.com/quatern-labs/replaydiff.git && cd replaydiff
```

```sh
python -m venv .venv && . .venv/bin/activate
pip install .
```

## 30-second example

`examples/make_recordings.py` generates five tiny synthetic recordings (about 140 KB in total): three replays of the same code (`base0-2`, the noise floor), a new version with the same behavior (`head_same`) and one that drives 30% faster (`head_regressed`). Run from the checkout, with the venv active:

```sh
python examples/make_recordings.py
replaydiff compare --base examples/base0.mcap examples/base1.mcap examples/base2.mcap --head examples/head_same.mcap --tolerances examples/tolerances.yaml; echo "exit code: $?"
replaydiff compare --base examples/base0.mcap examples/base1.mcap examples/base2.mcap --head examples/head_regressed.mcap --tolerances examples/tolerances.yaml; echo "exit code: $?"
```

Output:

```text
wrote 5 recordings to examples
verdict       topic                quantity                 noise      head       tol
PASS          /cmd_vel             rate                         -         0       0.1
PASS          /cmd_vel             linear.x             0.0002833 0.0002678      0.01
PASS          /cmd_vel             angular.z                    0         0      0.03
PASS          /odom                rate                         -         0       0.1
PASS          /odom                pose.translation      0.000298 0.0002567      0.01
PASS          /odom                pose.rotation_deg            0         0         1
VERDICT PASS
exit code: 0
verdict       topic                quantity                 noise      head       tol
PASS          /cmd_vel             rate                         -         0       0.1
FAIL          /cmd_vel             linear.x             0.0002833   0.07475      0.01  head p95 0.07475 > tolerance 0.01 vs every base run
PASS          /cmd_vel             angular.z                    0         0      0.03
PASS          /odom                rate                         -         0       0.1
PASS          /odom                pose.translation      0.000298 0.0002567      0.01
PASS          /odom                pose.rotation_deg            0         0         1
VERDICT FAIL
exit code: 1
```

Exit 0: same behavior within tolerance. 1: regression. 2: can't tell (the base runs are too noisy for the tolerance, or fewer than two) or something failed. The recordings are generated, not committed; `examples/tolerances.yaml` is the tolerance file.

Replay and recording use [replay_testing](https://github.com/polymathrobotics/replay_testing).

## License
Apache License 2.0. See [LICENSE](LICENSE).

## Usage

```
replaydiff compare --base base0.mcap base1.mcap base2.mcap --head head.mcap --tolerances tolerances.yaml
```

`--json` prints the report as JSON. Comparing needs no ROS install. Compared today: Twist, Odometry, Path.
