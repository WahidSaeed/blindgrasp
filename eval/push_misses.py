"""Prediction miss per push around a physics change, by adaptation mode (from a push_eval JSON with "misses").

    python -m eval.push_misses eval/out/push_icy.json

Pushes are counted from the change (push 1 = first push after it). Writes <json stem>_misses.png and prints a table.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BEFORE, AFTER = 4, 8   # pushes shown before / after the change


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "eval/out/push_icy.json")
    rows = json.loads(path.read_text())
    curves = defaultdict(list)   # (learner, adapt) -> list of per-seed arrays, index 0 = first push after change
    for r in rows:
        pre, post = [], []
        for ep in r["episodes"]:
            ms = [m for m in ep.get("misses", []) if m is not None]
            (post if ep["after_change"] else pre).extend(ms)
        if not post:
            continue
        seq = [np.nan] * (BEFORE - len(pre[-BEFORE:])) + pre[-BEFORE:] + post[:AFTER]
        seq += [np.nan] * (BEFORE + AFTER - len(seq))
        curves[(r["learner"], r["adapt"])].append(np.array(seq, float) * 100)

    xs = np.arange(-BEFORE + 1, AFTER + 1)
    fig, ax = plt.subplots(figsize=(7, 3.6))
    print(f"{'learner':8s} {'adapt':6s} " + " ".join(f"{x:>5d}" for x in xs) + "   (prediction miss, cm; push 1 = first after change)")
    for (lr, ad), seqs in sorted(curves.items()):
        m = np.nanmedian(np.vstack(seqs), axis=0)
        print(f"{lr:8s} {ad:6s} " + " ".join(f"{v:5.1f}" if np.isfinite(v) else "    -" for v in m))
        ax.plot(xs, m, marker="o", label=f"{lr} · {'reset on change' if ad == 'reset' else 'never reset' if ad == 'none' else ad}")
    ax.axvline(0.5, color="k", lw=1, ls="--")
    ax.text(0.6, ax.get_ylim()[1] * 0.92, "table turns icy", fontsize=9)
    ax.set_xlabel("push (relative to the change)")
    ax.set_ylabel("prediction miss (cm), median over seeds")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    out = path.with_name(path.stem + "_misses.png")
    fig.savefig(out, dpi=150)
    print("wrote", out)


if __name__ == "__main__":
    main()
