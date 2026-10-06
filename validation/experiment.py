"""Turns replayed runs into the experiment's results: verdicts for base-vs-base and for each injected regression,
catch / INCONCLUSIVE / false-FAIL rates, and the results/validation.{json,md} files. Pure Python, no ROS."""
from __future__ import annotations

import argparse
import glob
import json
import os
import math
import sys
from collections import Counter, defaultdict

import compare_proto as cp

N_VALUES = (3, 5)
N_BASE_RUNS = 6  # base0..base5: N=3 judges base3..base5 as "head", N=5 judges base5 (never a run that is in the base set)


# Injected regressions: nominal size as a multiple of the tolerance of the quantity they act on (validation/README.md).
# gain: linear.x tolerance 0.01 m/s = 5% of the 0.2 m/s cruise; offset: translation tolerance 0.01 m.
SIZES = {"gain_x0.5": 0.5, "gain_x0.75": 0.75, "gain_x1.0": 1.0, "gain_x1.5": 1.5, "gain10": 2.0, "gain30": 6.0,
         "offset_x0.5": 0.5, "offset_x0.75": 0.75, "offset_x1.0": 1.0, "offset_x1.5": 1.5, "offset2cm": 2.0}
TARGET = {"gain": "linear.x", "offset": "pose.translation"}  # family -> the quantity it changes
ABOUT_1X = (0.9, 1.1)  # measured effect in this band counts as "about 1x": any verdict is acceptable


def family_of(name: str | None) -> str | None:
    return next((f for f in TARGET if name and name.startswith(f)), None)


def checks_fired(report: cp.Report) -> list[str]:
    """Which checks made the verdict FAIL: p95 (head stat > tolerance), bias (window bias), count (message count /
    rate), missing (topic absent from the head run)."""
    out = set()
    for r in report.results:
        if r.verdict != "FAIL":
            continue
        why = " ".join(r.reasons)
        if "missing" in why:
            out.add("missing")
        elif r.quantity == "rate":
            out.add("count")
        if "> tolerance" in why:
            out.add("p95")
        if "window bias" in why:
            out.add("bias")
    return sorted(out)


def effect_of(report: cp.Report, regression: str | None) -> float | None:
    """Measured effect size: head-vs-base p95 / tolerance of the quantity the regression acts on. The gain only
    scales the speed where the controller commands one, so this can be smaller than the nominal size."""
    q = TARGET.get(family_of(regression))
    rows = [r for r in report.results if r.quantity == q and r.head_error is not None and r.tolerance]
    return max((r.head_error / r.tolerance for r in rows), default=None)


def judge(kind: str, family: str | None, verdict: str, effect: float | None, checks: list[str]) -> tuple[str, str]:
    """(expected answer, outcome) of one verdict, judged on the measured effect. Outcomes: correct; bias (a FAIL
    below 1x fired only by the bias-window check: the bias check doing its job); acceptable (about 1x: any answer);
    inconclusive; false_fail (a FAIL where no check was due); miss (PASS above 1x)."""
    if kind == "base_vs_base":
        expected = "PASS"
    elif effect is None:  # a dropped topic (control) has no p95 to measure
        expected = "FAIL" if family is None else "any"
    elif effect < ABOUT_1X[0]:
        expected = "PASS (bias FAIL ok)"
    elif effect <= ABOUT_1X[1]:
        expected = "any"
    else:
        expected = "FAIL / INCONCLUSIVE"
    if verdict == "INCONCLUSIVE":
        return expected, "inconclusive"
    if expected == "any":
        return expected, "acceptable"
    if verdict == "PASS":
        return expected, "correct" if expected.startswith("PASS") else "miss"
    if expected.startswith("PASS"):
        return expected, "bias" if kind == "regression" and checks == ["bias"] else "false_fail"
    return expected, "correct"


