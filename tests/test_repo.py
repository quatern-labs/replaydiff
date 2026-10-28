"""Repo hygiene checks: recordings stay out of git, the workflow parses."""
import os
import pathlib
import re
import subprocess

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_gitignore_blocks_recordings():
    for p in ("a.mcap", "x/y.mcap", "runs/a", "results/a.json", "bag/x.db3"):
        r = subprocess.run(["git", "check-ignore", "-q", p], cwd=ROOT)
        assert r.returncode == 0, p


class UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects a mapping key repeated within one mapping."""

    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=True)
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicate key {key!r}", key_node.start_mark)
            seen.add(key)
        return super().construct_mapping(node, deep)


def load_unique(text, name="<string>"):
    try:
        return yaml.load(text, Loader=UniqueKeyLoader)
    except yaml.constructor.ConstructorError as e:
        raise AssertionError(f"{name}: {e.problem} (line {e.problem_mark.line + 1})") from e


def test_workflows_parse():
    for f in (ROOT / ".github" / "workflows").glob("*.yml"):
        doc = load_unique(f.read_text(), f.name)
        assert "jobs" in doc, f


def test_loader_rejects_duplicate_key():
    assert load_unique("a: 1\nb: {c: 2}\n") == {"a": 1, "b": {"c": 2}}
    with pytest.raises(AssertionError, match=r"x\.yml: duplicate key 'a' \(line 3\)"):
        load_unique("a: 1\nb: 2\na: 3\n", "x.yml")


def test_tolerance_file_loads():
    from replaydiff import compare as compare_proto
    cfg = compare_proto.load_config(str(ROOT / "validation" / "tolerances.yaml"))
    assert set(cfg["topics"]) == {"/sut/cmd_vel", "/sut/odom"}


def _fenced_after(readme, marker):
    m = re.search(re.escape(marker) + r"\n```\w*\n(.*?)```", readme, re.S)
    assert m, marker
    return m.group(1)


def test_readme_quickstart_runs_verbatim(tmp_path):
    """The README's install and 30-second commands run as written in a fresh venv, with the output shown."""
    import shutil
    import sys
    import time
    readme = (ROOT / "README.md").read_text()
    install = [l for l in _fenced_after(readme, "<!-- install -->").splitlines() if l.startswith("pip install")]
    assert install == ["pip install ."]
    work = tmp_path / "repo"
    work.mkdir()
    for name in ("pyproject.toml", "README.md", "LICENSE", "NOTICE"):
        shutil.copy(ROOT / name, work / name)
    for name in ("replaydiff", "examples"):
        shutil.copytree(ROOT / name, work / name, ignore=shutil.ignore_patterns("__pycache__", "recordings"))
    subprocess.run([sys.executable, "-m", "venv", str(tmp_path / "venv")], check=True)
    env = {**os.environ, "PATH": f"{tmp_path / 'venv/bin'}:{os.environ['PATH']}", "VIRTUAL_ENV": str(tmp_path / "venv"),
           "PIP_DISABLE_PIP_VERSION_CHECK": "1"}
    env.pop("PYTHONPATH", None)
    inst = subprocess.run(install[0], shell=True, cwd=work, env=env, capture_output=True, text=True, timeout=240)
    if inst.returncode:
        pytest.skip("pip install needs a package index (offline): " + inst.stderr[-200:])
    t0 = time.time()
    r = subprocess.run(["bash", "-c", _fenced_after(readme, "<!-- quickstart -->")], cwd=work, env=env,
                       capture_output=True, text=True, timeout=30)
    assert time.time() - t0 < 30
    assert r.stdout == _fenced_after(readme, "<!-- quickstart-output -->"), r.stdout + r.stderr
