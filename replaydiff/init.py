"""`replaydiff init`: write a starter tolerance file from the topics and types of a recording."""
import argparse
import math
import sys

from .compare import NOISE_FRACTION, evaluate, expand_tf, read_mcap

SUPPORTED = {
    "geometry_msgs/msg/Twist": "twist", "geometry_msgs/msg/TwistStamped": "twist",
    "nav_msgs/msg/Odometry": "odom", "nav_msgs/msg/Path": "path",
    "sensor_msgs/msg/JointState": "joint", "tf2_msgs/msg/TFMessage": "tf",
}


class T(float):
    """A tolerance taken from the measured noise floor."""
    measured = True


def topics_and_types(path: str) -> dict:
    """topic -> message type, from the MCAP summary."""
    from mcap.reader import make_reader
    with open(path, "rb") as f:
        summary = make_reader(f).get_summary()
    if summary is None:
        raise ValueError(f"{path}: no summary section (is it a complete MCAP?)")
    return {c.topic: summary.schemas[c.schema_id].name for c in summary.channels.values()}


def tf_edges(path: str, topic: str) -> list:
    """Distinct (parent, child) pairs seen on a TFMessage topic, in order of first appearance."""
    edges: dict = {}
    for msg in read_mcap(path, [topic]).get(topic, ()).msgs:
        for tr in msg.transforms:
            edges[(tr.header.frame_id, tr.child_frame_id)] = None
    return list(edges)


def round_up(x: float) -> float:
    """Round up to one significant digit."""
    e = 10.0 ** math.floor(math.log10(x))
    return float(f"{math.ceil(round(x / e, 9)) * e:.6g}")


def build_spec(found: dict, edges: dict, tol) -> dict:
    """Config dict for the supported topics. `tol(topic, quantity, default)` gives each tolerance."""
    topics = {}
    for topic, typ in found.items():
        kind = SUPPORTED.get(typ)
        if kind == "twist":
            topics[topic] = {
                "fields": {"linear.x": {"abs": tol(topic, "linear.x", 0.01)},
                           "angular.z": {"abs": tol(topic, "angular.z", 0.03)}},
                "bias": {"window": 2.0, "abs": 0.005}}
        elif kind == "odom":
            topics[topic] = {
                "match": "interpolate", "max_gap": 0.2,
                "pose": {"translation": tol(topic, "pose.translation", 0.01),
                         "rotation_deg": tol(topic, "pose.rotation_deg", 1.0)},
                "twist": {"linear": tol(topic, "twist.linear", 0.02), "angular": tol(topic, "twist.angular", 0.03)}}
        elif kind == "path":
            topics[topic] = {"path": {k: tol(topic, f"path.{k}", 0.05) for k in ("mean_dist", "hausdorff", "endpoint")}}
        elif kind == "joint":
            topics[topic] = {"joints": {"*": {f: tol(topic, f"*.{f}", d) for f, d in (("position", 0.01), ("velocity", 0.05))}}}
        elif kind == "tf" and edges.get(topic):
            topics[topic] = {"match": "interpolate", "max_gap": 0.2, "pairs": [
                {"parent": p, "child": c,
                 "translation": tol(f"{topic} {p}->{c}", "pose.translation", 0.01),
                 "rotation_deg": tol(f"{topic} {p}->{c}", "pose.rotation_deg", 1.0)} for p, c in edges[topic]]}
    return {"version": 1, "defaults": {"match": "nearest", "max_dt": 0.02, "skip_first": 1.0, "stat": "p95"},
            "rate": {"rel": 0.10}, "topics": topics}


def measure(spec: dict, base_paths: list, edges: dict) -> dict:
    """Noise floor per (topic, quantity) over the base runs; joint wildcards take the worst joint."""
    runs, cfg = expand_tf([read_mcap(p, list(spec["topics"])) for p in base_paths], spec)
    noise: dict = {}
    for r in evaluate(runs, runs[-1], cfg).results:
        if r.noise is None or math.isnan(r.noise):
            continue
        key = (r.topic, "*." + r.quantity.rsplit(".", 1)[1] if r.quantity.endswith((".position", ".velocity")) else r.quantity)
        noise[key] = max(noise.get(key, 0.0), r.noise)
    return noise


