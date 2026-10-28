# SPDX-License-Identifier: Apache-2.0
import ast
import pathlib
from types import SimpleNamespace as NS

import latched_plan as lp

CI = pathlib.Path(__file__).parent.parent / "ci"


def plan(n):
    return NS(poses=[object()] * n)


def test_durability_name():
    assert lp.durability_name(True) == "TRANSIENT_LOCAL"
    assert lp.durability_name(False) == "VOLATILE"


def test_latch_keeps_newest_usable_plan():
    latch = lp.PlanLatch()
    a, b = plan(5), plan(3)
    assert latch.update(a) and latch.latest is a
    assert latch.update(b) and latch.latest is b
    assert not latch.update(plan(0)) and latch.latest is b  # cleared plan at goal does not replace it
    assert not latch.update(plan(1)) and latch.latest is b
    assert latch.seen == 4


def test_latch_empty_until_first_plan():
    latch = lp.PlanLatch()
    assert not latch.update(plan(0))
    assert latch.latest is None


def test_sut_plan_option_defaults_off():
    src = (CI / "sut.py").read_text()
    ast.parse(src)
    assert '"plan_transient_local", False' in src
    assert "DurabilityPolicy.TRANSIENT_LOCAL if plan_latched" in src


def test_replay_once_latch_wiring():
    sh = (CI / "replay_once.sh").read_text()
    assert "LATCH_PLAN" in sh and "--remap /plan:=/plan_in" in sh and "plan_transient_local:=true" in sh
    ast.parse((CI / "latched_plan_node.py").read_text())
