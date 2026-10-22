"""Repo hygiene checks: recordings stay out of git, the workflow parses."""
import pathlib
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
    import compare_proto
    cfg = compare_proto.load_config(str(ROOT / "validation" / "tolerances.yaml"))
    assert set(cfg["topics"]) == {"/sut/cmd_vel", "/sut/odom"}
