"""Prototype of the replaydiff compare step, for the validation experiment only.

Implements the parts of docs/design.md that the experiment exercises: per-topic message matching (nearest,
interpolate), per-field errors for Twist/TwistStamped and Odometry, the p95 stat, the noise floor from N base
runs, the INCONCLUSIVE / FAIL / PASS rule, the bias-window test and the message-count / rate check.
Not implemented: Path, JointState, TF, `sequence` matching, drift per metre, time-shift estimation.

Messages are duck-typed (attribute access), so unit tests use plain SimpleNamespace objects and need no ROS.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

DEFAULTS = {
    "match": "nearest",   # nearest | interpolate
    "max_dt": 0.02,       # s, nearest
    "max_gap": 0.2,       # s, interpolate: base samples further apart than this are not interpolated over
    "skip_first": 1.0,    # s
    "skip_last": 0.0,     # s
    "stat": "p95",        # p95 | max | mean
    "stamp": "auto",      # auto (header.stamp if set, else receive time) | header | receive
}
NOISE_FRACTION = 0.5      # noise > 0.5 * tolerance -> INCONCLUSIVE (design.md)
BIAS_SPREAD_FACTOR = 3.0  # bias must exceed 3x the base-vs-base window bias spread (design.md)
BIAS_MIN_SAMPLES = 5      # windows with fewer matched messages are ignored by the bias test
EXIT_CODES = {"PASS": 0, "FAIL": 1, "INCONCLUSIVE": 2}


# --------------------------------------------------------------------------- reading

@dataclass
class Series:
    """All messages of one topic in one run, sorted by receive time."""
    t_log: np.ndarray                    # receive (log) time, s
    t_hdr: np.ndarray                    # header.stamp, s; NaN where the message has none
    msgs: list = field(default_factory=list)
    _cache: dict = field(default_factory=dict, repr=False)

    def times(self, stamp: str) -> np.ndarray:
        if stamp == "receive":
            return self.t_log
        if stamp == "header":
            return self.t_hdr
        return self.t_hdr if len(self.t_hdr) and not np.isnan(self.t_hdr).any() else self.t_log


Run = dict  # topic -> Series


def _header_time(msg) -> float:
    stamp = getattr(getattr(msg, "header", None), "stamp", None)
    if stamp is None:
        return math.nan
    t = stamp.sec + stamp.nanosec * 1e-9
    return t if t > 0 else math.nan


def make_series(items) -> Series:
    """items: iterable of (log_time_seconds, msg)."""
    items = sorted(items, key=lambda x: x[0])
    return Series(
        t_log=np.array([t for t, _ in items], dtype=float),
        t_hdr=np.array([_header_time(m) for _, m in items], dtype=float),
        msgs=[m for _, m in items],
    )


def read_mcap(path: str, topics=None) -> Run:
    """Read a ROS 2 MCAP into a Run. Receive time is the log time: record with `--use-sim-time` when replaying
    with `--clock`, so it is sim time and comparable between runs."""
    from mcap.reader import make_reader
    from mcap_ros2.decoder import DecoderFactory

    items: dict[str, list] = {}
    with open(path, "rb") as f:
        reader = make_reader(f, decoder_factories=[DecoderFactory()])
        for _schema, channel, message, ros_msg in reader.iter_decoded_messages(topics=topics):
            items.setdefault(channel.topic, []).append((message.log_time * 1e-9, ros_msg))
    return {topic: make_series(v) for topic, v in items.items()}


# --------------------------------------------------------------------------- quantities

def twist_of(msg):
    """Twist from Twist, TwistStamped, or the twist part of Odometry."""
    if hasattr(msg, "linear"):
        return msg
    t = msg.twist
    return t.twist if hasattr(t, "twist") else t


def _dotted(obj, path: str):
    for part in path.split("."):
        obj = getattr(obj, part)
    return obj


def _vec(v):
    return [v.x, v.y, v.z]


def _quat(q):
    return [q.x, q.y, q.z, q.w]


@dataclass
class Quantity:
    name: str
    extract: Callable          # msg -> sequence of floats
    tol: float
    rel: float = 0.0
    kind: str = "lin"          # lin (vector, error = norm of difference) | quat (error = rotation angle, deg)
    bias: dict | None = None   # {window, abs}; only for scalar (single-component) quantities


def quantities_for(topic_cfg: dict, sample_msg) -> list[Quantity]:
    """Build the compared quantities of one topic from its config block."""
    out: list[Quantity] = []
    is_odom = hasattr(sample_msg, "pose") and hasattr(sample_msg.pose, "pose")
    bias = topic_cfg.get("bias")
    if is_odom:
        pose = topic_cfg.get("pose", {})
        tw = topic_cfg.get("twist", {})
        if "translation" in pose:
            out.append(Quantity("pose.translation", lambda m: _vec(m.pose.pose.position), pose["translation"]))
        if "rotation_deg" in pose:
            out.append(Quantity("pose.rotation_deg", lambda m: _quat(m.pose.pose.orientation),
                                pose["rotation_deg"], kind="quat"))
        if "linear" in tw:
            out.append(Quantity("twist.linear", lambda m: _vec(twist_of(m).linear), tw["linear"]))
        if "angular" in tw:
            out.append(Quantity("twist.angular", lambda m: _vec(twist_of(m).angular), tw["angular"]))
    else:
        for path, spec in topic_cfg.get("fields", {}).items():
            out.append(Quantity(path, lambda m, p=path: [_dotted(twist_of(m), p)], spec["abs"],
                                spec.get("rel", 0.0), bias=bias))
    return out


# --------------------------------------------------------------------------- matching and errors

def _values(series: Series, q: Quantity) -> np.ndarray:
    if q.name not in series._cache:
        series._cache[q.name] = np.array([q.extract(m) for m in series.msgs], dtype=float).reshape(len(series.msgs), -1)
    return series._cache[q.name]


def _slerp(q0: np.ndarray, q1: np.ndarray, w: np.ndarray) -> np.ndarray:
    q0 = q0 / np.linalg.norm(q0, axis=1, keepdims=True)
    q1 = q1 / np.linalg.norm(q1, axis=1, keepdims=True)
    dot = np.sum(q0 * q1, axis=1)
    q1 = np.where((dot < 0)[:, None], -q1, q1)
    dot = np.abs(dot)
    theta = np.arccos(np.clip(dot, -1.0, 1.0))
    sin = np.sin(theta)
    small = sin < 1e-8
    a = np.where(small, 1.0 - w, np.sin((1.0 - w) * theta) / np.where(small, 1.0, sin))
    b = np.where(small, w, np.sin(w * theta) / np.where(small, 1.0, sin))
    return a[:, None] * q0 + b[:, None] * q1


def _quat_angle_deg(qa: np.ndarray, qb: np.ndarray) -> np.ndarray:
    """Rotation angle of qa^-1 * qb. Uses the chord length, which stays accurate for tiny angles."""
    qa = qa / np.linalg.norm(qa, axis=1, keepdims=True)
    qb = qb / np.linalg.norm(qb, axis=1, keepdims=True)
    sign = np.where(np.sum(qa * qb, axis=1) < 0, -1.0, 1.0)
    chord = np.linalg.norm(qa - sign[:, None] * qb, axis=1)
    return np.degrees(4.0 * np.arcsin(np.clip(chord / 2.0, 0.0, 1.0)))


@dataclass
class Errors:
    t: np.ndarray                  # times of the matched compared messages
    err: np.ndarray                # per-message error (already net of the relative part)
    signed: np.ndarray | None      # compared-minus-reference, scalar quantities only
    n_window: int                  # compared messages inside the time window
    n_unmatched: int               # of those, with no reference within max_dt / max_gap


def pair_errors(ref: Series, cmp: Series, q: Quantity, cfg: dict, lo: float, hi: float) -> Errors:
    """Errors of `cmp` against `ref` for one quantity. Unmatched messages are counted, never filled in."""
    stamp = cfg["stamp"]
    ta, tb = ref.times(stamp), cmp.times(stamp)
    inwin = (tb >= lo) & (tb <= hi)
    tb_w = tb[inwin]
    vb = _values(cmp, q)[inwin]
    va = _values(ref, q)
    n_w = int(inwin.sum())
    empty = Errors(np.array([]), np.array([]), None, n_w, n_w)
    if n_w == 0 or len(ta) == 0:
        return empty

    if cfg["match"] == "nearest":
        j = np.clip(np.searchsorted(ta, tb_w), 1, len(ta) - 1) if len(ta) > 1 else np.zeros(n_w, dtype=int)
        if len(ta) > 1:
            left_closer = np.abs(tb_w - ta[j - 1]) <= np.abs(tb_w - ta[j])
            j = np.where(left_closer, j - 1, j)
        valid = np.abs(tb_w - ta[j]) <= cfg["max_dt"]
        pred = va[j]
        pred_q = va[j]
    elif cfg["match"] == "interpolate":
        if len(ta) < 2:
            return empty
        i = np.clip(np.searchsorted(ta, tb_w), 1, len(ta) - 1)
        span = ta[i] - ta[i - 1]
        valid = (tb_w >= ta[0]) & (tb_w <= ta[-1]) & (span <= cfg["max_gap"])
        w = np.where(span > 0, (tb_w - ta[i - 1]) / np.where(span > 0, span, 1.0), 0.0)
        pred = va[i - 1] * (1 - w[:, None]) + va[i] * w[:, None]
        pred_q = _slerp(va[i - 1], va[i], w) if q.kind == "quat" else pred
    else:
        raise ValueError(f"unsupported match mode: {cfg['match']}")

    if q.kind == "quat":
        err = _quat_angle_deg(pred_q, vb)
        signed = None
    else:
        d = vb - pred
        err = np.maximum(np.linalg.norm(d, axis=1) - q.rel * np.linalg.norm(pred, axis=1), 0.0)
        signed = d[:, 0] if d.shape[1] == 1 else None
    return Errors(tb_w[valid], err[valid], signed[valid] if signed is not None else None, n_w, int((~valid).sum()))


def stat_of(err: np.ndarray, stat: str) -> float:
    if len(err) == 0:
        return math.nan
    if stat == "p95":
        return float(np.percentile(err, 95))
    if stat == "max":
        return float(np.max(err))
    if stat == "mean":
        return float(np.mean(err))
    raise ValueError(f"unknown stat: {stat}")


def window_biases(e: Errors, lo: float, window: float) -> list[float]:
    """Mean signed error per time window (windows with too few samples are skipped)."""
    if e.signed is None or len(e.t) == 0:
        return []
    idx = np.floor((e.t - lo) / window).astype(int)
    out = []
    for k in np.unique(idx):
        sel = idx == k
        if sel.sum() >= BIAS_MIN_SAMPLES:
            out.append(float(e.signed[sel].mean()))
    return out


# --------------------------------------------------------------------------- verdicts

@dataclass
class QResult:
    topic: str
    quantity: str
    verdict: str                  # PASS | FAIL | INCONCLUSIVE
    tolerance: float | None
    noise: float | None           # base-vs-base stat (max over base pairs)
    head_error: float | None      # head-vs-base stat, smallest over base runs
    reasons: list = field(default_factory=list)
    unmatched: int = 0
    bias: float | None = None     # smallest over base runs of the largest |window bias|
    bias_spread: float | None = None

    def ratio(self) -> float:
        """How close the deciding number is to its limit, for picking a headline row."""
        if not self.tolerance:
            return 0.0
        if self.verdict == "INCONCLUSIVE" and self.noise is not None and not math.isnan(self.noise):
            return self.noise / (NOISE_FRACTION * self.tolerance)
        he = self.head_error
        return 0.0 if he is None or math.isnan(he) else he / self.tolerance


@dataclass
class Report:
    results: list[QResult]

    @property
    def verdict(self) -> str:
        vs = {r.verdict for r in self.results}
        if "FAIL" in vs:
            return "FAIL"
        if "INCONCLUSIVE" in vs or not vs:
            return "INCONCLUSIVE"
        return "PASS"

    @property
    def exit_code(self) -> int:
        return EXIT_CODES[self.verdict]

    def headline(self) -> QResult | None:
        """The row that decided the overall verdict (largest ratio among rows with that verdict)."""
        rows = [r for r in self.results if r.verdict == self.verdict]
        return max(rows, key=lambda r: r.ratio()) if rows else None

    def to_dict(self) -> dict:
        return {"verdict": self.verdict, "results": [r.__dict__ for r in self.results]}


def _nan_to_none(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else x


def evaluate(base_runs: list[Run], head: Run, config: dict) -> Report:
    """Verdict of `head` against N >= 2 base runs under the design.md rule. The tolerance is fixed; noise only
    decides whether a verdict is possible."""
    defaults = {**DEFAULTS, **config.get("defaults", {})}
    rate_rel = config.get("rate", {}).get("rel", 0.10)
    runs = list(base_runs) + [head]
    results: list[QResult] = []

    for topic, tcfg_raw in config["topics"].items():
        cfg = {**defaults, **{k: v for k, v in tcfg_raw.items() if k in DEFAULTS}}
        series = [r.get(topic) for r in runs]
        base_series, head_series = series[:-1], series[-1]
        # time window shared by every run, from the data of this topic in all runs
        all_t = [s.times(cfg["stamp"]) for s in series if s is not None and len(s.msgs)]
        sample_src = next((s for s in (head_series, *base_series) if s is not None and s.msgs), None)
        if sample_src is None:
            results.append(QResult(topic, "*", "INCONCLUSIVE", None, None, None, ["topic absent from every run"]))
            continue
        t0 = min(float(t.min()) for t in all_t)
        t1 = max(float(t.max()) for t in all_t)
        lo, hi = t0 + cfg["skip_first"], t1 - cfg["skip_last"]
        quantities = quantities_for(tcfg_raw, sample_src.msgs[0])

        head_missing = head_series is None or not head_series.msgs
        if head_missing:
            for q in quantities:
                results.append(QResult(topic, q.name, "FAIL", q.tol, None, None,
                                       ["topic missing from head run (not interpolated over)"]))
            results.append(QResult(topic, "rate", "FAIL", rate_rel, None, None, ["topic missing from head run"]))
            continue
        if any(s is None or not s.msgs for s in base_series):
            results.append(QResult(topic, "*", "INCONCLUSIVE", None, None, None,
                                   ["topic missing from at least one base run: replay is broken"]))
            continue

        def count(s: Series) -> int:
            t = s.times(cfg["stamp"])
            return int(((t >= lo) & (t <= hi)).sum())

        # message-count / rate check: FAIL if the head count differs by more than rate.rel from every base run
        nh = count(head_series)
        diffs = [abs(nh - count(s)) / max(count(s), 1) for s in base_series]
        rate_fail = min(diffs) > rate_rel
        results.append(QResult(topic, "rate", "FAIL" if rate_fail else "PASS", rate_rel, None, min(diffs),
                               [f"head published {nh} messages vs base {[count(s) for s in base_series]}"]
                               if rate_fail else []))

        pairs = list(itertools.combinations(range(len(base_series)), 2))
        for q in quantities:
            res = QResult(topic, q.name, "PASS", q.tol, None, None)
            # noise floor: base-vs-base, worst pair
            noise_stats, b2b_bias = [], []
            for i, j in pairs:
                e = pair_errors(base_series[i], base_series[j], q, cfg, lo, hi)
                noise_stats.append(stat_of(e.err, cfg["stat"]))
                if q.bias:
                    b2b_bias += window_biases(e, lo, q.bias.get("window", 2.0))
            noise = max(noise_stats) if noise_stats and not any(math.isnan(n) for n in noise_stats) else math.nan
            # head vs each base run
            head_stats, bias_max, unmatched = [], [], []
            for s in base_series:
                e = pair_errors(s, head_series, q, cfg, lo, hi)
                head_stats.append(stat_of(e.err, cfg["stat"]))
                unmatched.append(e.n_unmatched)
                if q.bias:
                    wb = window_biases(e, lo, q.bias.get("window", 2.0))
                    bias_max.append(max((abs(b) for b in wb), default=math.nan))
            valid_head = [h for h in head_stats if not math.isnan(h)]
            res.noise = _nan_to_none(noise)
            res.head_error = min(valid_head) if valid_head else None
            res.unmatched = min(unmatched)

            if not pairs or math.isnan(noise):
                res.verdict = "INCONCLUSIVE"
                res.reasons.append("noise floor unavailable (need >= 2 base runs with matched messages)")
            elif noise > NOISE_FRACTION * q.tol:
                res.verdict = "INCONCLUSIVE"
                res.reasons.append(f"noise {noise:.4g} > {NOISE_FRACTION} x tolerance {q.tol:g}: can't tell")
            elif not valid_head:
                res.verdict = "INCONCLUSIVE"
                res.reasons.append("no head message matched a base message")
            else:
                if res.head_error > q.tol:
                    res.verdict = "FAIL"
                    res.reasons.append(f"head {cfg['stat']} {res.head_error:.4g} > tolerance {q.tol:g} vs every base run")
                if q.bias and bias_max and not all(math.isnan(b) for b in bias_max):
                    best = min(b for b in bias_max if not math.isnan(b))
                    spread = float(np.sqrt(np.mean(np.square(b2b_bias)))) if b2b_bias else 0.0
                    res.bias, res.bias_spread = best, spread
                    if best > q.bias["abs"] and best > BIAS_SPREAD_FACTOR * spread:
                        res.verdict = "FAIL"
                        res.reasons.append(f"window bias {best:.4g} > {q.bias['abs']:g} and > "
                                           f"{BIAS_SPREAD_FACTOR:g}x base spread {spread:.3g}")
            results.append(res)
    return Report(results)


# --------------------------------------------------------------------------- CLI

def load_config(path: str) -> dict:
    import yaml
    with open(path) as f:
        return yaml.safe_load(f)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", required=True, help="YAML tolerance file")
    ap.add_argument("--base", nargs="+", required=True, help="N >= 2 base-run MCAPs (the noise floor)")
    ap.add_argument("--head", required=True, help="head-run MCAP")
    ap.add_argument("--json", help="write the report here")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    topics = list(cfg["topics"])
    report = evaluate([read_mcap(p, topics) for p in args.base], read_mcap(args.head, topics), cfg)
    for r in report.results:
        print(f"{r.verdict:13} {r.topic} {r.quantity}  noise={r.noise} head={r.head_error} tol={r.tolerance}  "
              + "; ".join(r.reasons))
    print(f"VERDICT {report.verdict}")
    if args.json:
        with open(args.json, "w") as f:
            json.dump(report.to_dict(), f, indent=2)
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
