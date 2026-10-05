# Rules for contributors and agents

replaydiff is a public Apache-2.0 open-source tool. The design is `docs/design.md`; it is the spec. If the design
doesn't match what you find in replay_testing, ROS or a recording, stop and ask instead of guessing.

- Everything in this repo is public. No product code from other projects, no internal names, hosts or private
  context in any file.
- Dependencies only under Apache-2.0, BSD or MIT (replay_testing, mcap, numpy/scipy, PyYAML, pytest). Name and
  license every new dependency in the PR description.
- Never commit recordings: no `*.mcap`, `*.db3`, bag directories, `runs/` or `results/`. Recordings are downloaded
  or generated in CI only.
- Every commit is signed off (`git commit -s`, DCO). No Co-Authored-By trailers. Never push to main; work on a
  branch and open a PR.
- `make test` runs the unit tests offline with no ROS install and stays under 2 minutes. ROS-dependent code is
  exercised only in GitHub Actions CI.
