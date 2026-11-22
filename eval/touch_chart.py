"""README / pitch chart for finding the puck by touch (push_eval --sense touch JSONs in eval/out).

    .venv/bin/python -m eval.touch_chart [BEFORE.json] [AFTER.json]   -> docs/eval/touch_search.png

Left: touches needed to find the puck after each push (median), before vs after the search and planner changes.
Right: goals reached when the robot only knows where the puck is by touch, on the normal table and after it turns icy.
Defaults: eval/out/touch_v1.json (2-D search, random planner) vs eval/out/touch_v2.json (1-D search along the push
line, cautious planner, designed seed pushes).
"""
import json
import statistics as st
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

COL = {"tabpfn": "#2a78d6", "gp": "#eb6834"}          # same fixed colours as eval/summary_chart.py
TINT = {"tabpfn": "#a9c9f0", "gp": "#f6c2a8"}         # lighter step of the same hue for "before"
NAME = {"tabpfn": "TabPFN", "gp": "Gaussian process"}
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e6e5e1", "#fcfcfb"


def load(path):
    rows = json.load(open(path))
    out = {}
    for lr in ("tabpfn", "gp"):
        rs = [r for r in rows if r["learner"] == lr]
        if not rs:
            continue
        touches = [t for r in rs for e in r["episodes"] for t in e.get("touches", [])]
        eps = [e for r in rs for e in r["episodes"]]
        out[lr] = {
            "touches": st.median(touches),
            "n_push": len(touches),
            "normal": (sum(e["reached"] for e in eps if not e["after_change"]), sum(not e["after_change"] for e in eps)),
            "icy": (sum(e["reached"] for e in eps if e["after_change"]), sum(e["after_change"] for e in eps)),
            "seeds": len(rs),
        }
    return out


def main() -> None:
    before_p = sys.argv[1] if len(sys.argv) > 1 else "eval/out/touch_v1.json"
    after_p = sys.argv[2] if len(sys.argv) > 2 else "eval/out/touch_v2.json"
    before, after = load(before_p), load(after_p)

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.edgecolor": GRID,
                         "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2})
    fig, (a, b) = plt.subplots(1, 2, figsize=(11, 4.2), dpi=160)
    fig.patch.set_facecolor(SURF)
    for ax in (a, b):
        ax.set_facecolor(SURF)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.yaxis.grid(True, color=GRID, lw=0.8)
        ax.set_axisbelow(True)
        ax.tick_params(axis="y", length=0)

    w = 0.36
    order = ["tabpfn", "gp"]
    for j, k in enumerate(order):
        for i, (res, col, tag) in enumerate(((before, TINT[k], "before"), (after, COL[k], "after"))):
            v = res[k]["touches"]
            x = j + (i - 0.5) * (w + 0.03)
            a.bar(x, v, width=w, color=col, edgecolor=SURF, linewidth=2)
            a.text(x, v + 0.2, f"{v:g}", ha="center", va="bottom", color=INK, fontsize=11)
            a.text(x, -0.35, tag, ha="center", va="top", color=INK2, fontsize=9)
    a.set_xticks(range(len(order)), [NAME[k] for k in order])
    a.tick_params(axis="x", length=0, pad=24)
    a.set_ylim(0, max(before[k]["touches"] for k in order) * 1.25)
    a.set_ylabel("touches to find the puck (median per push)")
    a.set_title("Finding the puck by touch · lower is better", loc="left", color=INK, fontsize=12.5, pad=12)

    groups = [("normal", "normal table"), ("icy", "after it turns icy")]
    for i, k in enumerate(order):
        pos = [j + (i - 0.5) * (w + 0.03) for j in range(len(groups))]
        vals = [100 * after[k][g][0] / max(after[k][g][1], 1) for g, _ in groups]
        b.bar(pos, vals, width=w, color=COL[k], edgecolor=SURF, linewidth=2, label=NAME[k])
        for p, (g, _) in zip(pos, groups):
            r, n = after[k][g]
            b.text(p, 100 * r / max(n, 1) + 2, f"{r}/{n}", ha="center", va="bottom", color=INK, fontsize=11)
    b.set_xticks(range(len(groups)), [g for _, g in groups])
    b.tick_params(axis="x", length=0)
    b.set_ylim(0, 132)
    b.set_yticks([0, 25, 50, 75, 100], ["0%", "25%", "50%", "75%", "100%"])
    b.set_ylabel("goals reached (within 3 cm)")
    b.set_title("Goals reached, puck found only by touch", loc="left", color=INK, fontsize=12.5, pad=12)
    b.legend(frameon=False, loc="upper center", ncol=2, labelcolor=INK2)

    s = after["tabpfn"]["seeds"]
    fig.text(0.01, 0.01, f"{s} seeds per learner; 3 goals on the normal table, then the table turns icy and 2 more. "
             f"Before: {before_p.split('/')[-1]}, after: {after_p.split('/')[-1]}. Reached is scored on the simulator's true position.",
             color=INK2, fontsize=8.5)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig("docs/eval/touch_search.png", facecolor=SURF)
    print({"before": before, "after": after})


if __name__ == "__main__":
    main()
