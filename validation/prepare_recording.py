"""prepare-recording for the validation experiment's real-robot recording: verify a ROS 1 bag against its pinned
sha256, convert it (scand.py), derive /scan from the point cloud, check the result and cache it by file id + sha256.

Source-agnostic: it starts from a bag already on disk. How the bag gets there (download) is not part of this module.
Stdlib only; the convert and laser-scan steps are passed in, so the unit tests need no ROS and no rosbags.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Callable

CACHE_MARKER = "prepared.json"


class Sha256Mismatch(ValueError):
    pass


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_sha256(path: str | Path, expected: str) -> str:
    """Return the file's sha256 if it equals expected (case-insensitive), else raise Sha256Mismatch."""
    got = sha256_file(path)
    if got != expected.strip().lower():
        raise Sha256Mismatch(f"{path}: sha256 {got} != pinned {expected}")
    return got


def cache_key(file_id: str | int, sha256: str, window: tuple[float, float] | None = None) -> str:
    """Key for actions/cache: changes with the file id, the pinned hash or the trim window (each changes the output)."""
    key = f"scand-{file_id}-{sha256.strip().lower()[:16]}"
    if window is not None:
        key += f"-s{window[0]:g}-d{window[1]:g}"
    return key


def laserscan_commands(cloud_bag: str, out_bag: str, target_frame: str = "base_link") -> list[list[str]]:
    """The ros2 commands (run in the CI ROS container) that turn the cloud in the intermediate bag into /scan:
    node in the background, play the bag with sim-time-free clocking, record /scan. Run by run_laserscan()."""
    return [
        ["ros2", "run", "pointcloud_to_laserscan", "pointcloud_to_laserscan_node", "--ros-args",
         "-r", "cloud_in:=/velodyne_points", "-r", "scan:=/scan", "-p", f"target_frame:={target_frame}"],
        ["ros2", "bag", "record", "-s", "mcap", "-o", out_bag, "/scan"],
        ["ros2", "bag", "play", cloud_bag],
    ]


def prepare(bag: str, sha256: str, file_id: str | int, out_dir: str | Path, cache_dir: str | Path,
            window: tuple[float, float], convert: Callable, laserscan: Callable, check: Callable) -> dict:
    """verify -> (cache hit: copy) | convert + laserscan + check -> store in cache. Returns {"key", "cached", "topics"}.
    convert(bag, dst, start, duration, keep_cloud) writes the rosbag2 dir; laserscan(cloud_dir, out_dir) adds /scan to
    the uploaded recording and must leave no cloud topic in it; check(path) returns the topic list or raises."""
    verify_sha256(bag, sha256)
    key = cache_key(file_id, sha256, window)
    out, hit = Path(out_dir), Path(cache_dir) / key
    if (hit / CACHE_MARKER).is_file():
        shutil.copytree(hit / "recording", out, dirs_exist_ok=True)
        topics = check(str(out))  # a cache entry is re-checked, never trusted
        return {"key": key, "cached": True, "topics": topics}
    work = out.parent / (out.name + ".work")
    shutil.rmtree(work, ignore_errors=True)
    try:
        convert(bag, str(work / "cloud"), window[0], window[1], True)
        laserscan(str(work / "cloud"), str(out))
        topics = check(str(out))
    finally:
        shutil.rmtree(work, ignore_errors=True)  # the intermediate bag holds the raw cloud: never kept
    shutil.copytree(out, hit / "recording", dirs_exist_ok=True)
    (hit / CACHE_MARKER).write_text(json.dumps({"key": key, "sha256": sha256, "file_id": str(file_id),
                                                "topics": topics}, indent=2))
    return {"key": key, "cached": False, "topics": topics}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("key", help="print the cache key")
    p.add_argument("--file-id", required=True)
    p.add_argument("--sha256", required=True)
    p.add_argument("--start", type=float)
    p.add_argument("--duration", type=float)
    p = sub.add_parser("verify", help="exit 1 unless the file matches the pinned sha256")
    p.add_argument("path")
    p.add_argument("sha256")
    a = ap.parse_args(argv)
    if a.cmd == "key":
        win = (a.start, a.duration) if a.start is not None and a.duration is not None else None
        print(cache_key(a.file_id, a.sha256, win))
        return 0
    try:
        print(verify_sha256(a.path, a.sha256))
    except Sha256Mismatch as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
