"""Calibration of the 10-90% bands: predict before you look.

Before each new probe (map) or push, the learner predicts it from the rows so far; we then check whether the real
outcome fell inside its 10-90% band. Well calibrated -> ~80% inside, ~10% below, ~10% above.

    python -m eval.calibration --learners tabpfn gp --seeds 3

Map: the actual active-probing sequence on random layouts (oracle probes, like eval/map_eval.py).
Push: 50 random strikes in physics (normal friction), then predict push k from pushes 0..k-1, for k = 5..49.
Writes eval/out/calibration.{json,png}.
"""
from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from eval.map_eval import oracle_probe, random_layout
from src.demos.push import DIST_RANGE, OFFSET_RANGE, SPEED_RANGE
from src.demos.touch_map import TouchMap
from src.learn.baselines import learner_kwargs, make_learner
from src.sim.env import Sim, in_workspace, run
from src.sim.primitives import push

warnings.filterwarnings("ignore")
OUT = Path(__file__).resolve().parent / "out"
MAP_PROBES, MAP_START = 60, 5      # score probes 5..59 (the first few have almost no context)
N_PUSH, PUSH_START = 50, 5


def map_calibration(learner, seed, n_est, pred_step):
    rng = np.random.default_rng(seed)
    sim = Sim()
    random_layout(sim, rng)
    tm = TouchMap(learner, "active", seed=seed, learner_kwargs=learner_kwargs(learner, n_est), pred_step=pred_step)
    tip, rows = np.array([0.46, 0.0]), []
    for k in range(MAP_PROBES):
        x, y = tm.next_target(tip)
        h = oracle_probe(sim, x, y, rng)
        if k >= MAP_START:
            q10, q50, q90 = tm._predict_at(x, y)
            rows.append((float(q10), float(q50), float(q90), float(h)))
        tm.add_probe(x, y, h)
        tm.wait()
        tip = np.array([x, y])
    tm.service.shutdown()
    return rows


def collect_pushes(seed):
    """Random strikes in physics; returns features (offset, distance, speed) and outcomes (along, left)."""
    rng = np.random.default_rng(1000 + seed)
    sim = Sim()
    for i, b in enumerate(("box_a", "box_b", "box_c")):
        sim.place(b, 2.0 + 0.3 * i, 0.0)
    sim.place("puck", 0.46, 0.0, 0.02)
    sim.settle(0.3)
    X, Y = [], []
    while len(X) < N_PUSH:
        puck, _ = sim.puck_pose()
        if not in_workspace(*puck, 0.08):
            sim.place("puck", 0.46, rng.uniform(-0.1, 0.1), 0.02)
            sim.settle(0.3)
            continue
        centre = np.array([0.46, 0.0]) - puck
        angle = np.arctan2(centre[1], centre[0]) + rng.normal(0, 1.2)   # roughly back towards the middle
        f = (rng.uniform(*OFFSET_RANGE), rng.uniform(*DIST_RANGE), rng.uniform(*SPEED_RANGE))
        r = run(sim, push(sim, angle, *f))
        if not r.ok:
            continue
        X.append(f)
        Y.append(r.d_push)
    return np.array(X), np.array(Y)


def push_calibration(learner, X, Y, n_est):
    rows = []
    for j in (0, 1):   # along, left
        m = make_learner(learner, **learner_kwargs(learner, n_est))
        for k in range(PUSH_START, len(X)):
            q10, q50, q90 = m.fit(X[:k], Y[:k, j]).predict_quantiles(X[k:k + 1])
            rows.append((float(q10[0]), float(q50[0]), float(q90[0]), float(Y[k, j])))
    return rows


def summary(rows):
    a = np.array(rows)
    lo, hi, y = a[:, 0], a[:, 2], a[:, 3]
    return {"n": len(a), "inside": float(np.mean((y >= lo) & (y <= hi))), "below": float(np.mean(y < lo)),
            "above": float(np.mean(y > hi)), "median_band": float(np.median(hi - lo))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--learners", nargs="+", default=["tabpfn", "gp"])
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--n-estimators", type=int, default=1)
    ap.add_argument("--pred-step", type=float, default=0.04)
    args = ap.parse_args()
    pushes = [collect_pushes(s) for s in range(args.seeds)]
    print("collected", sum(len(x) for x, _ in pushes), "physics pushes")
    res = {}
    for lr in args.learners:
        ps = args.pred_step if lr == "tabpfn" else None
        m_rows = [r for s in range(args.seeds) for r in map_calibration(lr, s, args.n_estimators, ps)]
        p_rows = [r for X, Y in pushes for r in push_calibration(lr, X, Y, args.n_estimators)]
        res[lr] = {"map": summary(m_rows), "push": summary(p_rows)}
        for task in ("map", "push"):
            s = res[lr][task]
            print(f"{lr:8s} {task:4s}: inside 10-90% band {s['inside']:.0%} (target 80%) | below {s['below']:.0%} "
                  f"above {s['above']:.0%} | n={s['n']} | median band {s['median_band'] * 100:.2f} cm", flush=True)
    OUT.mkdir(exist_ok=True)
    (OUT / "calibration.json").write_text(json.dumps(res, indent=2))
    fig, ax = plt.subplots(figsize=(6, 3.2))
    labels, w = [f"{lr}\n{t}" for lr in res for t in ("map", "push")], 0.6
    vals = [[res[lr][t][k] for lr in res for t in ("map", "push")] for k in ("below", "inside", "above")]
    bottom = np.zeros(len(labels))
    for v, name, c in zip(vals, ("below 10%", "inside 10-90%", "above 90%"), ("#9bb7d4", "#3b7dd8", "#f0a35e")):
        ax.bar(labels, v, w, bottom=bottom, label=name, color=c)
        bottom += np.array(v)
    ax.axhline(0.1, color="k", lw=0.8, ls=":")
    ax.axhline(0.9, color="k", lw=0.8, ls=":")
    ax.set_ylabel("share of predictions")
    ax.set_title("Is the 10-90% band right? (dotted: ideal 10% / 90%)", fontsize=10)
    ax.legend(frameon=False, fontsize=8, loc="upper left", bbox_to_anchor=(1, 1))
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "calibration.png", dpi=150)
    print("wrote", OUT / "calibration.png")


if __name__ == "__main__":
    main()
