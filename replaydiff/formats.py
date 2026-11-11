"""Extra report outputs for `replaydiff compare`: junit.xml, error plots (PNG) and head-minus-base error topics (MCAP).

JUnit: one testcase per topic quantity (classname = topic, name = quantity). FAIL is a <failure>, INCONCLUSIVE an
<error> ("can't tell"), PASS has no child element. matplotlib is optional (`pip install replaydiff[plots]`).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np

ERROR_TOPIC_PREFIX = "/replaydiff/error"
ERROR_SCHEMA = {
    "type": "object",
    "properties": {
        "error": {"type": "number", "description": "head minus base (signed where the quantity is a scalar)"},
        "tolerance": {"type": "number"},
    },
}


def junit_xml(report) -> bytes:
    suite = ET.Element("testsuite", name="replaydiff", tests=str(len(report.results)),
                       failures=str(sum(r.verdict == "FAIL" for r in report.results)),
                       errors=str(sum(r.verdict == "INCONCLUSIVE" for r in report.results)))
    for r in report.results:
        case = ET.SubElement(suite, "testcase", classname=r.topic, name=r.quantity)
        if r.verdict != "PASS":
            kind = "failure" if r.verdict == "FAIL" else "error"
            msg = "; ".join(r.reasons) or r.verdict
            ET.SubElement(case, kind, message=msg, type=r.verdict).text = msg
    ET.indent(suite)
    return ET.tostring(suite, encoding="utf-8", xml_declaration=True)


def _series(e) -> tuple[np.ndarray, np.ndarray]:
    return np.asarray(e.t, dtype=float), np.asarray(e.signed if e.signed is not None else e.err, dtype=float)


def _slug(topic: str, quantity: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", f"{topic}_{quantity}").strip("_")


def write_plots(report, errors: dict, outdir: str) -> list[str]:
    """One PNG per quantity with matched messages: head-minus-base error over time and the tolerance band."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as e:
        raise RuntimeError("--plots needs matplotlib: pip install replaydiff[plots]") from e
    Path(outdir).mkdir(parents=True, exist_ok=True)
    paths = []
    for r in report.results:
        if (r.topic, r.quantity) not in errors:
            continue
        t, y = _series(errors[(r.topic, r.quantity)])
        if not len(t):
            continue
        fig, ax = plt.subplots(figsize=(7, 3))
        ax.plot(t - t[0], y, lw=1)
        if r.tolerance:
            ax.axhline(r.tolerance, color="r", ls="--", lw=0.8)
            ax.axhline(-r.tolerance, color="r", ls="--", lw=0.8)
        ax.set(title=f"{r.topic} {r.quantity}: {r.verdict}", xlabel="time (s)", ylabel="head - base")
        fig.tight_layout()
        path = str(Path(outdir) / f"{_slug(r.topic, r.quantity)}.png")
        fig.savefig(path, dpi=100)
        plt.close(fig)
        paths.append(path)
    return paths


def export_mcap(report, errors: dict, path: str) -> list[str]:
    """Write one JSON topic `/replaydiff/error/<topic>/<quantity>` per quantity, for plotting in Foxglove."""
    from mcap.writer import Writer

    topics = []
    with open(path, "wb") as f:
        w = Writer(f)
        w.start()
        schema = w.register_schema("replaydiff/Error", "jsonschema", json.dumps(ERROR_SCHEMA).encode())
        for r in report.results:
            if (r.topic, r.quantity) not in errors:
                continue
            t, y = _series(errors[(r.topic, r.quantity)])
            topic = f"{ERROR_TOPIC_PREFIX}/{r.topic.strip('/')}/{r.quantity}".replace(" ", "_")
            ch = w.register_channel(topic, "json", schema)
            for ti, yi in zip(t, y):
                data = {"error": float(yi), "tolerance": r.tolerance if r.tolerance is not None else 0.0}
                ns = int(round(ti * 1e9))
                w.add_message(ch, ns, json.dumps(data).encode(), ns)
            topics.append(topic)
        w.finish()
    return topics
