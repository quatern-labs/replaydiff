# Changelog

All notable changes are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [Semantic Versioning](https://semver.org/). Nothing is released yet.

## [Unreleased]

### Added
- `replaydiff compare`: compares a head recording against N >= 2 base replays; the base-vs-base spread is the noise floor.
- Comparators for Twist, Odometry, Path, JointState (matched by joint name) and `/tf` (listed parent/child pairs).
- Tolerance file (YAML), including `joints` and `ignore_fields`.
- Reports: `--json [FILE]`, `--markdown FILE` (PR-comment sized) and `--inconclusive fail|pass`.
- Composite GitHub Action (`action.yml`) that runs the comparison and posts or updates one PR comment.
- `replaydiff --version`; the version comes from `pyproject.toml` and `replaydiff.__version__`.
- SPDX license headers on every Python file and a release check (`tests/test_release.py`, `docs/release-checklist.md`).
