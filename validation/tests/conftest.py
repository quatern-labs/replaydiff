"""CI guard: with REPLAYDIFF_REQUIRE_ROSBAGS=1 the rosbags tests may not skip, so a missing extra fails the run."""
import os

import pytest


def pytest_sessionstart(session):
    if os.environ.get("REPLAYDIFF_REQUIRE_ROSBAGS") != "1":
        return
    try:
        import rosbags  # noqa: F401
    except ImportError as e:
        pytest.exit(
            f"REPLAYDIFF_REQUIRE_ROSBAGS=1 but rosbags is not importable ({e}); "
            'install the extra: pip install -e ".[validation]"',
            returncode=1,
        )
