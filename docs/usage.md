# Using replaydiff

replaydiff compares one recording replayed through a base version and a head version of your code, topic by topic,
against per-topic tolerances. This page covers what works today. The full design, including parts not built yet, is
in [design.md](design.md).

## Install

```
pip install .
```

Python 3.10 or newer. Comparing needs no ROS install: it reads MCAP files directly. The replay step (producing the
MCAP files) is not part of the CLI yet; bring recordings you already have. Never commit recordings to git.

## `replaydiff compare`

```
replaydiff compare --base base0.mcap base1.mcap base2.mcap --head head.mcap --tolerances tolerances.yaml
```

| Flag | Meaning |
|---|---|
| `--base` | Two or more base-run MCAP files. Their disagreement with each other is the noise floor. Required. |
| `--head` | The head-run MCAP file. Required. |
| `--tolerances` | The tolerance YAML file. Required. |
| `--config` | Alias for `--tolerances`. |
| `--json` | Print the report as JSON on stdout. With a file name, write the JSON there and print the table. |

With fewer than two base runs the noise floor can't be measured and the result is inconclusive (exit 2).

## Tolerance file

The subset of [design.md](design.md#tolerance-file-yaml) that is implemented:

```yaml
defaults:
  match: nearest        # nearest | interpolate
  max_dt: 0.02          # s, nearest: largest time gap to a base message
  max_gap: 0.2          # s, interpolate: base samples further apart are not interpolated over
  skip_first: 1.0       # s, ignored at the start
  skip_last: 0.0        # s, ignored at the end
  stat: p95             # p95 | max | mean, applied to the per-message errors
  stamp: auto           # auto | header | receive
topics:
  /cmd_vel:             # Twist or TwistStamped
    fields:
      linear.x:  {abs: 0.02, rel: 0.05}
      angular.z: {abs: 0.03}
    bias: {window: 2.0, abs: 0.01}   # systematic-shift test, scalar fields only
  /odom:                # Odometry
    match: interpolate
    pose: {translation: 0.05, rotation_deg: 2.0}
    twist: {linear: 0.05, angular: 0.05}
  /plan:                # Path
    path: {mean_dist: 0.05, hausdorff: 0.20, endpoint: 0.05, resample: 0.05}
rate: {rel: 0.10}       # message count may differ by 10%
```

- Every topic under `topics` is compared; `match`, `max_dt`, `max_gap`, `skip_first`, `skip_last`, `stat` and
  `stamp` can be set per topic as well as in `defaults`.
- `abs` and `rel` for a Twist field combine as `abs + rel * |base|`. Pose and twist limits for Odometry are
  plain numbers (metres, degrees, m/s, rad/s).
- Compared today: Twist, TwistStamped, Odometry and Path. Not implemented yet: JointState, `/tf`, `drift_per_m`,
  `match: sequence` as a setting (Path is always matched message by message), `init`, `ignore`, `count`.
- The tolerance is fixed by you. If the noise between base runs is more than half of it, the result is
  inconclusive instead of pass or fail.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Same behavior within tolerance. |
| 1 | Regression: at least one quantity is outside tolerance, or a topic is missing from the head run. |
| 2 | Can't tell (noisy base runs, too few base runs, a topic missing from a base run) or something failed (unreadable file, bad tolerance file). |

## JSON output

```
replaydiff compare ... --json report.json
```

```json
{
  "verdict": "PASS",
  "results": [
    {"topic": "/cmd_vel", "quantity": "linear.x", "verdict": "PASS", "tolerance": 0.02,
     "noise": 0.001, "head_error": 0.002, "reasons": [], "unmatched": 0, "bias": null, "bias_spread": null}
  ]
}
```

`verdict` is `PASS`, `FAIL` or `INCONCLUSIVE`. Each result is one topic and quantity (`rate` is the message-count
check); `noise` is the base-vs-base statistic and `head_error` the head-vs-base one. When the verdict is `FAIL` and
a file was written, the table output ends with a pointer line, `See why: quatern explain <file>`.

## GitHub Action

```yaml
- uses: quatern-labs/replaydiff@v0
  with:
    base: base0.mcap base1.mcap base2.mcap
    head: head.mcap
    tolerances: replaydiff.yaml
    comment: "true"
```

The step result is the `replaydiff compare` exit code. The report goes to the job summary.

| Input | Meaning |
|---|---|
| `base` | Space-separated base-run MCAP paths (two or more). Required. |
| `head` | Head-run MCAP path. Required. |
| `tolerances` | Tolerance YAML file. |
| `config` | Alias for `tolerances`. |
| `inconclusive` | How exit code 2 counts: `fail` (default) or `pass`. |
| `comment` | `true` posts or updates one pull request comment with the report; needs `pull-requests: write`. Default `false`. |
| `python-version` | Python version for the CLI. Default `3.11`. |

Output `exit-code` is the exit code of `replaydiff compare`. The action compares recordings that already exist in
the workspace; it does not replay your code.
