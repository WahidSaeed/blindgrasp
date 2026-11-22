"""Headless Demo 1 evaluation: map error and occupancy IoU vs number of probes.

Probes are ray-cast ("oracle") by default: height = highest surface under the 6 mm tip disc, plus 0.3 mm
noise. eval/phase1_check.py shows real physics probes match the surface to ~1 mm, so this keeps the
learning comparison fast. Use --physics to drive the arm instead (slow).

    python -m eval.map_eval --learners gp knn mlp tabpfn --strategies active random raster --seeds 10
    python -m eval.map_eval --recovery            # move a box after --move-at probes, measure re-mapping

Writes eval/out/map_<tag>.json and eval/out/map_<tag>.png.
"""
from __future__ import annotations

import argparse
import json
import time
import warnings
from pathlib import Path

import numpy as np

from src.demos.touch_map import TouchMap
from src.learn.baselines import learner_kwargs
from src.sim.env import Sim, TIP_R, in_workspace

warnings.filterwarnings("ignore")
OUT = Path(__file__).resolve().parent / "out"
BOX_HALF = {"box_a": (0.05, 0.04, 0.04), "box_b": (0.07, 0.035, 0.03), "box_c": (0.035, 0.035, 0.06)}


def random_layout(sim: Sim, rng: np.random.Generator, names=tuple(BOX_HALF)) -> None:
    """Place boxes at random non-overlapping poses with their centres reachable."""
    placed = []
    sim.place("puck", 2.0, 1.0, 0.02)  # puck off the table for mapping runs
    for name in names:
        hx, hy, hz = BOX_HALF[name]
        for _ in range(1000):
            x, y, yaw = rng.uniform(0.25, 0.70), rng.uniform(-0.32, 0.32), rng.uniform(0, np.pi / 2)
            if not in_workspace(x, y, 0.02):
                continue
            r = np.hypot(hx, hy)
            if all(np.hypot(x - px, y - py) > r + pr + 0.03 for px, py, pr in placed):
                break
        sim.place(name, x, y, hz, yaw)
        placed.append((x, y, np.hypot(hx, hy)))


def oracle_probe(sim: Sim, x: float, y: float, rng: np.random.Generator) -> float:
    pts = [(x, y)] + [(x + TIP_R * np.cos(a), y + TIP_R * np.sin(a)) for a in np.linspace(0, 2 * np.pi, 8, endpoint=False)]
    return max(sim.true_height(px, py) for px, py in pts) + rng.normal(0, 0.0003)


def physics_probe(sim: Sim, x: float, y: float, rng=None):
    from src.sim.env import run
    from src.sim.primitives import probe_down

    r = run(sim, probe_down(sim, x, y))
    return r.x, r.y, r.height


def run_one(learner: str, strategy: str, seed: int, n_probes: int, physics: bool = False,
            move_at: int | None = None, n_estimators: int | None = None, pred_step: float | None = None,
            max_rows: int | None = None) -> dict:
    rng = np.random.default_rng(seed)
    sim = Sim()
    random_layout(sim, rng)
    tm = TouchMap(learner, strategy, seed=seed, learner_kwargs=learner_kwargs(learner, n_estimators),
                  pred_step=pred_step, max_rows=max_rows)
    truth, truth_geom = tm.truth_grid(sim), tm.truth_grid(sim, footprint=False)
    curve, fit_s, moved_info = [], [], None
    tip = np.array([0.46, 0.0])
    for k in range(n_probes):
        if move_at is not None and k == move_at:
            # Move the box the map knows best (most probes on it), like a presenter moving a box the
            # audience has watched being mapped, to a new random reachable spot away from where it was.
            X, Yh = tm.table.arrays()
            def rows_on(b):
                hx, hy, _ = BOX_HALF[b]
                return int(np.sum((np.linalg.norm(X - sim.body_pos(b)[:2], axis=1) < np.hypot(hx, hy)) & (Yh > 0.01)))
            moved = max(BOX_HALF, key=rows_on)
            old = sim.body_pos(moved)[:2]
            for _ in range(1000):
                x, y = rng.uniform(0.25, 0.70), rng.uniform(-0.32, 0.32)
                others = [sim.body_pos(b)[:2] for b in BOX_HALF if b != moved]
                if (in_workspace(x, y, 0.02) and np.hypot(*(np.array([x, y]) - old)) > 0.15
                        and all(np.hypot(*(np.array([x, y]) - o)) > 0.16 for o in others)):
                    break
            sim.place(moved, x, y, BOX_HALF[moved][2], rng.uniform(0, np.pi / 2))
            truth, truth_geom = tm.truth_grid(sim), tm.truth_grid(sim, footprint=False)
            moved_info = {"box": moved, "rows_on_it": rows_on(moved) if False else None, "from": old.tolist(), "to": [x, y]}
        x, y = tm.next_target(tip)
        if physics:
            x, y, h = physics_probe(sim, x, y)
        else:
            h = oracle_probe(sim, x, y, rng)
        tip = np.array([x, y])
        ev = tm.add_probe(x, y, h)
        tm.wait()
        fit_s.append(tm.service.latest.seconds)
        m = tm.metrics(truth, truth_geom)
        m["surprise"] = bool(ev.surprise)
        m["confirmed"] = bool(ev.confirmed)
        curve.append(m)
    tm.service.shutdown()
    return {"learner": learner, "strategy": strategy, "seed": seed, "curve": curve,
            "fit_s_median": float(np.median(fit_s)), "moved": moved_info, "move_at": move_at}


