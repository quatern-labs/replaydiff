# Releasing replaydiff

The owner runs these steps. Tagging and publishing are never done by automation or by contributors' branches.

The version lives in one place: `__version__` in `replaydiff/__init__.py`. `pyproject.toml` reads it
(`dynamic = ["version"]`).

1. On a branch, set `__version__` in `replaydiff/__init__.py` (for example `0.1.0`).
2. In `CHANGELOG.md`, rename `Unreleased` to the version and date, and add a fresh empty `Unreleased` section.
3. Open a PR and merge it once CI is green (`make test` and the `build` job).
4. Tag the merge commit with a `v` prefix and the exact version, then push the tag:
   `git tag -s v0.1.0 -m "replaydiff 0.1.0" && git push origin v0.1.0`.
5. The `release` workflow (`.github/workflows/release.yml`) runs on the tag, checks the tag matches
   `__version__`, builds the sdist and wheel, runs `twine check`, and uploads them as the `dist` workflow artifact.
   It does not publish and uses no secrets.
6. Download the `dist` artifact from the workflow run and inspect it.
7. Publishing (PyPI, GitHub Release, Marketplace) is a separate, manual decision and is not set up yet.
