# Release checklist

Checks that make the first release verifiable without making it. Nothing here tags, builds a release or publishes.
`tests/test_release.py` enforces the automatable items (run by `make test`).

## Automated (tests/test_release.py)

- [x] One version: `pyproject.toml` and `replaydiff.__version__` agree (`0.1.0.dev0`); `replaydiff --version` prints `replaydiff 0.1.0.dev0`.
- [x] `CHANGELOG.md` (Keep a Changelog) has an `Unreleased` section listing the delivered features.
- [x] `# SPDX-License-Identifier: Apache-2.0` is the first line (second after a shebang) of every `.py` file under `replaydiff/` and `validation/`.
- [x] `LICENSE` is the unmodified Apache-2.0 text (sha256 `cfc7749b...523d30`); `NOTICE` exists and names the license.

## Clean install from scratch (run 2026-10-28, Python 3.12.3, Linux)

| Step | Command | Result |
| --- | --- | --- |
| 1. Fresh venv | `python3 -m venv $TMP/fresh` | created |
| 2. Install from the checkout | `$TMP/fresh/bin/pip install ".[dev]"` | `Successfully installed ... replaydiff-0.1.0.dev0 ...` |
| 3. Version | `$TMP/fresh/bin/replaydiff --version` (run outside the checkout) | `replaydiff 0.1.0.dev0` |
| 4. Help | `$TMP/fresh/bin/replaydiff compare --help` | usage for `--base`, `--head`, `--tolerances`, `--json`, `--markdown`, `--inconclusive`; exit 0 |
| 5. Tests | `make test PY=$TMP/fresh/bin/python` | `71 passed in 25.65s` |

Not run here: ROS replays (GitHub Actions CI only) and the GitHub Action itself.

## Left for the release decision (not done by this work)

- [ ] Choose the version number (currently `0.1.0.dev0`; moving off `.dev` is a bump).
- [ ] Move the changelog's `Unreleased` entries under that version and date.
- [ ] Create and sign the git tag.
- [ ] Decide whether to publish to PyPI, and build and upload.
- [ ] Review `NOTICE`: it currently carries an individual's name as copyright holder; confirm that is the holder you want on a public release.
- [ ] Re-run the table above on the release commit.
