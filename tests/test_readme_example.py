"""Runs the commands in the README's "Try it" block and checks the exit codes it states."""
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def readme_commands():
    text = (ROOT / "README.md").read_text()
    block = text.split("## Try it", 1)[1].split("```console", 1)[1].split("```", 1)[0]
    cmds = []
    for line in filter(str.strip, block.splitlines()):
        m = re.match(r"\$ (.+?)(?:\s+# exit (\d))?$", line)
        assert m, line
        cmds.append((m.group(1), None if m.group(2) is None else int(m.group(2))))
    return cmds


def test_readme_try_it_commands(tmp_path):
    (tmp_path / "examples").symlink_to(ROOT / "examples")
    cmds = readme_commands()
    assert [c for c, _ in cmds if "make_demo" in c] and [e for _, e in cmds if e is not None] == [0, 1]
    fail_out = ""
    for cmd, expected in cmds:
        argv = shlex.split(cmd)
        if argv[0] == "python":
            argv[0:1] = [sys.executable]
        elif argv[0] == "replaydiff":
            argv[0:1] = [sys.executable, "-m", "replaydiff.cli"]
        p = subprocess.run(argv, cwd=tmp_path, capture_output=True, text=True, env=None)
        assert p.returncode == (0 if expected is None else expected), (cmd, p.stdout, p.stderr)
        if expected == 1:
            fail_out = p.stdout
    assert "VERDICT FAIL" in fail_out
    fails = [ln.split() for ln in fail_out.splitlines() if ln.startswith("FAIL")]
    assert [f[1:3] for f in fails] == [["/odom", "pose.translation"]]
    assert "Nothing is implemented" not in (ROOT / "README.md").read_text()
