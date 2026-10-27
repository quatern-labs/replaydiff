# replaydiff

Replay-based differential testing for ROS 2

Replay the same ROS 2 recording (MCAP) through two versions of your code and find out whether the behavior changed.

replaydiff runs a recording through your stack at two git refs, records the outputs, compares them topic by topic
against a per-topic tolerance file, and exits 0 (same behavior within tolerance), 1 (regression) or 2 (can't tell:
the replay is too noisy for the tolerance you set, or something failed). It is built to run in CI on pull requests.

**Status: early development.** `replaydiff compare` works on recordings you already have (Twist, Odometry, Path, JointState); the replay step, the `/tf` comparator and the GitHub Action are still planned. The design is in [docs/design.md](docs/design.md).

Planned for the first release:
- Comparators for `geometry_msgs/Twist`, `nav_msgs/Odometry`, `nav_msgs/Path`, `sensor_msgs/JointState` and `/tf`.
- A YAML tolerance file with absolute/relative limits, matching modes and warmup windows.
- A measured noise floor (the base version replayed several times), so timing jitter can't pass as a regression
  and can't hide one either.
- A GitHub Action that posts the report on the pull request.

Replay and recording use [replay_testing](https://github.com/polymathrobotics/replay_testing).

## License
Apache License 2.0. See [LICENSE](LICENSE).

## Usage

```
pip install .
replaydiff compare --base base0.mcap base1.mcap base2.mcap --head head.mcap --tolerances tolerances.yaml
```

Exit 0: same within tolerance. 1: regression. 2: can't tell (noisy base runs, too few base runs) or something failed.
`--json` prints the report as JSON. Comparing needs no ROS install. Compared today: Twist, Odometry, Path.

## GitHub Action
```yaml
permissions: {pull-requests: write}
steps:
  - uses: quatern-labs/replaydiff@main
    with:
      base: runs/base0.mcap runs/base1.mcap runs/base2.mcap
      head: runs/head.mcap
      tolerances: replaydiff.yaml
```
Runs `replaydiff compare` on recordings you already produced, uploads `report.json`, `report.md` and `report.txt` as
the `replaydiff-report` artifact, adds the table to the job summary, and on `pull_request` events posts or updates one
PR comment (`comment: "false"` turns that off). The step exits with the tool's code; `inconclusive: pass` lets an
inconclusive verdict through (a tool error still fails). The workflow has not yet run on GitHub.
