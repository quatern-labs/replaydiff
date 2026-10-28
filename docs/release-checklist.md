# Release checklist (nothing is released)

This records a dry run of a clean install from the checkout, run 2026-10-28 on Linux with Python 3.12 in a new venv.
No tag, release or PyPI upload was made.

## Checked

| Step | Command | Result |
|---|---|---|
| Fresh venv | `python3 -m venv $TMPDIR/fresh` | created |
| Install from the checkout | `$TMPDIR/fresh/bin/pip install .` | built and installed `replaydiff-0.1.0.dev0` with PyYAML, numpy, mcap, mcap-ros2-support, rosbags |
| Version | `replaydiff --version` | `replaydiff 0.1.0.dev0` |
| CLI help | `replaydiff compare --help` | prints `--base`, `--head`, `--tolerances`, `--json`, `--markdown`, `--inconclusive` |
| Test deps | `$TMPDIR/fresh/bin/pip install pytest` | installed |
| Unit tests | `make test PY=$TMPDIR/fresh/bin/python` | 67 passed in 26 s, offline, no ROS |
| Release checks | `pytest tests/test_release.py` | version agreement, changelog Unreleased section, SPDX headers, unmodified Apache-2.0 LICENSE, NOTICE present |

Also in place: `CHANGELOG.md` (Keep a Changelog, Unreleased section), `NOTICE`, an
`SPDX-License-Identifier: Apache-2.0` line on every `.py` file under `replaydiff/` and `validation/`.

## Not checked here

- ROS replays and the nav2 validation experiment run only in GitHub Actions CI.
- `action.yml` was not run from a workflow in this check.

## Left for the release decision (not done by this item)

- The version number (now `0.1.0.dev0`; change in `pyproject.toml` and `replaydiff/__init__.py` together) and moving the
  changelog's Unreleased entries under a dated version heading.
- The git tag.
- Publishing to PyPI (name availability, trusted publisher or token, build with `python -m build`).
- Whether `NOTICE` should carry the copyright holder's name as it does now.
