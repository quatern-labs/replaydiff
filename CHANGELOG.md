# Changelog

All notable changes to replaydiff are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/) once it is released.

## [Unreleased]

### Added
- `replaydiff compare`: compares one or more base recordings against a head recording and exits non-zero on a difference outside tolerance.
- Comparators for `Twist`, `Odometry`, `Path`, `JointState` (matched by joint name) and `/tf` (listed parent/child pairs).
- Tolerance file (YAML) with per-topic tolerances, plus `joints` and `ignore_fields` for `JointState`.
- Output options: `--json`, `--markdown` and `--inconclusive`.
- GitHub Action (`action.yml`) that runs the comparison in CI.
- `replaydiff --version`, read from the single version in `pyproject.toml`.
- SPDX license header on every Python file under `replaydiff/` and `validation/`.

No release has been made; the version is `0.1.0.dev0`.
