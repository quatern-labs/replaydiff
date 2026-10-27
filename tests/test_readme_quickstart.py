"""The README quickstart: extract its fenced commands and run them verbatim in a fresh venv."""
import pathlib
import re
import shutil
import socket
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text()


def section(title):
    m = re.search(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", README, re.S | re.M)
    assert m, title
    return m.group(1)


def fences(text, lang):
    return re.findall(rf"```{lang}\n(.*?)```", text, re.S)


def online():
    try:
        socket.create_connection(("pypi.org", 443), timeout=3).close()
        return True
    except OSError:
        return False


def test_readme_has_no_stale_status():
    assert "design only" not in README.lower()


@pytest.mark.skipif(not online(), reason="pip install needs the package index (runs in CI)")
def test_install_and_example_run_verbatim(tmp_path):
    work = tmp_path / "checkout"
    shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns(".git", ".venv", "runs", "*.egg-info", "__pycache__"))
    script = "\n".join(fences(section("Install"), "bash") + fences(section("30-second example"), "bash"))
    r = subprocess.run(["bash", "-c", script], cwd=work, capture_output=True, text=True, timeout=600,
                       env={"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(tmp_path)})
    # no `bash -e`: the compare lines exit 1 on purpose and print the code via `echo`
    assert r.returncode == 0, r.stdout + r.stderr
    shown = fences(section("30-second example"), "text")[0].splitlines()
    got = r.stdout.splitlines()
    # the pip install chatter goes to stdout too: compare the tail
    assert got[-len(shown):] == shown
