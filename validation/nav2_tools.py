"""Pure-Python helpers for the nav2 replay loop (no ROS): parameter overlays, the TF filter rule, the map usability
check and the map cache key. The ROS side (ci/nav2_replay_nodes.py, ci/nav2_replay.launch.py) calls these."""
from __future__ import annotations

import argparse
import glob
import hashlib
import sys

import yaml


def apply_overlay(params: dict, overlay: dict) -> dict:
    """Return a copy of params with each dotted path in overlay set. A path must already exist: an overlay that
    names a parameter nav2 doesn't have is a typo, not a regression."""
    out = yaml.safe_load(yaml.safe_dump(params))
    for path, value in overlay.items():
        node, rest = out, path.split(".")
        while True:
            # parameter names themselves contain dots (DWB's "PathAlign.scale"), so match the longest key prefix
            for n in range(len(rest), 0, -1):
                key = ".".join(rest[:n])
                if isinstance(node, dict) and key in node:
                    break
            else:
                raise KeyError(f"overlay path not in params: {path}")
            if n == len(rest):
                node[key] = value
                break
            node, rest = node[key], rest[n:]
    return out


def keep_transform(parent: str, child: str, drop_children: set[str]) -> bool:
    """TF replay rule: drop transforms whose child frame is regenerated live (robot_state_publisher's links, the
    localisation's map->odom); everything else is replayed from the bag."""
    return child.lstrip("/") not in drop_children


def map_stats(pgm_path: str) -> dict:
    """Free / occupied / unknown cell counts of a nav2 map_saver .pgm (P5, trinary: 254 free, 0 occupied, 205 unknown)."""
    with open(pgm_path, "rb") as f:
        data = f.read()
    tokens, pos = [], 0
    while len(tokens) < 4:  # magic, width, height, maxval (comments start with #)
        while data[pos:pos + 1].isspace():
            pos += 1
        if data[pos:pos + 1] == b"#":
            pos = data.index(b"\n", pos)
            continue
        end = pos
        while not data[end:end + 1].isspace():
            end += 1
        tokens.append(data[pos:end])
        pos = end
    if tokens[0] != b"P5":
        raise ValueError(f"{pgm_path}: not a binary PGM")
    w, h = int(tokens[1]), int(tokens[2])
    px = data[pos + 1:pos + 1 + w * h]
    free = sum(1 for b in px if b >= 250)
    occ = sum(1 for b in px if b <= 5)
    return {"width": w, "height": h, "free": free, "occupied": occ, "unknown": len(px) - free - occ}


def map_usable(stats: dict, min_free: int = 2000, min_occupied: int = 200) -> tuple[bool, str]:
    """A map is usable when it has explored free space and walls: a window too short or featureless gives a mostly
    unknown map. 2000 free cells at 5 cm is 5 m^2."""
    ok = stats["free"] >= min_free and stats["occupied"] >= min_occupied
    return ok, (f"free {stats['free']} (min {min_free}), occupied {stats['occupied']} (min {min_occupied}), "
                f"unknown {stats['unknown']}")


def cache_key(recording_dir: str, slam_params: str) -> str:
    """Map cache key: sha256 of the recording's MCAP files and the SLAM parameters, so the map is rebuilt when either
    changes (keyed like the recording)."""
    h = hashlib.sha256()
    for path in sorted(glob.glob(recording_dir + "/*.mcap")) + [slam_params]:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    return "map-" + h.hexdigest()[:16]


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("overlay", help="write params.yaml with a named overlay applied (or unchanged without a name)")
    o.add_argument("--params", required=True)
    o.add_argument("--overlays", required=True)
    o.add_argument("--name", default="")
    o.add_argument("--out", required=True)
    m = sub.add_parser("check-map", help="exit 3 when the map is not usable")
    m.add_argument("pgm")
    k = sub.add_parser("cache-key")
    k.add_argument("recording_dir")
    k.add_argument("slam_params")
    a = ap.parse_args(argv)
    if a.cmd == "overlay":
        params = yaml.safe_load(open(a.params))
        if a.name:
            params = apply_overlay(params, yaml.safe_load(open(a.overlays))[a.name])
        with open(a.out, "w") as f:
            yaml.safe_dump(params, f)
    elif a.cmd == "check-map":
        ok, why = map_usable(map_stats(a.pgm))
        print(("usable map: " if ok else "UNUSABLE map: ") + why)
        return 0 if ok else 3
    else:
        print(cache_key(a.recording_dir, a.slam_params))
    return 0


if __name__ == "__main__":
    sys.exit(main())
