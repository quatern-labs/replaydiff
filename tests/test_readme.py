"""The README example runs verbatim: every ```sh block is executed, in order, in a fresh venv."""
import os
import pathlib
import importlib.util
import re
import shutil
import site
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def blocks(text, lang):
    return re.findall(rf"^```{lang}\n(.*?)^```", text, re.S | re.M)


def test_readme_example_runs_verbatim(tmp_path):
    readme = (ROOT / "README.md").read_text()
    script = "".join(blocks(readme, "sh"))  # no `set -e`: the example ends on a command that exits 1
    expected = "".join(blocks(readme, "text"))
    checkout = tmp_path / "replaydiff"
    checkout.mkdir()
    for name in ("pyproject.toml", "README.md", "LICENSE", "NOTICE", "replaydiff", "examples"):
        src = ROOT / name
        shutil.copytree(src, checkout / name, ignore=shutil.ignore_patterns("__pycache__", "*.mcap")) \
            if src.is_dir() else shutil.copy(src, checkout / name)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "python").symlink_to(sys.executable)
    env = {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "PYTHONHOME")}
    env["PATH"] = f"{bindir}:/usr/bin:/bin"
    # the dependencies come from the test environment; pip only builds and installs replaydiff itself
    # (linked without replaydiff itself, else pip sees it as already installed and skips the console script)
    deps = tmp_path / "deps"
    deps.mkdir()
    for sp in filter(os.path.isdir, site.getsitepackages()):
        for entry in pathlib.Path(sp).iterdir():
            if "replaydiff" not in entry.name.lower() and not (deps / entry.name).exists():
                (deps / entry.name).symlink_to(entry)
    env["PYTHONPATH"] = str(deps)
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    offline = all(importlib.util.find_spec(m) for m in ("setuptools", "wheel"))
    if offline:  # build with the installed backend, no network
        env.update(PIP_NO_INDEX="1", PIP_NO_BUILD_ISOLATION="0")
    r = subprocess.run(["bash", "-c", script], cwd=checkout, env=env, capture_output=True, text=True, timeout=180)
    # the script has no `set -e`, so a failed `pip install .` only shows up as a missing command later
    if not offline and "command not found" in r.stderr and re.search(
            r"Could not find a version|No matching distribution|Connection|resolution|Max retries", r.stderr):
        pytest.skip("pip needs PyPI for the build backend and it is unreachable")
    assert r.returncode == 0, r.stdout + r.stderr
    # pip's own progress lines come first; from the generator's first line on, the output is what the README shows
    assert r.stdout[r.stdout.index("wrote 5"):].strip() == expected.strip(), r.stderr
    where = subprocess.run([str(checkout / ".venv/bin/python"), "-c", "import replaydiff;print(replaydiff.__file__)"],
                           cwd=tmp_path, env=env, capture_output=True, text=True).stdout
    assert str(checkout / ".venv") in where  # the run used the freshly installed copy
    assert "exit code: 0" in r.stdout and "exit code: 1" in r.stdout