def _flat(v) -> bool:
    return not isinstance(v, (dict, list)) or (isinstance(v, dict) and all(not isinstance(x, (dict, list)) for x in v.values()))


def _scalar(v) -> str:
    return f"{v:g}" if isinstance(v, float) else str(v)


def _flow(d: dict) -> str:
    return "{" + ", ".join(f"{k}: {_scalar(v)}" for k, v in d.items()) + "}"


def _note(*vals) -> str:
    return "   # measured, review" if any(getattr(v, "measured", False) for v in vals) else ""


def emit(d: dict, indent: int = 0) -> list:
    pad, out = "  " * indent, []
    for k, v in d.items():
        key = f'"{k}"' if k == "*" else k
        if isinstance(v, list):
            out.append(f"{pad}{key}:")
            out += [f"{pad}  - {_flow(i)}{_note(*i.values())}" for i in v]
        elif isinstance(v, dict) and _flat(v):
            out.append(f"{pad}{key}: {_flow(v)}{_note(*v.values())}")
        elif isinstance(v, dict) and indent > 0 and len(v) == 1 and _flat(next(iter(v.values()))) :
            (ik, iv), = v.items()
            out.append(f"{pad}{key}:")
            out.append(f"{pad}  {'\"*\"' if ik == '*' else ik}: {_flow(iv)}{_note(*iv.values())}")
        elif isinstance(v, dict):
            out.append(f"{pad}{key}:")
            out += emit(v, indent + 1)
        else:
            out.append(f"{pad}{key}: {_scalar(v)}")
    return out


def render(found: dict, spec: dict, measured: bool, recording: str) -> str:
    skipped = [f"#   {t} ({typ})" for t, typ in found.items() if typ not in SUPPORTED]
    head = ["# Starter tolerances written by `replaydiff init` from " + recording + ".",
            "# Fixed limits: noise never widens them (docs/design.md). Review every value before use."]
    head.append("# Values marked `# measured, review` are the base-run noise floor divided by "
                f"{NOISE_FRACTION:g} (the point where compare says INCONCLUSIVE), rounded up." if measured else
                "# No base runs were given: values are generic starting points. Pass --base <mcap>... to measure them.")
    if skipped:
        head += ["# Topics with no comparator yet, not listed:"] + skipped
    return "\n".join(head + emit(spec)) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="replaydiff init", description="Write a starter tolerance file from a recording.")
    ap.add_argument("--recording", required=True, help="MCAP to read the topics and types from")
    ap.add_argument("--base", nargs="+", help="N >= 2 base-run MCAPs: measure the tolerances from their noise floor")
    ap.add_argument("--out", default="replaydiff.yaml", help="file to write (default: replaydiff.yaml)")
    ap.add_argument("--force", action="store_true", help="overwrite an existing file")
    args = ap.parse_args(argv)
    try:
        import os
        if os.path.exists(args.out) and not args.force:
            raise FileExistsError(f"{args.out} exists (use --force to overwrite)")
        if args.base is not None and len(args.base) < 2:
            raise ValueError("need at least 2 --base runs to measure a noise floor")
        found = topics_and_types(args.recording)
        edges = {t: tf_edges(args.recording, t) for t, typ in found.items() if SUPPORTED.get(typ) == "tf"}
        spec = build_spec(found, edges, lambda topic, q, default: default)
        if not spec["topics"]:
            raise ValueError("no topic of a supported type (Twist, Odometry, Path, JointState, TFMessage) in the recording")
        noise = measure(spec, args.base, edges) if args.base else {}
        spec = build_spec(found, edges, lambda topic, q, default: (
            T(round_up(noise[topic, q] / NOISE_FRACTION)) if noise.get((topic, q)) else default))
        text = render(found, spec, bool(args.base), os.path.basename(args.recording))
        with open(args.out, "w") as f:
            f.write(text)
    except Exception as e:
        print(f"replaydiff: error: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    print(f"wrote {args.out}: {len(spec['topics'])} topics")
    return 0


if __name__ == "__main__":
    sys.exit(main())
