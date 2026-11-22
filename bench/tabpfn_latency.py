"""Phase 0 benchmark: TabPFN fit + quantile predict latency on synthetic 2D height maps.

Usage:
  python -m bench.tabpfn_latency                       # all available backends
  python -m bench.tabpfn_latency --backends local:mps local:cpu hosted --runs 20

Writes bench/out/latency.md (table) and bench/out/latency.json (raw timings),
and reports rough calibration of the 10-90% quantile band.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from src import config

TABLE = (0.8, 0.6)  # metres
QUANTILES = [0.1, 0.5, 0.9]
OUT = Path(__file__).resolve().parent / "out"


def synthetic_height_map(rng: np.random.Generator):
    """Flat table with 3 random axis-aligned boxes. Returns height(x, y) in metres."""
    boxes = []
    for _ in range(3):
        w, d = rng.uniform(0.06, 0.18, size=2)
        cx = rng.uniform(w / 2, TABLE[0] - w / 2)
        cy = rng.uniform(d / 2, TABLE[1] - d / 2)
        h = rng.uniform(0.03, 0.12)
        boxes.append((cx - w / 2, cx + w / 2, cy - d / 2, cy + d / 2, h))

    def f(xy: np.ndarray) -> np.ndarray:
        z = np.zeros(len(xy))
        for x0, x1, y0, y1, h in boxes:
            m = (xy[:, 0] >= x0) & (xy[:, 0] <= x1) & (xy[:, 1] >= y0) & (xy[:, 1] <= y1)
            z[m] = np.maximum(z[m], h)
        return z

    return f


def grid(n: int) -> np.ndarray:
    xs = np.linspace(0, TABLE[0], n)
    ys = np.linspace(0, TABLE[1], n)
    gx, gy = np.meshgrid(xs, ys)
    return np.column_stack([gx.ravel(), gy.ravel()])


def time_one(reg, X, y, Q) -> tuple[float, np.ndarray]:
    """Time fit + quantile predict on an already-constructed regressor (the live service keeps one alive)."""
    t0 = time.perf_counter()
    reg.fit(X, y)
    q = reg.predict(Q, output_type="quantiles", quantiles=QUANTILES)
    dt = time.perf_counter() - t0
    return dt, np.asarray(q)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backends", nargs="+", default=None, help="e.g. local:mps local:cpu hosted")
    ap.add_argument("--contexts", nargs="+", type=int, default=[25, 100, 400, 1000])
    ap.add_argument("--grids", nargs="+", type=int, default=[30, 50])
    ap.add_argument("--runs", type=int, default=20)
    ap.add_argument("--warmup", type=int, default=1)
    ap.add_argument("--n-estimators", type=int, nargs="+", default=[8], help="TabPFN ensemble sizes to try")
    ap.add_argument("--tag", default="latency")
    args = ap.parse_args()

    cfg = config.load()
    backends = args.backends or (
        [f"local:{cfg.device}"] + (["local:cpu"] if cfg.device != "cpu" else []) + (["hosted"] if cfg.has_token else [])
    )
    print(f"config={cfg} backends={backends}")

    rng = np.random.default_rng(0)
    results = []
    for b0 in backends:
      backend, _, device = b0.partition(":")
      device = device or None
      for ne in args.n_estimators:
        b = f"{b0} n_est={ne}"
        t_load = time.perf_counter()
        reg = config.make_regressor(backend, device, n_estimators=ne)
        print(f"  {b}: constructed in {time.perf_counter() - t_load:.2f}s")
        for n_ctx in args.contexts:
            for g in args.grids:
                Q = grid(g)
                times, covered, abs_err, spread = [], [], [], []
                for r in range(args.warmup + args.runs):
                    f = synthetic_height_map(rng)
                    X = rng.uniform([0, 0], TABLE, size=(n_ctx, 2))
                    y = f(X) + rng.normal(0, 0.001, n_ctx)
                    try:
                        dt, q = time_one(reg, X, y, Q)
                    except Exception as e:  # noqa: BLE001
                        print(f"  {b} ctx={n_ctx} grid={g}: FAILED {type(e).__name__}: {e}")
                        times = []
                        break
                    if r < args.warmup:
                        continue
                    times.append(dt)
                    truth = f(Q)
                    lo, med, hi = q[0], q[1], q[2]
                    covered.append(np.mean((truth >= lo) & (truth <= hi)))
                    abs_err.append(np.mean(np.abs(med - truth)))
                    spread.append(np.corrcoef(hi - lo, np.abs(med - truth))[0, 1])
                if not times:
                    continue
                t = np.array(times)
                row = dict(
                    backend=b, context=n_ctx, grid=f"{g}x{g}",
                    median_s=float(np.median(t)), p95_s=float(np.percentile(t, 95)),
                    coverage_10_90=float(np.mean(covered)), mae_cm=float(np.mean(abs_err) * 100),
                    spread_err_corr=float(np.nanmean(spread)),
                )
                results.append(row)
                print(
                    f"  {b:10s} ctx={n_ctx:5d} grid={g}x{g}: median {row['median_s']:.3f}s "
                    f"p95 {row['p95_s']:.3f}s | cover {row['coverage_10_90']:.2f} "
                    f"MAE {row['mae_cm']:.2f}cm corr {row['spread_err_corr']:.2f}"
                )

    OUT.mkdir(exist_ok=True)
    (OUT / f"{args.tag}.json").write_text(json.dumps(results, indent=2))
    lines = [
        "| Backend | Context | Grid | Median (s) | p95 (s) | 10–90% coverage | MAE (cm) | spread/err corr |",
        "|---|---|---|---|---|---|---|---|",
    ] + [
        f"| {r['backend']} | {r['context']} | {r['grid']} | {r['median_s']:.3f} | {r['p95_s']:.3f} | "
        f"{r['coverage_10_90']:.2f} | {r['mae_cm']:.2f} | {r['spread_err_corr']:.2f} |"
        for r in results
    ]
    (OUT / f"{args.tag}.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