def _record(meta: dict, n: int, kind: str, regression: str | None, head: str, report: cp.Report) -> dict:
    h = report.headline()
    effect, checks = effect_of(report, regression), checks_fired(report)
    expected, outcome = judge(kind, family_of(regression), report.verdict, effect, checks)
    return {
        **meta, "n": n, "kind": kind, "regression": regression, "head": head,
        "family": family_of(regression), "nominal": SIZES.get(regression), "effect": effect,
        "checks": checks, "expected": expected, "outcome": outcome,
        "verdict": report.verdict,
        "quantity": f"{h.topic} {h.quantity}" if h else None,
        "noise": h.noise if h else None,
        "head_error": h.head_error if h else None,
        "tolerance": h.tolerance if h else None,
        "reasons": h.reasons if h else [],
        "inconclusive_quantities": [f"{r.topic} {r.quantity}" for r in report.results if r.verdict == "INCONCLUSIVE"],
    }


def analyze_rep(runs: dict[str, cp.Run], config: dict, meta: dict) -> list[dict]:
    """runs: base0..base{K-1} plus any number of regression runs (other names). Returns one record per verdict."""
    base_names = sorted(k for k in runs if k.startswith("base"))
    reg_names = sorted(k for k in runs if not k.startswith("base"))
    out = []
    for n in N_VALUES:
        if len(base_names) <= n:
            continue
        base = [runs[k] for k in base_names[:n]]
        for h in base_names[n:] if n == min(N_VALUES) else base_names[-1:]:
            out.append(_record(meta, n, "base_vs_base", None, h, cp.evaluate(base, runs[h], config)))
        for r in reg_names:
            out.append(_record(meta, n, "regression", r, r, cp.evaluate(base, runs[r], config)))
    return out


def summarize(records: list[dict]) -> dict:
    """Rates per (distro, rate, n) and overall."""
    def rates(rows):
        b = [r for r in rows if r["kind"] == "base_vs_base"]
        g = [r for r in rows if r["kind"] == "regression"]
        cnt = lambda rs, v: sum(1 for r in rs if r["verdict"] == v)
        frac = lambda a, tot: (a / tot) if tot else None
        per_reg = {}
        for name in sorted({r["regression"] for r in g}):
            rr = [r for r in g if r["regression"] == name]
            per_reg[name] = {"total": len(rr), "caught": cnt(rr, "FAIL"), "inconclusive": cnt(rr, "INCONCLUSIVE"),
                             "missed": cnt(rr, "PASS"), "catch_rate": frac(cnt(rr, "FAIL"), len(rr))}
        return {
            "base_vs_base": {"total": len(b), "pass": cnt(b, "PASS"), "inconclusive": cnt(b, "INCONCLUSIVE"),
                             "false_fail": cnt(b, "FAIL"), "inconclusive_rate": frac(cnt(b, "INCONCLUSIVE"), len(b)),
                             "false_fail_rate": frac(cnt(b, "FAIL"), len(b))},
            "regressions": {"total": len(g), "inconclusive_rate": frac(cnt(g, "INCONCLUSIVE"), len(g)),
                            "missed": cnt(g, "PASS")},
            "per_regression": per_reg,
        }

    groups = defaultdict(list)
    for r in records:
        groups[(r["distro"], r["rate"], r["n"])].append(r)
    by_config = [{"distro": d, "rate": rt, "n": n, **rates(rows)} for (d, rt, n), rows in sorted(groups.items())]
    overall = rates(records)
    overall["success"] = (overall["base_vs_base"]["false_fail"] == 0 and overall["regressions"]["missed"] == 0
                          and overall["regressions"]["total"] > 0)
    return {"overall": overall, "by_config": by_config, "curve": curve(records)}


