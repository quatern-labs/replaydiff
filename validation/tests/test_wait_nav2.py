"""The nav2 wait bound (validation/ci/wait_nav2.sh), proven with stub processes; needs coreutils `timeout`."""
import multiprocessing
import os
import shutil
import subprocess
from pathlib import Path

import pytest


def _burn(deadline):
    import time

    while time.monotonic() < deadline:
        pass

SCRIPT = Path(__file__).resolve().parents[1] / "ci" / "test_wait_nav2.sh"


@pytest.mark.skipif(shutil.which("timeout") is None, reason="coreutils `timeout` not on PATH (e.g. macOS)")
@pytest.mark.skipif(shutil.which("pgrep") is None, reason="pgrep not on PATH")
def test_wait_bound_holds_with_sigterm_ignoring_ros2():
    r = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.fixture
def cpu_load():
    """One busy worker per core, each with a hard deadline; terminated then killed on exit."""
    import time

    deadline = time.monotonic() + 900
    procs = [multiprocessing.Process(target=_burn, args=(deadline,), daemon=True) for _ in range(os.cpu_count() or 1)]
    try:
        for p in procs:
            p.start()
        yield
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            p.join(5)
            if p.is_alive():
                p.kill()
                p.join(5)


@pytest.mark.skipif(os.environ.get("RD_LOAD_RUNS") != "1", reason="slow (~8 min); set RD_LOAD_RUNS=1")
@pytest.mark.skipif(shutil.which("timeout") is None, reason="coreutils `timeout` not on PATH")
@pytest.mark.skipif(shutil.which("pgrep") is None, reason="pgrep not on PATH")
def test_wait_bound_holds_20_runs_under_cpu_load(cpu_load):
    for i in range(20):
        r = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, timeout=180)
        assert r.returncode == 0, f"run {i}: " + r.stdout + r.stderr
