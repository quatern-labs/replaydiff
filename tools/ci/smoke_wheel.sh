#!/usr/bin/env bash
# Install the built wheel into a fresh venv and smoke-run the installed CLI: `replaydiff --help`, then one
# compare on a synthetic MCAP (written with the test fixture in validation/tests/synth.py, nothing committed).
# Usage: tools/ci/smoke_wheel.sh [dist-dir]   (run from the repo root after `python -m build`)
set -euo pipefail
repo=$(cd "$(dirname "$0")/../.." && pwd)
dist=$(cd "${1:-$repo/dist}" && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

python -m venv "$work/venv"
"$work/venv/bin/pip" install --quiet "$dist"/replaydiff-*.whl
cd "$work"   # not the repo root, so the import cannot pick up the checkout

"$work/venv/bin/replaydiff" --help
"$work/venv/bin/python" - "$repo" "$work" <<'PY'
import sys
import replaydiff
repo, work = sys.argv[1:]
assert replaydiff.__file__.startswith(work), replaydiff.__file__   # imported from the venv, not the checkout
sys.path.insert(0, repo + "/validation/tests")
from synth import CLI_TOLERANCES, write_mcap
for i in range(3):
    write_mcap(f"{work}/base{i}.mcap", seed=i)
write_mcap(f"{work}/head.mcap", seed=7)
open(f"{work}/tol.yaml", "w").write(CLI_TOLERANCES)
PY
"$work/venv/bin/replaydiff" compare --base base0.mcap base1.mcap base2.mcap --head head.mcap --tolerances tol.yaml
