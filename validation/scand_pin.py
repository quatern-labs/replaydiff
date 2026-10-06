"""Find the SCAND bag to pin (CI only, workflow scand-pin): list the Dataverse files of SCAND v5.2, take the smallest
Jackal bags, download each, print its sha256, its topics (name, type, count; never message contents) and the steadiest
driving window from its wheel odometry. The bag is deleted afterwards and never uploaded. Stdlib + rosbags + numpy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import urllib.request

import numpy as np

DATAVERSE = "https://dataverse.tdl.org"
DOI = "doi:10.18738/T8/0PRYRH"
VERSION = "5.2"


def jackal_bags(listing: dict) -> list[dict]:
    """Jackal .bag files of a Dataverse `versions/<v>/files` response, smallest first."""
    out = []
    for f in listing["data"]:
        df = f["dataFile"]
        text = " ".join(str(x) for x in (df.get("filename"), f.get("directoryLabel"), f.get("description"),
                                         f.get("categories"))).lower()
        if df["filename"].endswith(".bag") and "jackal" in text:
            out.append({"id": df["id"], "filename": df["filename"], "size": df["filesize"],
                        "checksum": df.get("checksum", {}), "description": f.get("description", ""),
                        "dir": f.get("directoryLabel", "")})
    return sorted(out, key=lambda b: b["size"])


def steady_window(t: np.ndarray, v: np.ndarray, length: float) -> dict | None:
    """Window of `length` s (start relative to t[0]) whose slowest 1 s mean speed is highest: steady driving, no stop."""
    if len(t) < 2 or t[-1] - t[0] < length:
        return None
    rel = t - t[0]
    bins = np.floor(rel).astype(int)
    means = np.array([np.abs(v[bins == k]).mean() if (bins == k).any() else 0.0 for k in range(bins[-1] + 1)])
    n = int(length)
    best = max(range(len(means) - n + 1), key=lambda s: means[s:s + n].min())
    w = means[best:best + n]
    return {"start": float(best), "duration": float(n), "min_speed": float(w.min()), "mean_speed": float(w.mean())}


def inspect_bag(path: str, length: float) -> dict:
    """Topic table and steady window of a ROS 1 bag; only odometry speeds are decoded."""
    from pathlib import Path

    from rosbags.highlevel import AnyReader

    with AnyReader([Path(path)]) as r:
        topics = {c.topic: {"type": c.msgtype, "count": c.msgcount} for c in r.connections}
        odom = [c for c in r.connections if c.msgtype == "nav_msgs/msg/Odometry"]
        odom = sorted(odom, key=lambda c: ("jackal" not in c.topic, c.topic))[:1]
        tv = [(t, r.deserialize(raw, c.msgtype).twist.twist.linear.x) for c, t, raw in r.messages(connections=odom)]
        duration, bag_start = (r.end_time - r.start_time) / 1e9, r.start_time / 1e9
    t = np.array([x[0] for x in tv], dtype=float) / 1e9
    win = steady_window(t, np.array([x[1] for x in tv]), length) if tv else None
    if win:
        win["start"] += float(t[0] - bag_start)  # relative to the bag start, as scand.py convert --start expects
    return {"duration": duration, "topics": topics, "odom_topic": odom[0].topic if odom else None, "window": win}


def _get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "replaydiff-validation (GitHub Actions)"})
    return urllib.request.urlopen(req, timeout=120)


def _hashes(path: str, algo: str) -> tuple[str, str]:
    h, extra = hashlib.sha256(), hashlib.new(algo.lower().replace("-", "")) if algo else None
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
            if extra:
                extra.update(chunk)
    return h.hexdigest(), extra.hexdigest() if extra else ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--top", type=int, default=3, help="how many of the smallest Jackal bags to download and inspect")
    ap.add_argument("--window", type=float, default=60.0, help="window length, s (30-90)")
    ap.add_argument("--workdir", default=".")
    ap.add_argument("--out", default="scand-pin.json")
    a = ap.parse_args(argv)
    url = f"{DATAVERSE}/api/datasets/:persistentId/versions/{VERSION}/files?persistentId={DOI}"
    listing = json.load(_get(url))
    bags = jackal_bags(listing)
    print(f"{len(listing['data'])} files in SCAND v{VERSION}, {len(bags)} Jackal bags (smallest first):")
    for b in bags:
        print(f"  id {b['id']}  {b['size']:>12} B  {b['filename']}  {b['dir']}  {b['description'][:80]}")
    for b in bags[:a.top]:
        path = os.path.join(a.workdir, f"scand-{b['id']}.bag")
        with _get(f"{DATAVERSE}/api/access/datafile/{b['id']}") as resp, open(path, "wb") as f:
            shutil.copyfileobj(resp, f, 1 << 22)
        try:
            b["sha256"], got = _hashes(path, b["checksum"].get("type", ""))
            b["dataverse_checksum_ok"] = got == b["checksum"].get("value") if got else None
            b.update(inspect_bag(path, a.window))
        finally:
            os.remove(path)  # never kept, never uploaded
        print(json.dumps(b, indent=2))
    with open(a.out, "w") as f:
        json.dump({"doi": DOI, "version": VERSION, "jackal_bags": bags}, f, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
