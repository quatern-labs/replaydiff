#!/usr/bin/env bash
# Runs `replaydiff compare` for action.yml. Inputs come from RD_* env vars; the exit code is the compare exit code.
# Writes exit-code= and report= to $GITHUB_OUTPUT (when set) and the Markdown report to $GITHUB_STEP_SUMMARY.
set -u
out_dir="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
report="$out_dir/replaydiff-report.md"
emit() { [ -n "${GITHUB_OUTPUT:-}" ] && echo "$1" >> "$GITHUB_OUTPUT"; return 0; }

if [ -z "${RD_TOLERANCES:-}" ]; then
  echo "::error title=replaydiff::the 'tolerances' input is required: pass the path to a tolerance YAML file (tolerances: path/to/tolerances.yaml)" >&2
  echo "replaydiff: error: the 'tolerances' input is required (path to a tolerance YAML file)" >&2
  emit "exit-code=2"
  exit 2
fi
if [ -z "${RD_BASE:-}" ] || [ -z "${RD_HEAD:-}" ]; then
  echo "replaydiff: error: the 'base' and 'head' inputs are required" >&2
  emit "exit-code=2"
  exit 2
fi

# RD_BASE is a space-separated list of paths
# shellcheck disable=SC2086
replaydiff compare --base $RD_BASE --head "$RD_HEAD" --tolerances "$RD_TOLERANCES" \
  --markdown "$report" --inconclusive "${RD_INCONCLUSIVE:-fail}"
code=$?
if [ -f "$report" ]; then
  [ -n "${GITHUB_STEP_SUMMARY:-}" ] && cat "$report" >> "$GITHUB_STEP_SUMMARY"
  emit "report=$report"
fi
emit "exit-code=$code"
exit "$code"
