"""README summary chart from the evaluation JSONs (eval/out): map height error and pushes to the goal.

    .venv/bin/python -m eval.summary_chart   -> docs/eval/summary.png
"""
import json
import statistics as st

import matplotlib.pyplot as plt

COL = {"tabpfn": "#2a78d6", "gp": "#eb6834", "knn": "#1baf7a"}   # fixed per learner
NAME = {"tabpfn": "TabPFN", "gp": "Gaussian process", "knn": "Nearest neighbours"}
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e6e5e1", "#fcfcfb"

maps = json.load(open("eval/out/map_tabpfn_vs_baselines.json"))
mae = {}
for r in maps:
    mae.setdefault(r["learner"], []).append(r["curve"][-1]["mae"] * 100)
mae = {k: st.mean(v) for k, v in mae.items()}
pushes = json.load(open("eval/out/push_tabpfn_vs_gp.json"))
med = {}
for r in pushes:
    for e in r["episodes"]:
        med.setdefault((r["learner"], e["after_change"]), []).append(e["pushes"])
med = {k: st.median(v) for k, v in med.items()}

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2})
fig, (a, b) = plt.subplots(1, 2, figsize=(11, 4.2), dpi=160, gridspec_kw={"width_ratios": [1, 1.25]})
fig.patch.set_facecolor(SURF)
for ax in (a, b):
    ax.set_facecolor(SURF)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.yaxis.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0)

order = ["tabpfn", "knn", "gp"]
xs = range(len(order))
a.bar(xs, [mae[k] for k in order], width=0.6, color=[COL[k] for k in order], edgecolor=SURF, linewidth=2)
for x, k in zip(xs, order):
    a.text(x, mae[k] + 0.02, f"{mae[k]:.2f} cm", ha="center", va="bottom", color=INK, fontsize=11)
a.set_xticks(list(xs), [NAME[k] for k in order])
a.set_ylim(0, 1.0)
a.set_ylabel("height error after 80 touches (cm)")
a.set_title("Map height error · lower is better", loc="left", color=INK, fontsize=12.5, pad=12)

groups = [(False, "from an empty context"), (True, "after the table turns icy")]
w = 0.34
for i, k in enumerate(["tabpfn", "gp"]):
    vals = [med[(k, g)] for g, _ in groups]
    pos = [j + (i - 0.5) * (w + 0.02) for j in range(len(groups))]
    b.bar(pos, vals, width=w, color=COL[k], edgecolor=SURF, linewidth=2, label=NAME[k])
    for p, v in zip(pos, vals):
        b.text(p, v + 0.08, f"{v:g}", ha="center", va="bottom", color=INK, fontsize=11)
b.set_xticks(range(len(groups)), [g for _, g in groups])
b.set_ylim(0, 6)
b.set_ylabel("pushes to reach the goal (median)")
b.set_title("Pushes to the goal · lower is better", loc="left", color=INK, fontsize=12.5, pad=12)
b.legend(frameon=False, loc="upper right", labelcolor=INK2)

fig.text(0.01, 0.01, "3 seeds each; pushing: 9 goals before and 6 after the change. Source: eval/out/map_tabpfn_vs_baselines.json, push_tabpfn_vs_gp.json",
         color=INK2, fontsize=8.5)
fig.tight_layout(rect=(0, 0.04, 1, 1))
fig.savefig("docs/eval/summary.png", facecolor=SURF)
print({k: round(v, 3) for k, v in mae.items()}, med)
