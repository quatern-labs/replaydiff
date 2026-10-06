"""Turns replayed runs into the experiment's results: verdicts for base-vs-base and for each injected regression,
catch / INCONCLUSIVE / false-FAIL rates, and the results/validation.{json,md} files. Pure Python, no ROS."""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import defaultdict

import compare_proto as cp

N_VALUES = (3, 5)
N_BASE_RUNS = 6  # base0..base5: N=3 judges base3..base5 as "head", N=5 judges base5 (never a run that is in the base set)


def _record(meta: dict, n: int, kind: str, regression: str | None, head: str, report: cp.Report) -> dict:
    h = report.headline()
    return {
        **meta, "n": n, "kind": kind, "regression": regression, "head": head,
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
    return {"overall": overall, "by_config": by_config}


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
    lines += ["", "## Every verdict", "",
              "| distro | rate | rep | N | kind | regression / head | verdict | deciding quantity | noise floor | head error | tolerance |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in doc["records"]:
        lines.append(f"| {r['distro']} | {r['rate']}x | {r['rep']} | {r['n']} | {r['kind']} | {r['regression'] or r['head']} | "
                     f"{r['verdict']} | {r['quantity'] or '-'} | {_num(r['noise'])} | {_num(r['head_error'])} | {_num(r['tolerance'])} |")
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
        records += analyze_rep(runs, config, {"distro": a.distro, "rate": a.rate, "rep": rep})
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
