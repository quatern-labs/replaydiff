"""compare.main: an unexpected error exits 2 (error), never 1 (differences found)."""
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from replaydiff import compare

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def stubbed(monkeypatch):
    """compare with the file reading stubbed out; the report is a FAIL (exit code 1)."""
    report = SimpleNamespace(verdict="FAIL", exit_code=1, to_dict=lambda: {})
    monkeypatch.setattr(compare, "load_config", lambda p: {"topics": {}})
    monkeypatch.setattr(compare, "read_mcap", lambda p, t=None: None)
    monkeypatch.setattr(compare, "expand_tf", lambda runs, cfg: ([1, 2, 3], cfg))
    monkeypatch.setattr(compare, "evaluate", lambda b, h, c, e=None: report)
    monkeypatch.setattr(compare, "format_report", lambda r: "report")


ARGS = ["--base", "a", "b", "--head", "h", "--tolerances", "t"]


def test_fail_verdict_still_exits_1(stubbed, capsys):
    assert compare.main(ARGS) == 1


def test_unexpected_exception_exits_2(stubbed, monkeypatch, capsys):
    def boom(*a):
        raise RuntimeError("boom")
    monkeypatch.setattr(compare, "format_report", boom)
    assert compare.main(ARGS) == 2
    assert "boom" in capsys.readouterr().err


def test_markdown_write_failure_exits_2(stubbed, tmp_path, capsys):
    assert compare.main([*ARGS, "--markdown", str(tmp_path / "missing" / "r.md")]) == 2
    assert "error" in capsys.readouterr().err


def test_action_uses_are_pinned_to_a_full_sha():
    a = yaml.safe_load((ROOT / "action.yml").read_text())
    uses = [s["uses"] for s in a["runs"]["steps"] if "uses" in s]
    assert uses
    for u in uses:
        assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", u), u