def curve(records: list[dict]) -> list[dict]:
    """Detection curve: one row per recording, distro, regression (base-vs-base as size 0), rate and N, with the
    measured effect, verdict counts, which checks fired and the outcome rates (judge())."""
    groups = defaultdict(list)
    for r in records:
        name = r["regression"] or "base"
        groups[(r.get("recording", "sim"), r["distro"], r.get("family") or ("base" if name == "base" else name),
                SIZES.get(name, 0.0 if name == "base" else math.inf), name, r["rate"], r["n"])].append(r)
    out = []
    for (rec, distro, _f, nominal, name, rate, n), rows in sorted(groups.items()):
        eff = sorted(r["effect"] for r in rows if r.get("effect") is not None)
        oc = Counter(r.get("outcome") for r in rows)
        checks = Counter(c for r in rows for c in r.get("checks", []))
        tot = len(rows)
        out.append({
            "recording": rec, "distro": distro, "regression": name, "nominal": None if math.isinf(nominal) else nominal,
            "rate": rate, "n": n, "total": tot,
            "effect_median": eff[len(eff) // 2] if eff else None, "effect_min": eff[0] if eff else None,
            "effect_max": eff[-1] if eff else None,
            "verdicts": {v: sum(1 for r in rows if r["verdict"] == v) for v in ("PASS", "FAIL", "INCONCLUSIVE")},
            "checks": dict(sorted(checks.items())), "expected": sorted({r.get("expected") for r in rows}),
            "outcomes": dict(sorted(oc.items())), "false_fail_rate": oc["false_fail"] / tot,
            "miss_rate": oc["miss"] / tot, "inconclusive_rate": oc["inconclusive"] / tot,
        })
    return out


def _pct(x):
    return "n/a" if x is None else f"{100 * x:.0f}%"


def _num(x):
    return "-" if x is None else f"{x:.4g}"


def render_md(doc: dict) -> str:
    s = doc["summary"]
    o = s["overall"]
    lines = ["# replaydiff validation results", "",
             f"Wall time (replays + analysis, summed over jobs): {doc.get('wall_seconds', 0) / 60:.1f} min. "
             f"Repetitions per configuration: {doc.get('reps', {})}.", "",
             "## Overall", "",
             f"- Base-vs-base: {o['base_vs_base']['total']} verdicts, false-FAIL rate {_pct(o['base_vs_base']['false_fail_rate'])}, "
             f"INCONCLUSIVE rate {_pct(o['base_vs_base']['inconclusive_rate'])}",
             f"- Regression runs: {o['regressions']['total']} verdicts, INCONCLUSIVE rate {_pct(o['regressions']['inconclusive_rate'])}, "
             f"missed (PASS) {o['regressions']['missed']}",
             f"- Success criteria met (every regression caught or INCONCLUSIVE, zero false FAIL): **{'yes' if o['success'] else 'no'}**",
             "", "## Per configuration (distro, playback rate, N)", "",
             "| distro | rate | N | b-v-b n | b-v-b INCONCLUSIVE | false FAIL | regression | caught | INCONCLUSIVE | missed | catch rate |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for c in s["by_config"]:
        b = c["base_vs_base"]
        for name, g in c["per_regression"].items():
            lines.append(f"| {c['distro']} | {c['rate']}x | {c['n']} | {b['total']} | {_pct(b['inconclusive_rate'])} | "
                         f"{b['false_fail']} | {name} | {g['caught']}/{g['total']} | {g['inconclusive']} | {g['missed']} | {_pct(g['catch_rate'])} |")
    lines += ["", "## Detection curve (regression size relative to the tolerance)", "",
              "Measured effect = head-vs-base p95 / tolerance of the quantity the regression acts on (median, "
              "min-max over runs); verdicts are judged on it. Below 1x a PASS is correct and a FAIL fired only by the "
              "bias-window check is the bias check doing its job; about 1x "
              f"({ABOUT_1X[0]:g}-{ABOUT_1X[1]:g}) any answer is acceptable; above 1x a PASS is a miss. "
              "Checks: p95, bias (window bias), count (message count), missing (topic absent).", "",
              "| recording | distro | regression | nominal | rate | N | measured effect | PASS | FAIL | INCONCL. | checks fired | correct answer | false FAIL | miss | INCONCLUSIVE |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for c in s.get("curve", []):
        v = c["verdicts"]
        eff = "-" if c["effect_median"] is None else f"{c['effect_median']:.2f} ({c['effect_min']:.2f}-{c['effect_max']:.2f})"
        checks = ", ".join(f"{k} {n}" for k, n in c["checks"].items()) or "-"
        lines.append(f"| {c['recording']} | {c['distro']} | {c['regression']} | {'control' if c['nominal'] is None else format(c['nominal'], 'g') + 'x'} | {c['rate']}x | "
                     f"{c['n']} | {eff} | {v['PASS']} | {v['FAIL']} | {v['INCONCLUSIVE']} | {checks} | "
                     f"{' / '.join(c['expected'])} | {_pct(c['false_fail_rate'])} | {_pct(c['miss_rate'])} | "
                     f"{_pct(c['inconclusive_rate'])} |")
    lines += ["", "## Every verdict", "",
              "| recording | distro | rate | rep | N | kind | regression / head | verdict | checks fired | measured effect | outcome | deciding quantity | noise floor | head error | tolerance |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in doc["records"]:
        lines.append(f"| {r.get('recording', 'sim')} | {r['distro']} | {r['rate']}x | {r['rep']} | {r['n']} | {r['kind']} | "
                     f"{r['regression'] or r['head']} | {r['verdict']} | {', '.join(r.get('checks', [])) or '-'} | "
                     f"{_num(r.get('effect'))} | {r.get('outcome', '-')} | {r['quantity'] or '-'} | {_num(r['noise'])} | "
                     f"{_num(r['head_error'])} | {_num(r['tolerance'])} |")
    return "\n".join(lines) + "\n"


def aggregate(records: list[dict], wall_seconds: float = 0.0) -> dict:
    reps = defaultdict(set)
    for r in records:
        reps[f"{r['distro']} {r['rate']}x"].add(r["rep"])
    return {"summary": summarize(records), "wall_seconds": wall_seconds,
            "reps": {k: len(v) for k, v in sorted(reps.items())}, "records": records}


# --------------------------------------------------------------------------- CLI

def _find_mcap(d: str) -> str | None:
    found = glob.glob(os.path.join(d, "**", "*.mcap"), recursive=True)
    return found[0] if found else None


def cmd_analyze(a) -> int:
    config = cp.load_config(a.config)
    topics = list(config["topics"])
    records = []
    for rep_dir in sorted(glob.glob(os.path.join(a.runs_dir, "rep*"))):
        rep = int(os.path.basename(rep_dir)[3:])
        runs = {}
        for d in sorted(os.listdir(rep_dir)):
            p = _find_mcap(os.path.join(rep_dir, d))
            if p:  # a run whose recording is missing is skipped; base runs missing -> fewer verdicts, visible in counts
                runs[d] = cp.read_mcap(p, topics)
        records += analyze_rep(runs, config, {"distro": a.distro, "rate": a.rate, "rep": rep, "set": a.set,
                                              "recording": a.recording})
    wall = 0.0
    wf = os.path.join(a.runs_dir, "wall_seconds.txt")
    if os.path.exists(wf):
        wall = float(open(wf).read().strip() or 0)
    with open(a.out, "w") as f:
        json.dump({"records": records, "wall_seconds": wall}, f, indent=2)
    print(f"{len(records)} verdicts -> {a.out}")
    return 0


def cmd_aggregate(a) -> int:
    records, wall = [], 0.0
    for p in sorted(a.inputs):
        d = json.load(open(p))
        records += d["records"]
        wall += d.get("wall_seconds", 0.0)
    doc = aggregate(records, wall)
    os.makedirs(a.out_dir, exist_ok=True)
    with open(os.path.join(a.out_dir, "validation.json"), "w") as f:
        json.dump(doc, f, indent=2)
    with open(os.path.join(a.out_dir, "validation.md"), "w") as f:
        f.write(render_md(doc))
    print(render_md(doc))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("analyze")
    p.add_argument("--runs-dir", required=True, help="dir with rep*/<run>/ recordings and wall_seconds.txt")
    p.add_argument("--distro", required=True)
    p.add_argument("--rate", type=float, required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--set", default="controls", help="regression set of the job (controls | near)")
    p.add_argument("--recording", default="sim", help="which input recording the runs replayed")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_analyze)
    p = sub.add_parser("aggregate")
    p.add_argument("--inputs", nargs="+", required=True)
    p.add_argument("--out-dir", default="results")
    p.set_defaults(fn=cmd_aggregate)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
