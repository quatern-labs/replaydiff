# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- CLI: `replaydiff compare --base <mcap>... --head <mcap> --tolerances <file.yaml> [--json [FILE]]` compares
  recordings you already have against per-topic tolerances (Twist, Odometry, Path) and exits 0 (pass), 1 (fail)
  or 2 (bad input).

### Planned

- GitHub Action that posts the diff report on the pull request (not yet in the repository).
- Replay step, and JointState and `/tf` comparators.
