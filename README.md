# replaydiff

Replay-based differential testing for ROS 2

Replay the same ROS 2 recording (MCAP) through two versions of your code and find out whether the behavior changed.

replaydiff runs a recording through your stack at two git refs, records the outputs, compares them topic by topic
against a per-topic tolerance file, and exits 0 (same behavior within tolerance), 1 (regression) or 2 (can't tell:
the replay is too noisy for the tolerance you set, or something failed). It is built to run in CI on pull requests.

**Status: early development.** `replaydiff compare` works on recordings you already have (Twist, Odometry, Path, JointState and `/tf` pairs); the replay step and the GitHub Action are still planned. The design is in [docs/design.md](docs/design.md).

## Install

Not on PyPI yet. Install from a clone of this repo (Python 3.10 or newer; no ROS install needed to compare):

```console
$ git clone https://github.com/quatern-labs/replaydiff.git
$ cd replaydiff
$ pip install .
```

## Try it

This writes three base runs, two heads and a tolerance file as small MCAPs (about 70 KB) and compares them. The
base runs are the base version replayed three times; the first head behaves the same, the second has `/odom` 5 cm off.

```console
$ python examples/make_demo.py demo
$ replaydiff compare --base demo/base0.mcap demo/base1.mcap demo/base2.mcap --head demo/head_same.mcap --tolerances demo/tolerances.yaml  # exit 0
$ replaydiff compare --base demo/base0.mcap demo/base1.mcap demo/base2.mcap --head demo/head_regressed.mcap --tolerances demo/tolerances.yaml  # exit 1
```

The second command prints one line per topic and quantity and ends with `VERDICT FAIL`:

```
FAIL          /odom                pose.translation     0.0002988   0.05019      0.01  head p95 0.05019 > tolerance 0.01 vs every base run
```

Exit 0: same within tolerance. 1: regression. 2: can't tell (noisy base runs, too few base runs) or something
failed. `--json` prints the report as JSON. `--junit FILE` writes JUnit XML (one testcase per topic quantity), `--export-mcap FILE` writes head-minus-base error topics (`/replaydiff/error/...`) for Foxglove, and `--plots DIR` writes error PNGs (needs `pip install replaydiff[plots]`). Compared today: Twist, Odometry, Path, JointState, and `/tf` for the parent/child pairs you list.

Planned for the first release:
- Comparators for `geometry_msgs/Twist`, `nav_msgs/Odometry`, `nav_msgs/Path`, `sensor_msgs/JointState` and `/tf`.
- A YAML tolerance file with absolute/relative limits, matching modes and warmup windows.
- A measured noise floor (the base version replayed several times), so timing jitter can't pass as a regression
  and can't hide one either.
- A GitHub Action that posts the report on the pull request.

## Non-goals

replaydiff replays one recording through two code versions, applies per-topic tolerances, reports pass/fail plus a
diff report, and runs as a GitHub Action. It does not do, and will not do:
- cross-sensor consistency checks
- root-cause diagnosis
- suggested or generated fixes
- agents
- calibration
- deploy

Replay and recording use [replay_testing](https://github.com/polymathrobotics/replay_testing).

CI runs `make test` on every pull request and every push to main.

## License
Apache License 2.0. See [LICENSE](LICENSE).
