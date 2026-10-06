"""The nav2 wait bound (validation/ci/wait_nav2.sh), proven with stub processes; needs coreutils `timeout`."""
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "ci" / "test_wait_nav2.sh"


@pytest.mark.skipif(shutil.which("timeout") is None, reason="coreutils `timeout` not on PATH (e.g. macOS)")
@pytest.mark.skipif(shutil.which("pgrep") is None, reason="pgrep not on PATH")
def test_wait_bound_holds_with_sigterm_ignoring_ros2():
    r = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
