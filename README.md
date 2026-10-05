# replaydiff

Replay the same ROS 2 recording (MCAP) through two versions of your code and find out whether the behavior changed.

replaydiff runs a recording through your stack at two git refs, records the outputs, compares them topic by topic
against a per-topic tolerance file, and exits 0 (same behavior within tolerance), 1 (regression) or 2 (can't tell:
the replay is too noisy for the tolerance you set, or something failed). It is built to run in CI on pull requests.

**Status: design only. Nothing is implemented yet.** The design is in [docs/design.md](docs/design.md).

Planned first release:
- Comparators for `geometry_msgs/Twist`, `nav_msgs/Odometry`, `nav_msgs/Path`, `sensor_msgs/JointState` and `/tf`.
- A YAML tolerance file with absolute/relative limits, matching modes and warmup windows.
- A measured noise floor (the base version replayed several times), so timing jitter can't pass as a regression
  and can't hide one either.
- A GitHub Action that posts the report on the pull request.

Replay and recording use [replay_testing](https://github.com/polymathrobotics/replay_testing).

## License
Apache License 2.0. See [LICENSE](LICENSE).