def summarize(results: list[dict], move_at: int | None) -> None:
    groups: dict[tuple, list] = {}
    for r in results:
        groups.setdefault((r["learner"], r["strategy"]), []).append(r)
    checkpoints = [10, 20, 40, 60, 80, 120]
    print(f"\n{'learner':8s} {'strategy':8s} " + " ".join(f"{'@'+str(c):>13s}" for c in checkpoints) + "   fit")
    print(" " * 18 + " ".join(f"{'MAE cm / IoU':>13s}" for _ in checkpoints))
    for (lr, st), rs in sorted(groups.items()):
        row = []
        for c in checkpoints:
            vals = [r["curve"][c - 1] for r in rs if len(r["curve"]) >= c]
            row.append(f"{np.mean([v['mae'] for v in vals])*100:5.2f} / {np.mean([v['iou'] for v in vals]):.2f}" if vals else " " * 13)
        print(f"{lr:8s} {st:8s} " + " ".join(f"{s:>13s}" for s in row) + f"   {np.median([r['fit_s_median'] for r in rs]):.3f}s")
        g = [np.mean([r["curve"][c - 1]["iou_geom"] for r in rs]) for c in checkpoints if all(len(r["curve"]) >= c for r in rs)]
        print(f"{'':17s}  geometric IoU: " + "  ".join(f"{v:.2f}" for v in g))
        if move_at is not None:
            rec = []
            for r in rs:
                base = r["curve"][move_at - 1]["iou"]
                after = [i for i, v in enumerate(r["curve"][move_at:], 1) if v["iou"] >= min(0.8, base) - 0.05 and v["mae"] < 0.01]
                rec.append(after[0] if after else np.inf)
            det = []
            for r in rs:
                hits = [i for i, v in enumerate(r["curve"][move_at:], 1) if v.get("confirmed")]
                det.append(hits[0] if hits else np.inf)
            det = np.array(det)
            print(f"{'':17s}  after the move: change confirmed within 10 probes in {np.mean(det <= 10)*100:.0f}% of seeds "
                  f"(median {np.median(det):.0f} probes); IoU back to pre-move level: median {np.median(rec):.0f} probes, "
                  f"within 10 in {np.mean(np.array(rec) <= 10)*100:.0f}%")


def plot(results: list[dict], path: Path, move_at: int | None) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    groups: dict[tuple, list] = {}
    for r in results:
        groups.setdefault((r["learner"], r["strategy"]), []).append(r)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for (lr, st), rs in sorted(groups.items()):
        n = min(len(r["curve"]) for r in rs)
        k = np.arange(1, n + 1)
        for ax, key, scale in ((axes[0], "mae", 100), (axes[1], "iou", 1)):
            v = np.array([[c[key] for c in r["curve"][:n]] for r in rs]) * scale
            ax.plot(k, v.mean(0), label=f"{lr} / {st}", ls={"active": "-", "lse": "-.", "random": "--", "raster": ":"}[st])
    axes[0].set(xlabel="probes", ylabel="height MAE (cm)", title="Map error"); axes[0].axhline(1, c="k", lw=0.5)
    axes[1].set(xlabel="probes", ylabel="occupancy IoU", title="Occupancy IoU", ylim=(0, 1)); axes[1].axhline(0.8, c="k", lw=0.5)
    for ax in axes:
        ax.grid(alpha=0.3)
        if move_at is not None:
            ax.axvline(move_at, c="r", lw=0.8)
    axes[1].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=120)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--learners", nargs="+", default=["gp", "knn", "mlp"])
    ap.add_argument("--strategies", nargs="+", default=["active", "random", "raster"])
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--probes", type=int, default=80)
    ap.add_argument("--physics", action="store_true")
    ap.add_argument("--recovery", action="store_true", help="move box_a after --move-at probes")
    ap.add_argument("--move-at", type=int, default=40)
    ap.add_argument("--tag", default=None)
    ap.add_argument("--n-estimators", type=int, default=None, help="TabPFN ensemble size")
    ap.add_argument("--pred-step", type=float, default=None, help="coarser prediction grid (m)")
    ap.add_argument("--max-rows", type=int, default=None)
    args = ap.parse_args()
    move_at = args.move_at if args.recovery else None
    tag = args.tag or ("recovery" if args.recovery else "curves")

    results, t0 = [], time.perf_counter()
    for lr in args.learners:
        for st in args.strategies:
            for s in range(args.seeds):
                results.append(run_one(lr, st, s, args.probes, args.physics, move_at,
                                       args.n_estimators, args.pred_step, args.max_rows))
            print(f"done {lr}/{st} ({time.perf_counter() - t0:.0f}s)", flush=True)
    OUT.mkdir(exist_ok=True)
    (OUT / f"map_{tag}.json").write_text(json.dumps(results))
    summarize(results, move_at)
    plot(results, OUT / f"map_{tag}.png", move_at)
    print(f"wrote {OUT / f'map_{tag}.png'}")


if __name__ == "__main__":
    main()
